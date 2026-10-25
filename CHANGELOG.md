# Changelog

## 1.3.0

- Each TCD line now has W, A, V and kWh sensors: a single-phase line gets all four for its phase; a 3-phase load gets A and V per phase plus one W and one kWh total. The voltage is the meter's own phase-to-neutral voltage (TCDs have no voltage register), shown per line without an extra read.
- Names are "<long name> W", "<long name> A", "<long name> V", "<long name> kWh" (A and V get " L1".." L3" on a 3-phase load). The short name is used as the label only when a line has no long name. Both are recorded as attributes (`line_name`, `short_name`, `tcd`, `phase`, `distribution_board`).
- New per-meter step for the distribution board (an existing device's name, or typed). It is not part of any sensor name; it starts the entity IDs, which are `sensor.<board>_<short name>_<w|a|v|kwh>` (`_l1`.. on a 3-phase load); without a short name the long name is used. IDs are chosen when a sensor is first created; Reconfigure renames a line sensor whose ID still matches what the previous layout produced (IDs you edited by hand are left alone).
- Sensors created by 1.2.0 get the new entity IDs automatically on upgrade (and on Reconfigure): their old, Home Assistant-generated IDs such as `sensor.em280_address_1_r1_power` become `sensor.<board or meter name>_r1_w`. IDs you changed yourself, or that are already taken, are kept. Dashboards, automations and the energy dashboard that use the old IDs need updating, and history starts afresh under the new ID.
- Line sensors are named exactly "<long name> W" etc., without the meter's device name in front.
- Once a meter has a wired TCD, its meter-wide sensors (V, A, W, kWh totals) are off by default. A meter with no TCD wired keeps them.
- Config entry version 4: existing installs get the new on/off state applied automatically (sensors you disabled yourself stay off).
- The polling options page shows how many sensors are enabled, how many Modbus reads a poll takes, and the shortest update interval that keeps up (from the last real poll, or a model of the bus before one has run).

## 1.2.0

- TCD naming page: each line now also has a short name (R1, W1, ...) that leads its sensor names ("R1 Power", "R1 Energy"), alongside the name or linked device.
- A single-phase line left completely empty is not connected: its sensors stay off and are not polled.
- A TCD can be skipped for now by leaving its naming page empty, and *Skip the rest* skips every TCD still waiting (for a gateway serving several boards you have not reached yet). Skipped TCDs have their sensors off.
- Reconfigure pre-fills the wiring mode, names, short names and linked devices from the previous setup, and keeps the stored answers for TCDs you skip.

## 1.1.4

- Two new setup steps after discovery (also on Reconfigure) for EM270/EM280 meters. First, for each TCD (TCDA1, TCDA2) choose *Not connected*, *One 3-phase load* or *Three single-phase lines*; EM280 meters that report "No TCD detected" are pre-set to Not connected. Second, name each line, or pick an existing Home Assistant device: the sensors are then attached to that device and named from it (a picked device overrides a typed name).
- The layout decides which TCD sensors are on: a 3-phase load enables Power and Energy (totals); each single-phase line enables its own Power and Energy; an empty single-phase line and a Not connected TCD stay off and are not polled. Sensors are renamed to match (for example "Oven Power", "Oven Energy"). Reconfigure re-applies this to existing TCD sensors, leaving ones you disabled yourself alone.
- Enabled by default for EM270/EM280: TCDA1 W L1-L3 and TCDA1 kWh L1-L3. These meters only report per-phase power and energy through the TCD A1 channel, so they are the per-phase watts and usage. (Sensors for TCDA2 and everything else stay disabled until you enable them.)
- Config entry version 3 migration: default sensors that 1.1.3 had disabled (the TCDA1 per-phase ones) are enabled again. Sensors you disabled yourself are left alone.

## 1.1.3

- Only volts, amps, watts and energy used are enabled by default; every other sensor (VA, VAR, power factor, demand, the TCD channels and the diagnostics) is created disabled and can be enabled from the entity settings.
- Disabled sensors are no longer polled. Each poll reads only the registers behind enabled entities, so a meter with the default set needs 3 reads (EM270/EM280) or 6 (EM24) instead of 24 or 16. Enabling an entity takes effect after Home Assistant's automatic reload.
- One-time migration (config entry version 2): sensors already created by earlier versions are disabled unless they are in the default set, so existing installs stop polling them too. Re-enable any you want afterwards.
- A no-response read (silent meter, or a gateway exception pymodbus discards) no longer closes a healthy Modbus TCP connection, so scans and polls reuse one socket instead of reconnecting for every silent address. RTU-over-TCP framing still reconnects to resync.

## 1.1.2

- Fixed leaked Modbus client connections: a disconnected client is now closed before a new one is created, and pymodbus auto-reconnect is disabled. The leak opened concurrent connections that a single-connection gateway (Techbase iMod) answered by closing every new socket.

## 1.1.1

- Fixed the discovery progress step raising `Show progress can only transition to show progress or show progress done` by finishing with `progress_done` before the summary form.

## 1.1.0

- Added EM24 (EM24DINAV) meter support with its own identification codes, full read-only register map, and signed 16-bit decoding.
- EM24 read blocks honour the 11-word protocol limit and skip the EM270/EM280 serial-number and secondary-address reads that EM24 does not provide.
- Replaced the non-renderable `progress_done` step with a "Discovery complete" summary form after the scan finishes, so the dialog shows the result and the flow can be submitted instead of leaking.
- Relaxed the pinned `pymodbus` requirement to `pymodbus>=3.11.2`.

## 1.0.0

- Clean repository rebuild replacing the earlier prototype history.
- Fixed the config-flow `400 Bad Request` caused by serializing a null unit into number selectors.
- Made package initialization independent of `pymodbus`, allowing Home Assistant to import and display the first config-flow form before any Modbus client is created.
- Added CI smoke tests that start the flow through Home Assistant’s real flow manager on Home Assistant 2026.2.3 and 2026.6.1.
- Added a retryable config-flow error path instead of aborting setup after a failed or empty discovery scan.
- Added automatic Modbus TCP versus RTU-over-TCP probing, three-pass slave discovery, and skip-on-found behaviour.
- Added one Home Assistant device per meter with serial number, model, model ID, and firmware device metadata.
- Added the complete documented read-only measurement and diagnostic register map.
- Added configurable polling, advanced communication settings, reconfiguration/rescan, options, diagnostics, HACS metadata, brand assets, and release automation.
