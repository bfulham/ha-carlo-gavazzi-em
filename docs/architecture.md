# How it works

A guided tour of `custom_components/carlo_gavazzi_em/` (version 1.3.2). Home Assistant concepts are used by name; file and function names are real so you can follow along.

## Layout of the package

| File | Role |
|---|---|
| `manifest.json` | Domain `carlo_gavazzi_em`, type `hub`, `iot_class: local_polling`, `config_flow: true`, requires `pymodbus>=3.11.2`. |
| `const.py` | Domain, config keys, defaults, protocol limits, register addresses, `MeterInfo`, `TransportMode`. |
| `modbus.py` | `ModbusGatewayClient` (one serialised TCP connection) and the pure decoding helpers. |
| `registers.py` | The register map: model code tables, option mappings, and the `RegisterSensorDescription` lists `SENSOR_DESCRIPTIONS` (EM270/EM280, 105) and `SENSOR_DESCRIPTIONS_EM24` (64). |
| `api.py` | `CarloGavazziAPI`: discovery, meter metadata, read-block building, polling. |
| `coordinator.py` | `CarloGavazziCoordinator` (a `DataUpdateCoordinator`): decides what to read, runs polls, estimates load. |
| `tcd.py` | Pure logic that turns a TCD layout into names, defaults and device links (no Home Assistant imports at run time). |
| `layout_sync.py` | Applies a layout to sensors that already exist in the entity registry (enable/disable, rename). |
| `sensor.py` | The sensor platform: `CarloGavazziSensor` and `decode_sensor_value`. |
| `config_flow.py` | Setup, Reconfigure and the options flow. |
| `diagnostics.py` | Redacted diagnostics download. |
| `__init__.py` | Entry setup/unload and `async_migrate_entry`. |
| `strings.json` / `translations/en.json` | All user-visible text (kept identical). |
| `brand/` | Icons for the integration. |

Package initialisation deliberately imports neither `pymodbus` nor the API (they are imported inside `async_setup_entry`), so Home Assistant can always load the config flow and show its first form.

## Data flow

```text
config_flow ──► config entry (data: host, port, timeouts, meters, tcd_layout, ...)
                    │
        async_setup_entry (__init__.py)
                    │  builds CarloGavazziAPI (one Modbus client) and the coordinator
                    ▼
CarloGavazziCoordinator ── every update_interval ──► enabled_keys()  (what is switched on?)
        │                                                 │
        │                                                 ▼
        │                                  api.async_fetch_all_meter_data
        │                                    blocks_for(model, enabled keys)  → contiguous reads
        │                                    ModbusGatewayClient.read_holding_registers (function 3)
        ▼
 coordinator.data[meter][ "values" ][key] = raw registers
        │
        ▼
CarloGavazziSensor.native_value → decode_sensor_value (scaling, sentinels, option names)
```

## Configuration stored in the config entry

`entry.data` (set by the config flow; `entry.options` overrides the polling fields):

| Key | Content |
|---|---|
| `host`, `port` | Gateway. Unique ID is `host:port`. |
| `update_interval`, `timeout`, `request_retries`, `delay_between_requests_ms` | Polling settings. |
| `transport_mode`, `detected_transport_mode` | Requested framing and the framing found by the scan. |
| `scan_start`, `scan_end`, `discovery_passes` | The scan range and number of passes (3). |
| `meters` | A list of `MeterInfo` dictionaries (slave id, identification code, model name, family, serial, device uid, firmware, production year, secondary address). |
| `tcd_layout` | See below. |

`tcd_layout` is keyed by the meter's device identifier:

```json
{
  "serial:ABC123": {
    "board": {"name": "DB1", "device_id": null},
    "a1": {"mode": "three_phase",
           "lines": [{"name": "Oven", "short_name": "R1", "device_id": null}]},
    "a2": {"mode": "single_phase",
           "lines": [{"name": "Pump", "short_name": "R2", "device_id": null},
                     {"name": null, "short_name": null, "device_id": null},
                     {"name": "Fan", "short_name": "B2", "device_id": "<device registry id>"}]}
  }
}
```

`mode` is `unused`, `three_phase` (1 line) or `single_phase` (3 lines). The config flow version is `5` (see [Migrations](#migrations)).

## Modbus layer (`modbus.py`)

- `ModbusGatewayClient` wraps pymodbus' `AsyncModbusTcpClient`. All reads go through one `asyncio.Lock`, so only one request is on the wire at a time; after each read it sleeps the configured **delay between requests**.
- **Framing**: `socket` uses the Modbus TCP header (MBAP); `rtu_over_tcp` sends the raw RTU frame inside TCP. Switching mode closes the connection and reconnects on the next request.
- A stale client is always closed before a new one is created and pymodbus auto-reconnect is off (`reconnect_delay=0`, `retries=0`): leaked clients once opened parallel connections that a single-connection gateway refused (fixed in 1.1.2).
- `async_read_holding_registers(slave, address, count, attempts)` returns the list of registers or `None` after all attempts fail. It checks the slave id (1-247), the count (1-18), and that the reply has exactly the requested number of registers. Timeouts and socket errors close the connection (it is re-opened on the next attempt). A "no usable reply" (meter silent, or a gateway exception pymodbus discards) keeps a healthy Modbus TCP connection open but reconnects under RTU-over-TCP, which has no transaction id to discard a late reply.
- Decoders: unsigned/signed 16-bit, signed/unsigned 32-bit (**LSW first**), ASCII serial number (printable bytes only, 13 characters), and `is_missing_32` for the sentinel values.

## Discovery (`api.py`)

`async_discover_meters` is described step by step in [setup.md](setup.md#step-4---scanning). In short: connect; up to three passes over the range; read identification register `0x000B` once per address (known codes only); then `async_read_meter_info` reads the firmware version/revision and, for EM270/EM280, the serial number block and secondary address. The result is a list of `MeterInfo`.

Meter family: EM24 code -> `em24`; identification >= 280 -> `em280`; EM270 with version code 1 -> `em270_x`, 2 -> `em270_w`, otherwise `em270`.

## Polling

### What is read

`coordinator.enabled_keys()` returns, per meter, the keys of the sensors that are **enabled** in the entity registry (or enabled by default if the entity does not exist yet). A TCD voltage alias contributes the key of the register it points at (`source_key`). `api.blocks_for(model_family, keys)` (cached) then builds the reads:

1. Take the enabled descriptions (aliases are skipped; they are served by the register they alias).
2. Sort by register address.
3. Merge descriptions into one read while they are **adjacent** (next address equals the end of the previous one) and the read stays within **18 registers** (EM24: **11**).

Disabled sensors therefore cost nothing on the bus.

### One poll

`async_fetch_all_meter_data` goes through the meters in order, and for each read block calls `async_read_holding_registers` with `attempts = retries + 1`. For each meter it records `available` (at least one block succeeded, or there was nothing to read), counts of blocks, and the raw registers per key. If **no block of any meter** succeeded, the whole update raises `UpdateFailed` ("No meter returned any register data") and every sensor becomes unavailable until the next success. A meter that answers some blocks and not others leaves just the missing sensors unavailable.

`last_poll_seconds` records how long the last successful poll took (used for the interval recommendation).

### Turning raw registers into values (`sensor.py`)

`decode_sensor_value`:

- 32-bit: reject the missing sentinels; decode signed or unsigned per the description; divide by `scale`; reject voltages above the description's `maximum`; round to 6 decimals (integer if `scale` is 1).
- 16-bit signed: same with sign handling. 16-bit unsigned: `0xFFFF` is "not available"; text mappings (`map_option`) turn configuration codes into names, otherwise divide by `scale`.

`CarloGavazziSensor.available` is true only when the coordinator's last update succeeded **and** the value decoded to something (not `None`).

### Update interval and recommendation

The coordinator's interval comes from the options (if set) or the entry data (default 10 s, minimum 5 s). `poll_estimate()` produces the numbers shown in the Configure dialog: enabled sensors, reads per poll, seconds, and `recommended = max(5, ceil(seconds x 1.25))`, where each read is modelled as `(13 + 2 x registers) x 11 / 9600 + 0.06 s + request delay`, replaced by the last measured poll time once one exists. See [setup.md](setup.md#choosing-the-update-interval) for worked numbers.

## Entities and devices (`sensor.py`)

- One `CarloGavazziSensor` per description per meter. The unique ID is `<device identifier>_<key>`, so entities keep their identity when you rename or relink them.
- The device is the meter (identifiers `(carlo_gavazzi_em, <device identifier>)`, manufacturer *Carlo Gavazzi*, model, model ID, serial number, firmware). A line linked to another device uses that device's identifiers (or connections) instead; if it no longer exists the sensor falls back to the meter.
- Line sensors (`placement.meta` is set) turn `has_entity_name` off, so the name is exactly the one built by `tcd.py`, and set `entity_id` to `line_entity_id(...)`. This applies only when the entity is first added.
- `extra_state_attributes` exposes `line_name`, `short_name`, `tcd`, `phase`, `distribution_board` for line sensors.

## TCD layout logic (`tcd.py`)

`place_descriptions(descriptions, layout)` returns, for every key of one meter, a `Placement(description, device_id, meta)`:

- Keys not starting with `tcd` are meter-wide. If the meter has any wired TCD they are switched off by default.
- Keys `tcdaN_<field>` are looked up in the layout for channel `aN`:
  - **Not connected / no layout:** left as is (a layout-less meter keeps stock names and defaults; a channel marked unused is switched off).
  - **Three-phase load:** every field is named after the single line; only `w_total` and `kwh_total` are on.
  - **Three single-phase lines:** a field with a phase `_lM` belongs to line M; only `w_lM` and `kwh_lM` are on. Fields without a phase (totals) are off with the stock name.
  - A line without a long or short name is off.
- The name is `<label> <metric>[ L<phase>]` where the label is the long name, else the short name, and the metric is the stock name stripped of the TCD prefix and trailing `Total`/`L1`..`L3`.
- `meta.object_id` is `<short name or long name>_<metric>[_l<phase>]`; `layout_sync.line_entity_id` prefixes the board (or the meter's device name), slugifies it and adds `sensor.`.
- `legacy_entity_name` reproduces the names version 1.2.0 gave, so its entity IDs can be recognised for renaming.

## Applying a layout to existing sensors (`layout_sync.py`)

`sync_entities(hass, entry, meters, layout, old_layout=None)` walks the registry entry of every TCD sensor and default meter-wide sensor of every EM270/EM280 meter in the layout:

1. **Rename** (line sensors only), under the conditions in [tcd-lines.md](tcd-lines.md#when-entity-ids-change).
2. **Enable/disable**: a sensor that should be on and was disabled *by the integration* is enabled; one that should be off and is currently enabled is disabled *by the integration*. A sensor disabled *by the user* is never touched.

It is called from the config flow on Reconfigure and from the migrations.

## Migrations

`__init__.async_migrate_entry` upgrades the stored entry; the config flow `VERSION` is **5**.

| From version | What it does |
|---|---|
| 1 -> 3 | 1.1.3 disables non-default sensors in the entity registry so existing installs stop polling them; default sensors the integration disabled are re-enabled. |
| 2 -> 3 | The default set grew (TCDA1 per-phase W and kWh), so default sensors the integration had disabled are re-enabled. |
| < 4 | `sync_entities` with the stored layout: applies the 1.3 defaults and renames 1.2.0-style entity IDs. |
| < 5 | `sync_entities` again to switch line A and V off (1.3.2). |

Sensors the user disabled are never re-enabled. A migration (like Reconfigure) can not tell a sensor the integration enabled from one you enabled by hand, so a hand-enabled TCD sensor or default meter-wide sensor that the layout says should be off is switched off; enable it again afterwards.

## Config flow (`config_flow.py`)

`CarloGavazziConfigFlow.VERSION = 5`. Steps: `user` -> (`advanced`) -> (`scan_range`) -> `discover` (progress task) -> `finish` -> `tcd_layout` -> `tcd_board` / `tcd_names` (looping over the queue of TCDs in use) -> entry. Notable details:

- `discover` runs the scan as a background task and ends with `async_show_progress_done` (Home Assistant only allows a progress step to be followed by another progress step or `progress_done`).
- `finish` collects the result, probes the EM280 CT-primary registers to pre-select the TCD wiring, closes the API and moves on.
- Reconfigure starts from `{**entry.data, **entry.options}` and pre-fills everything (`_stored_layout`, `_stored_board`).
- The options flow (`CarloGavazziOptionsFlow`, `OptionsFlowWithReload`) shows the polling estimate and saves `update_interval`, `timeout`, `request_retries`, `delay_between_requests_ms`.

## Safety properties

- **Read-only.** The only Modbus call is `read_holding_registers`. There is no write, reset or programming path; the bundled gateway proxy also refuses every non-read function.
- **No secrets stored** other than the gateway address; diagnostics redact the host and meter serial numbers.
- **Bounded traffic.** One request at a time, a delay after each, reads sized to the protocol limits, only enabled registers.
