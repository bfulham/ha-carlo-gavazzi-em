# Carlo Gavazzi EM for Home Assistant

A local, read-only Home Assistant custom integration for Carlo Gavazzi **EM270 X**, **EM270 W**, **EM280**, and **EM24** energy meters connected through a transparent Modbus RTU-to-Modbus TCP gateway.

> [!NOTE]
> The integration is verified against the supplied EM270/EM280 protocol documentation and by automated import, lint, HACS and hassfest checks. Hardware test reports are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

**Documentation:** [docs/README.md](docs/README.md) covers installation, the gateway, every setup screen, TCD wiring and naming, the full sensor list, how the code works and troubleshooting.

## Features

- UI setup through a Home Assistant config flow.
- One config entry per TCP gateway and one Home Assistant device per discovered meter.
- Full slave-address scan from **1–247** by default, with an optional restricted range.
- Three discovery passes; passes two and three skip addresses already discovered.
- Live discovery progress showing the pass, current address, framing mode, and number of meters found.
- Automatic probing of standard Modbus TCP and RTU-over-TCP framing, or an explicit user-selected mode.
- Automatic EM270/EM280/EM24 model identification.
- Serial number, model, model ID, and firmware stored as Home Assistant device information rather than duplicate sensors.
- All documented read-only measurement and diagnostic registers available as sensors for EM270/EM280 (105) and EM24 (64) meters; only a small default set is enabled and **only enabled sensors are polled**.
- TCD support for EM270/EM280: per TCD choose *one 3-phase load* or *three single-phase lines*, name each line (long name, short name, or link an existing device) and a distribution board, and get W, kWh (on) and A, V (off) sensors with predictable entity IDs `sensor.<board>_<short name>_<w|a|v|kwh>`.
- A recommended update interval based on how many sensors are enabled.
- Configurable update interval, timeout, retry count, and delay between requests.
- Contiguous reads limited to the protocol maximum of 18 registers (11 on the EM24).
- LSW/MSW 32-bit decoding and handling for the documented unsupported, overflow, and missing-TCD values.
- Reconfigure/rescan flow (pre-filled from the previous setup) and an automatically reloading options flow.
- Redacted diagnostics.
- No write, reset, or programming commands.

## Requirements

- Home Assistant **2026.2.3** or newer.
- A transparent RTU-to-TCP gateway reachable from Home Assistant.
- The gateway serial port already configured to match the RS485 bus.

A generic transparent gateway does not expose a standard Modbus method for changing its own baud, parity, or stop-bit settings. The integration can read the meter's serial settings after communication succeeds, but it cannot configure the gateway itself.

## Installation with HACS

1. Open **HACS → Integrations**.
2. Open the three-dot menu and choose **Custom repositories**.
3. Add `https://github.com/bfulham/ha-carlo-gavazzi-em` as an **Integration** repository.
4. Install **Carlo Gavazzi EM**.
5. Restart Home Assistant.
6. Open **Settings → Devices & services → Add integration** and search for **Carlo Gavazzi EM**.

## Manual installation

Copy:

```text
custom_components/carlo_gavazzi_em
```

into:

```text
/config/custom_components/carlo_gavazzi_em
```

Restart Home Assistant before opening the config flow.

## Setup

**Settings -> Devices & services -> Add integration -> Carlo Gavazzi EM.** The dialog asks, in order:

1. **Gateway** - host/IP, TCP port (502), update interval (5-3600 s, default 10), and tick-boxes for advanced settings and a restricted address range.
2. *(optional)* **Advanced settings** - request timeout (0.75 s), polling retries (2), delay between requests (10 ms), TCP framing (Auto detect / Modbus TCP / RTU over TCP).
3. *(optional)* **Address range** - first and last slave address (default 1-247).
4. **Scan** - three passes over the range with live progress.
5. **TCD wiring** (EM270/EM280 only) - per TCD: *Not connected*, *One 3-phase load* or *Three single-phase lines*.
6. **Distribution board** - once per meter: a name or an existing device (starts the entity IDs).
7. **Line names** - per TCD: name, short name (R1, W1, ...) or a linked device per line. Empty lines are not connected; *Skip the rest* sets the remaining TCDs up later.

A full scan can take several minutes because unused RTU addresses each wait for the timeout. Restrict the range when the expected slave IDs are known. Every field is documented in [docs/setup.md](docs/setup.md).

## Device and entity behaviour

Each discovered meter is one Home Assistant device. Its serial number, model, model ID and firmware are device information, not sensors. The device identifier is the serial number when it can be read, otherwise `gateway:<host>:<port>:slave:<address>` (always the latter on the EM24, which exposes no serial number).

**Defaults.** A meter with no TCD wired has phase voltages, phase currents, power and energy used on (EM270/EM280 also `TCDA1 W` and `TCDA1 kWh` per phase; EM24 also export energy). Once a TCD is wired, the meter-wide sensors are switched off, and each named line gets **W and kWh on, A and V off** (a 3-phase load gets one W and one kWh total). Everything else is created disabled, and **a disabled sensor is not polled**, so it adds no traffic to the RS-485 bus. Enable any sensor under Settings -> Devices & services -> Entities -> the sensor -> Settings; the integration reloads and starts polling that register. Values the meter reports as not available stay *unavailable* instead of showing a wrong number.

How TCD lines are named, which entity IDs they get, and when those IDs are renamed on Reconfigure: [docs/tcd-lines.md](docs/tcd-lines.md). Every sensor, register and scaling: [docs/sensors.md](docs/sensors.md).

## Reconfigure and options

Use **Reconfigure** on the integration entry to change the gateway address, framing mode, scan range, TCD wiring, names and boards, or to rescan the RTU bus. Everything is pre-filled from the previous setup. Reconfigure re-applies the TCD defaults, so sensors you enabled by hand among the TCD and meter-wide sensors may be switched off again.

Use **Configure** to change the update interval, timeout, retry count and request delay without rescanning. Its text shows how many sensors are enabled, how many Modbus reads a poll takes, and the recommended (shortest sustainable) update interval.

## Gateway preparation

Before setup, configure the gateway serial side to match the meters:

- baud rate;
- parity;
- stop bits;
- RS485 two-wire mode; and
- a suitable RTU response timeout.

Also verify RS485 A/B polarity, termination, and unique slave addresses.

Techbase NPE/iMod gateways can be turned into a plain read-only Modbus TCP bridge with the scripts in [`contrib/`](contrib/); see [docs/gateway.md](docs/gateway.md).

## Troubleshooting

### Config flow does not open

Confirm that `/config/custom_components/carlo_gavazzi_em/manifest.json` reports the expected version, then perform a full Home Assistant restart. The repository CI includes a config-flow import test against Home Assistant 2026.6.1 to catch import-time failures.

### No meters found

1. Confirm the gateway host and TCP port are reachable from Home Assistant.
2. Confirm gateway baud, parity, stop bits, and RTU mode match the meter bus.
3. Check A/B polarity, common reference, termination, and slave addresses.
4. Try explicitly selecting **Modbus TCP** or **RTU over TCP**.
5. Increase the request timeout and inter-request delay.
6. Restrict the scan to the known address range while testing.

See also [docs/troubleshooting.md](docs/troubleshooting.md).

### Reporting an issue

Download diagnostics from the integration entry and attach them to a GitHub issue. The gateway host and serial numbers are redacted, but the saved TCD line names, short names and board names are not, so review the file first.

## Supported identification values

EM24:

| Code | Model family |
|---:|---|
| 45 | EM24DINAV93X |
| 46 | EM24DINAV03X |
| 47 | EM24DINAV53X |
| 48 | EM24DINAV63X |

The exact EM24 model is derived from the firmware version code, for example EM24DINAV93XO2X, EM24DINAV53DISX, or EM24DINAV53DR2X.

EM270 and EM280:

| Code | Model |
|---:|---|
| 270 | EM27072DMV53X2SX or EM27072DMV53X2SW |
| 271 | EM27072DMV53XOSX or EM27072DMV53XOSW |
| 272 | EM27072DMV63X2SX or EM27072DMV63X2SW |
| 273 | EM27072DMV63XOSX or EM27072DMV63XOSW |
| 280 | EM28072DMV53X2SX |
| 281 | EM28072DMV53XOSX |
| 282 | EM28072DMV63X2SX |
| 283 | EM28072DMV63XOSX |

EM270 X and W share identification codes 270–273. The integration uses the documented firmware branch to distinguish them when possible and otherwise labels the model as X/W.

## Development

```bash
python -m pip install -r requirements-dev.txt
ruff format --check .
ruff check .
python -m compileall -q custom_components/carlo_gavazzi_em scripts
```

See [docs/development.md](docs/development.md).

GitHub Actions additionally run Home Assistant hassfest, HACS validation, and a real config-flow import smoke test.

## License

MIT. This project is not affiliated with or endorsed by Carlo Gavazzi.
