# Carlo Gavazzi EM - documentation

Everything about the integration, from the gateway on the wall to the code in the repository. The pages were written from the source of version **1.3.2**; where a number or behaviour is quoted, it is the one in the code (file names are given so you can check).

| Page | Read it when you want to... |
|---|---|
| [Installation](installation.md) | Install the integration with HACS or by hand, and update it. |
| [Setting up the gateway](gateway.md) | Prepare the RS-485 to Ethernet gateway, or replace a Techbase iMod gateway with the bundled read-only proxy. |
| [Adding the integration](setup.md) | Walk through every screen of the setup, Reconfigure and Configure dialogs, field by field. |
| [TCD lines, names and entity IDs](tcd-lines.md) | Understand how a TCD (current transformer module) is wired in Home Assistant, what gets named what, and which sensors are on. |
| [Sensor reference](sensors.md) | Look up every sensor, its register, scaling, unit and default state. |
| [How it works](architecture.md) | Understand the code: modules, discovery, polling, decoding, migrations and stored data. |
| [Troubleshooting](troubleshooting.md) | Fix "no meters found", unavailable sensors, slow polling, wrong entity IDs. |
| [Development](development.md) | Run the checks, change the code, cut a release. |
| [Screenshots](screenshots/README.md) | See which screenshots the pages expect and how to capture them. |

## What the integration is

A **local, read-only** Home Assistant integration for Carlo Gavazzi **EM270 X/W**, **EM280** and **EM24 (DIN)** energy meters on an RS-485 bus, reached through a **transparent Modbus RTU to Modbus TCP gateway**.

```text
meters (RS-485, Modbus RTU)  ->  gateway (serial -> TCP port 502)  ->  Home Assistant (this integration)
```

- One config entry per gateway (`host:port`); one Home Assistant device per meter found behind it.
- It only ever sends Modbus function 3 (read holding registers). There is no write, reset or programming code anywhere in the integration.
- Only the sensors you have enabled are read from the bus.
- For EM270/EM280 meters with TCD modules, you describe how each TCD is wired (one 3-phase load, or three single-phase lines), name the lines, and the integration creates W / A / V / kWh sensors per line with predictable entity IDs.

## A note about screenshots

The repository can not ship real screenshots yet: they have to be taken from a running Home Assistant with real meters, and none was available while this documentation was written. Rather than invent pictures, every dialog is described field by field (the field names are the exact labels from `strings.json`), and [screenshots/README.md](screenshots/README.md) lists each picture, its file name, and exactly what to capture. Add the PNGs to `docs/screenshots/` and the markers in the pages are ready to be replaced with image links.
