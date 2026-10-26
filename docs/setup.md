# Adding the integration

Open **Settings -> Devices & services -> Add integration -> Carlo Gavazzi EM**. The dialog is a sequence of steps. This page follows them in order and lists every field exactly as it is labelled in Home Assistant. (Labels come from `custom_components/carlo_gavazzi_em/strings.json`.)

```text
Add Modbus gateway
   |-- Show advanced settings?  --> Advanced gateway settings
   |-- Limit discovery?         --> Modbus address range
   v
Scanning (progress)
   v
How are the TCDs wired?   (only if an EM270/EM280 was found)
   v
Distribution board for <meter>      (once per meter that has a TCD in use)
   v
Name the <TCD> line(s) on <meter>   (once per TCD in use)
   v
Entry created
```

_Screenshot marker for each step: `02-add-gateway.png`, `03-advanced.png`, `04-scan-range.png`, `05-scanning.png`, `06-tcd-layout.png`, `07-board.png`, `08-names-3phase.png`, `09-names-1phase.png`._

## Step 1 - Add Modbus gateway

| Field | Meaning | Default / range |
|---|---|---|
| **Gateway host or IP address** | Address of the gateway. Stored trimmed and lower-case. | required |
| **TCP port** | Gateway TCP port. | `502`, 1-65535 |
| **Update interval** | Seconds between polls. | `10`, 5-3600 s |
| **Show advanced settings** | Show step 2 next. | off |
| **Limit discovery to an address range** | Show step 3 next. | off |

The gateway is identified as `host:port`. Adding a second entry with the same host and port is refused with *This gateway is already configured.*

Pick the update interval once you know how many sensors are on: **Configure** later shows the shortest interval that keeps up (see [Choosing the update interval](#choosing-the-update-interval)).

## Step 2 - Advanced gateway settings (only if ticked)

| Field | Meaning | Default / range |
|---|---|---|
| **Request timeout** | How long to wait for each Modbus reply. | `0.75` s, 0.1-10 in steps of 0.05 |
| **Polling retries after the first attempt** | Extra attempts when a poll read fails. | `2`, 0-5 |
| **Delay between requests** | Pause after every read, to give the gateway and bus time. | `10` ms, 0-500 |
| **TCP framing** | **Auto detect**, **Modbus TCP**, or **RTU over TCP**. | Auto detect |

*Auto detect* chooses the framing during the scan (see below). Pick a fixed mode only if auto detection fails or you want to be explicit. These settings do not change the gateway; the gateway's baud rate and parity must already match the meters.

## Step 3 - Modbus address range (only if ticked)

| Field | Meaning | Default / range |
|---|---|---|
| **First slave address** | | `1`, 1-247 |
| **Last slave address** | | `247`, 1-247 |

If the first address is greater than the last you get *The first slave address must be less than or equal to the last slave address.* Restricting the range makes setup much faster, because every empty address costs a timeout.

## Step 4 - Scanning

A progress dialog shows *Scanning pass N/3, address A, using <framing>. Compatible meters found: F.* What happens (`api.py`, `async_discover_meters`):

1. The integration connects to the gateway. If it can not: *Could not communicate with the gateway...* and you are returned to step 1 with your values.
2. It makes **three passes** over the address range. Passes 2 and 3 skip addresses already found.
3. For each address it reads the **identification register `0x000B`** once. A reply counts only if the value is a known model code (EM270/EM280: 270-273, 280-283; EM24: 45-48).
4. **Framing** (Auto detect only): pass 1 uses Modbus TCP, pass 2 uses RTU over TCP, pass 3 uses Modbus TCP. As soon as one meter answers, that framing is kept for the rest of the scan and stored as the detected framing. A fixed framing is used throughout.
5. For every meter found it reads the firmware version/revision (`0x0302`, `0x0303`, one word each), and for EM270/EM280 the serial number and production year (`0x5000`, 8 words) and secondary address (`0x5100`). EM24 has none of these.

If nothing answers: *The gateway responded, but no compatible EM270, EM280, or EM24 meters were found. Check the RS485 settings, wiring, and slave-address range.* and you are returned to step 1.

### What gets stored about each meter

| Item | Value |
|---|---|
| Model name | From the identification code (and for EM24 / EM270 the firmware version code), e.g. `EM28072DMV53X2SX`, `EM24DINAV53DISX`, or `EM27072DMV53X2SX`/`...SW`; shown as `X/W` if it can not be told apart. |
| Firmware | EM270/EM280: `r.` + letter + revision (version code 0 = `A`; lower-case for EM270 X), e.g. `r.A3`. EM24: `r.<revision>`. |
| Device identifier | `serial:<serial number>` when a serial number was read, otherwise `gateway:<host>:<port>:slave:<address>` (always the latter on EM24). |
| Default device name | `<model> (address <slave id>)`. |

The serial number, model, model ID and firmware are shown as **device information**, not as sensors.

## Step 5 - How are the TCDs wired?

Shown when at least one EM270/EM280 meter was found (an EM24-only gateway skips straight to creating the entry). There is **one drop-down per meter per TCD channel**, labelled `<meter name> - TCDA1` and `<meter name> - TCDA2`:

| Option | Use it when |
|---|---|
| **Not connected** | That TCD is not fitted. Its sensors are switched off and not polled. |
| **One 3-phase load** | The TCD's three current inputs measure one three-phase load (a 3-phase motor, a whole board). You get one W and one kWh total. |
| **Three single-phase lines** | The three inputs measure three separate single-phase circuits. You get W and kWh per line. |

Pre-selection: on a first setup an **EM280** is pre-set from its CT-primary registers (`0x1003`/`0x1004`; value 4 = "No TCD detected" gives *Not connected*, anything else gives *One 3-phase load*). Other EM270 models can not report it, so TCDA1 is pre-set to *One 3-phase load* and TCDA2 to *Not connected*. On Reconfigure, the saved answer always wins.

Full detail of what each choice does is in [tcd-lines.md](tcd-lines.md).

## Step 6 - Distribution board for `<meter>`

Asked **once per meter** that has at least one TCD in use, before its first TCD is named.

| Field | Meaning |
|---|---|
| **Distribution board name** | Free text, e.g. `DB1`. |
| **Or take the name from a device** | Pick an existing Home Assistant device; its name (your custom name if set) is used instead of the typed text. |

The board **starts every line sensor's entity ID** (for example `sensor.db1_r1_w`) and is recorded on the sensor as the `distribution_board` attribute. It is **not** part of any sensor name. Leave both empty to use the meter's own device name in the entity IDs.

## Step 7 - Name the `<TCD>` line(s) on `<meter>`

One page per TCD in use. A 3-phase load has one set of fields; three single-phase lines have three sets (`Line 1`..`Line 3`).

| Field | Meaning |
|---|---|
| **Name** / **Line N name** | The long name, e.g. `Oven`. Used in the sensor names: `Oven W`, `Oven kWh`... |
| **Short name (e.g. R1)** / **Line N short name** | Used in the entity ID, and as the label when there is no long name. |
| **Or link to device** / **Line N - or link to device** | Pick an existing device: the line's sensors are attached to that device and its name is used as the long name (overriding anything typed). |
| **Skip the rest (set up later)** | Skip this TCD and every TCD still waiting. |

Rules:

- A single-phase line with **all three fields empty** is *not connected*: its sensors stay off.
- Submitting a page with **everything empty** sets that TCD up later (sensors off). **Skip the rest** does the same for every TCD still to come, which is useful when one gateway serves several boards and you have not reached the others yet.
- If a line has neither a long name nor a short name, its sensors stay off.

When the last page is submitted the entry **Carlo Gavazzi EM Gateway `<host>`** is created and the sensors appear.

## Reconfigure

**Settings -> Devices & services -> Carlo Gavazzi EM -> three-dot menu -> Reconfigure.**

It re-runs steps 1-7: you can change the gateway address, framing and scan range, rescan the bus for meters, and change the wiring, names, short names, boards and linked devices. Every field is **pre-filled from what you saved**; for TCDs you skip with *Skip the rest*, the saved answers are kept.

On finishing:

- The stored meters, layout and settings are replaced and the integration reloads.
- Sensors that already exist are brought in line with the new layout: switched on or off, and **renamed** to the new entity ID *if* their current ID is one the integration generated (the one the previous layout produced, or the one 1.2.0 produced). An entity ID you changed by hand, or whose new ID is already taken, is left alone. A sensor you disabled yourself is never switched back on, but **TCD sensors and default meter-wide sensors that the layout says should be off are switched off again, even if you had enabled them by hand** (for example line A and V sensors): enable them again afterwards. See [tcd-lines.md](tcd-lines.md#when-entity-ids-change).
- Values you set under **Configure** are carried into the entry (the options are then cleared).
- Changing the host/port changes the entry's unique ID. If another entry already has the new host and port, Reconfigure stops with *This gateway is already configured.*
- Devices of meters that are no longer found are not removed automatically; delete them from their device page.

## Configure (polling options)

**Settings -> Devices & services -> Carlo Gavazzi EM -> Configure.** This changes polling without rescanning, and reloads the integration when saved.

| Field | Default / range |
|---|---|
| **Update interval** | 5-3600 s |
| **Show advanced polling settings** | off; if ticked, a second page asks for **Request timeout**, **Retries after the first attempt**, **Delay between requests** (same ranges as above) |

The description at the top shows the current load: *`{entities}` sensors are enabled, which takes `{reads}` Modbus reads per poll (about `{seconds}` s on the bus). Recommended update interval ...: `{recommended}` s.* Options set here are stored as entry options and override the values from setup.

## Choosing the update interval

The bus is shared and every read is a separate request, so a poll takes roughly the sum of its reads. The recommended interval is the shortest one that does not make polls overlap:

```text
per read  = (13 + 2 x registers) x 11 / 9600  s   (frame time at 9600 baud)
          + 0.06 s                               (meter turnaround, gateway, network)
          + delay between requests               (default 0.010 s)
poll time = sum over all reads       (replaced by the last measured poll once one has run)
recommended = max(5, ceil(poll time x 1.25))      seconds
```

The 5 s minimum is the integration's lower limit. Examples from the model (defaults, 9600 baud, one EM280 unless noted):

| Sensors on | Reads | Modelled poll | Recommended |
|---|---:|---:|---:|
| Default set, no TCD wired (14 sensors) | 5 | 0.49 s | 5 s |
| One 3-phase TCD (W and kWh totals) | 2 | 0.18 s | 5 s |
| Three single-phase lines on TCDA1 | 2 | 0.20 s | 5 s |
| 3-phase on TCDA1 + three single-phase on TCDA2 | 4 | 0.38 s | 5 s |
| EM24 default set (12 sensors) | 6 | 0.56 s | 5 s |

So with a few sensors per meter the minimum, 5 s, is usually the answer; the figure grows as you enable more sensors or add meters on the same bus. The model is only a guide before the first poll; afterwards the measured time of the last poll is used.

## Turning sensors on and off

Disabled sensors are created but **not polled**. To change one: **Settings -> Devices & services -> Entities ->** the sensor **-> Settings -> Enabled**. Home Assistant reloads the integration shortly afterwards and the register is read (or no longer read) from then on. A sensor that is enabled but whose register the meter does not support shows **unavailable** rather than a wrong value.

## Diagnostics

On the integration entry, **Download diagnostics** gives a JSON file with the entry settings (without the meter list), the meter list, the last update status and the last values per slave. The gateway host and each meter's serial number and device identifier are redacted. **The saved TCD layout (line names, short names, board names and linked device ids) is included as-is**, so review it before posting a file publicly.
