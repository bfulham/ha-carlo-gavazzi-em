# Changelog

## 1.1.4

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
