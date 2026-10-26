# Installation

## Requirements

| | |
|---|---|
| Home Assistant | **2026.2.3** or newer (`hacs.json`). CI also tests 2026.6.1. |
| Python library | `pymodbus>=3.11.2` (`manifest.json`). Home Assistant installs it for you. |
| Network | The gateway's TCP port (normally 502) must be reachable from Home Assistant. |
| Gateway | A *transparent* RTU to TCP gateway whose serial side already matches the meters (see [gateway.md](gateway.md)). |
| Meters | EM270 X, EM270 W, EM280 or EM24 DIN, each with a unique Modbus address on the bus. |

## With HACS (recommended)

1. Open **HACS -> Integrations**.
2. Open the three-dot menu and choose **Custom repositories**.
3. Add `https://github.com/bfulham/ha-carlo-gavazzi-em` as an **Integration** repository.
4. Install **Carlo Gavazzi EM**.
5. **Restart Home Assistant.**
6. Go to **Settings -> Devices & services -> Add integration** and search for **Carlo Gavazzi EM**.

_Screenshot marker: `01-add-integration.png` (the integration in the Add integration list)._

## Manually

Copy the folder

```text
custom_components/carlo_gavazzi_em
```

from this repository to

```text
/config/custom_components/carlo_gavazzi_em
```

and restart Home Assistant before opening the config flow. Check that `/config/custom_components/carlo_gavazzi_em/manifest.json` shows the version you expect.

A release ZIP (`carlo_gavazzi_em.zip`, with `SHA256SUMS.txt`) is attached to every GitHub release if you prefer to unpack it yourself.

## Updating

1. Update through HACS (or replace the folder).
2. **Restart Home Assistant.**
3. On the first start of a new version the integration may run a one-time *migration* of its stored data (the config entry "version"). What each one does is listed in [architecture.md](architecture.md#migrations). Read the [changelog](../CHANGELOG.md) before updating across a minor version: 1.3.0 changed entity IDs and defaults for TCD lines.

If sensors show *unavailable* after an update, download the log and diagnostics (see [troubleshooting.md](troubleshooting.md)).

## Removing

Delete the integration entry under **Settings -> Devices & services**, then remove it in HACS (or delete the folder). Entities and devices created by the integration are removed with the entry. The gateway and meters are never changed by the integration, so there is nothing to undo on the hardware.
