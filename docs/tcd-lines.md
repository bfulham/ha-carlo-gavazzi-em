# TCD lines, names and entity IDs

## What a TCD is

An EM270/EM280 has no direct current inputs for the loads you usually care about. Instead, up to two **TCD** (current transformer) modules, **TCDA1** and **TCDA2**, plug into it. Each TCD has three current inputs (L1, L2, L3) and the meter reports current, power and energy **per input**. What those three inputs measure is up to the installer:

- **One 3-phase load** - the three inputs are the three phases of one load (a 3-phase motor, a whole distribution board). The useful numbers are the totals.
- **Three single-phase lines** - the three inputs are three separate single-phase circuits (for example the red, white and blue phases feeding three different things). Each input is its own line.

The meter can not tell which of these you have, so you tell the integration during setup ([setup.md](setup.md#step-5---how-are-the-tcds-wired)). From that answer, plus a name for each line and a distribution board, it decides which sensors are on, what they are called, and what their entity IDs are.

_Screenshot marker: `10-tcd-sensors.png` (the device page showing the named line sensors)._

## What the integration creates for a line

For every line the integration creates four sensors. **Two are on by default**; the other two exist but are off until you enable them.

| Sensor | Wired as one 3-phase load | Wired as three single-phase lines | On by default |
|---|---|---|---|
| **W** (active power) | one total for the load | one per line | **yes** |
| **kWh** (energy) | one total for the load | one per line | **yes** |
| **A** (current) | one per phase (`L1`, `L2`, `L3`) | one per line | no |
| **V** (voltage) | one per phase (`L1`, `L2`, `L3`) | one per line | no |

Notes:

- **W** and **kWh** come from the TCD's own registers (for TCDA1: `0x0112`-`0x0117` per-phase W, `0x0118` total W, `0x012A`-`0x012F` per-phase kWh, `0x011E` total kWh; TCDA2 is the same at `0x02xx`). The full list is in [sensors.md](sensors.md).
- **A** is the TCD's own per-input current (`0x010C`-`0x0111`).
- **V** is the **meter's own phase-to-neutral voltage** for that phase (L1-N, L2-N, L3-N). A TCD has no voltage input and no voltage register; the sensor is an alias of the meter's `V L1-N` ... `V L3-N`, so enabling it adds **no extra Modbus read** if the meter's voltage is read anyway.
- Everything else a TCD reports (VA, VAR, power factor, demand, maximum demand, ...) is created but **off**. Those sensors also take the line's name (`Pump PF`, `Oven VA`, `Oven W L1`, `Oven kWh L1`; a 3-phase load names its per-phase values with `L1`..`L3`). Only the totals across three *separate* single-phase lines (for example `TCDA2 W Total`) keep their stock name, on the meter's device, because they add unrelated lines together.
- A **Not connected** TCD, an unnamed line (no long name and no short name) or a single-phase line left empty has all its sensors off and not polled.

## Which meter-wide sensors stay on

A meter that has **at least one TCD with a mode other than "Not connected"** (even if its lines have no names yet) has its meter-wide sensors switched **off** by default: `V L1-N`..`V L3-N`, `A L1 Σ`..`A L3 Σ`, `W Σ` and `kWh Import Total`. They only add up unrelated lines. You can still enable any of them.

A meter with **no TCD wired** keeps the original defaults (the meter-wide voltage, current, W Σ and kWh import, plus TCDA1 per-phase W and kWh).

## Names

The name of a line sensor is

```text
<long name> <metric>            e.g.  Oven W      Oven kWh      Pump A      Pump V
```

- If the line has **no long name**, the **short name** is used in its place (`R1 W`).
- On a **3-phase load**, the per-phase sensors get the phase appended: `Oven A L1`, `Oven A L2`, `Oven A L3`, `Oven V L1`, ... (and the off-by-default per-phase `Oven W L1`, `Oven kWh L1`). The W and kWh totals that are on by default carry no phase: `Oven W`, `Oven kWh`.
- The **distribution board is never part of a name**. The meter's device keeps its default name (`<model> (address N)`).
- If you **link a line to a device**, the device's name (your custom name if you set one) is used as the long name, and the sensors are shown under that device instead of under the meter. The name is copied when you set it up; it does not follow later renames of that device (run Reconfigure to refresh it). If the linked device is later deleted, its sensors fall back to the meter's device.

### Attributes

Every line sensor records how it was set up as state attributes:

| Attribute | Value |
|---|---|
| `line_name` | The long name (or the linked device's name), or empty. |
| `short_name` | The short name, or empty. |
| `tcd` | `TCDA1` or `TCDA2`. |
| `phase` | `L1`, `L2` or `L3`; empty for the totals of a 3-phase load. |
| `distribution_board` | The board name, or empty. |

## Entity IDs

```text
sensor.<board>_<short name>_<w|a|v|kwh>[_l1|_l2|_l3]
```

- `<board>` is the distribution board name; if there is none, the **meter's device name** (for example `em28072dmv53x2sx_address_1`).
- `<short name>` is the short name; **if there is no short name, the long name is used instead.**
- The last part is the metric: `w`, `a`, `v` or `kwh` (other metrics use their own name, e.g. `pf`, `w_dmd`). `_l1`..`_l3` is added to the per-phase sensors of a **3-phase load** (`..._a_l1`, `..._v_l1`, `..._w_l1`, `..._kwh_l1`); the on-by-default totals and everything on single-phase lines have no suffix.
- The whole thing is run through Home Assistant's slugify (lower case, spaces and punctuation become `_`).
- If the ID is already taken (two lines on one board with the same short name), Home Assistant adds `_2`, `_3`, ... so give each line on a board a different short name.

### Worked example

Board `DB1`. TCDA1 wired as **one 3-phase load** named `Oven`, short name `R1`. TCDA2 wired as **three single-phase lines**: `Pump` (`R2`), `Lights` (`W2`), `Fan` (`B2`).

| Entity ID | Name | On by default |
|---|---|---|
| `sensor.db1_r1_w` | Oven W | yes |
| `sensor.db1_r1_kwh` | Oven kWh | yes |
| `sensor.db1_r1_a_l1` / `_l2` / `_l3` | Oven A L1 / L2 / L3 | no |
| `sensor.db1_r1_v_l1` / `_l2` / `_l3` | Oven V L1 / L2 / L3 | no |
| `sensor.db1_r2_w` | Pump W | yes |
| `sensor.db1_r2_kwh` | Pump kWh | yes |
| `sensor.db1_r2_a` | Pump A | no |
| `sensor.db1_r2_v` | Pump V | no |
| `sensor.db1_w2_w`, `sensor.db1_w2_kwh`, `..._a`, `..._v` | Lights W, kWh, A, V | W and kWh |
| `sensor.db1_b2_w`, `sensor.db1_b2_kwh`, `..._a`, `..._v` | Fan W, kWh, A, V | W and kWh |

With no board entered, `db1` would be the meter's device name, e.g. `sensor.em28072dmv53x2sx_address_1_r1_w`.

Entity IDs are chosen **when a sensor is first created**. Later changes are applied only as described next.

## When entity IDs change

Home Assistant never renames an entity ID on its own, so the integration does it on **Reconfigure** (and once on upgrade from 1.2.0), under strict rules (`layout_sync.py`). A sensor is renamed to the ID the new layout produces only if **all** of these hold:

1. Its current ID (ignoring a trailing `_2`, `_3`) is one the integration itself generated: either the ID the **previous layout** gave it, or the ID **version 1.2.0** gave it (built from the device name and the 1.2.0 sensor name, for example `sensor.em280_address_1_r1_power`).
2. The ID it would be renamed to is not already used by another entity.

An ID you changed yourself is left alone, as is one whose new ID is taken. A sensor you disabled yourself is never re-enabled. The reverse is not true: each Reconfigure (and the upgrade migrations) switches off any TCD sensor or default meter-wide sensor that the layout says should be off, **including one you enabled by hand**, so re-enable your A and V sensors after a Reconfigure. Names (the friendly name) follow the layout unless you set your own name in Home Assistant.

Renaming an entity ID has consequences you should plan for:

- Dashboards, automations, scripts and the **Energy dashboard** that refer to the old ID must be updated.
- Long-term statistics and history continue under the old ID; the new ID starts a new history. (Home Assistant can link them in **Settings -> Developer tools -> Statistics** if you need that.)

## Upgrading from 1.2.0 or earlier

On the first start of 1.3.x the stored configuration is migrated once (see [architecture.md](architecture.md#migrations)): the new defaults are applied to the sensors that already exist (W and kWh on, line A and V off, meter-wide sensors off on wired meters) and the 1.2.0-style entity IDs are replaced by the new scheme, following the rules above. Sensors you disabled yourself stay off.
