# Screenshots

No screenshots are included yet. They have to come from a running Home Assistant connected to real meters, and none was available when the documentation was written; inventing pictures would defeat the purpose. The pages describe every dialog in words, with the exact field labels, and mark where a picture belongs with `Screenshot marker: <file>`.

## How to add them

1. Take the screenshot in Home Assistant (light theme, browser zoom 100 %, crop to the dialog or panel).
2. Save it here with the file name below (PNG, under ~300 kB).
3. In the page, replace the marker line with `![description](screenshots/<file>)` (for pages in `docs/`).

Blur or crop anything private: the gateway IP address, serial numbers, and real customer or site names.

## Shot list

| File | Page | What to capture |
|---|---|---|
| `01-add-integration.png` | installation | **Settings -> Devices & services -> Add integration** with *Carlo Gavazzi EM* in the search results. |
| `02-add-gateway.png` | setup | Step 1 form (*Add Modbus gateway*) with the five fields. |
| `03-advanced.png` | setup | *Advanced gateway settings* form. |
| `04-scan-range.png` | setup | *Modbus address range* form. |
| `05-scanning.png` | setup | The progress dialog mid-scan (shows pass, address, framing, meters found). |
| `06-tcd-layout.png` | setup | *How are the TCDs wired?* with the drop-down open, showing the three options. |
| `07-board.png` | setup | *Distribution board for ...* form. |
| `08-names-3phase.png` | setup | *Name the TCDA1 line(s) ...* for a 3-phase load (one set of fields plus *Skip the rest*). |
| `09-names-1phase.png` | setup | The same page for three single-phase lines (three sets of fields). |
| `10-tcd-sensors.png` | tcd-lines | The device page of a meter (or the linked device) showing the named line sensors, e.g. *Oven W*, *Oven kWh*. |
| `11-entity-attributes.png` | tcd-lines | A line sensor's *Attributes* section (`line_name`, `short_name`, `tcd`, `phase`, `distribution_board`). |
| `12-configure.png` | setup | The *Polling options* dialog with the recommended update interval text. |
| `13-entities-disabled.png` | setup | The device's entity list with some sensors disabled, and the entity settings *Enabled* toggle. |
| `14-diagnostics.png` | troubleshooting | The *Download diagnostics* entry on the integration page. |
