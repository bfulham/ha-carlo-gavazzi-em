# Sensor reference

Every sensor the integration can create, generated from the register map in `custom_components/carlo_gavazzi_em/registers.py` (version 1.3.2). All registers are read with Modbus function 3 (holding registers) as one or two 16-bit words.

## Reading the tables

| Column | Meaning |
|---|---|
| Key | The sensor's internal key. The entity's unique ID is `<device identifier>_<key>`. |
| Register | Modbus address of the first word (hexadecimal). |
| Words | 1 or 2 registers. A 2-word value is **32-bit, least significant word first** (LSW, then MSW). |
| Decoding | `signed`/`unsigned` integer, then `÷ N`: the raw integer is divided by N to get the value in the unit. |
| Default | State of the sensor **as created on a meter with no TCD wired**. On a meter with TCDs wired, the [TCD rules](tcd-lines.md) replace this for the meter-wide and TCD sensors. `off` sensors are created but **not polled**. |
| _(diagnostic)_ | Shown under *Diagnostic* on the device page. |

State classes are `measurement` for instantaneous values and `total_increasing` for energy counters, so the sensors work with Home Assistant statistics and the Energy dashboard.

## Values that read as unavailable

A sensor shows **unavailable** (never a wrong number) when:

- the meter did not answer the read, or the whole poll failed;
- a 32-bit value is the "missing" marker: LSW `0xFFFF` with MSW `0x7FFD` (not managed), `0x7FFE` (no TCD) or `0x7FFF` (overflow);
- a 16-bit unsigned value is `0xFFFF`;
- a voltage is above 5000 V after scaling (treated as invalid).

This is how a TCD that is not fitted, or a quantity your measuring system does not provide, shows up.

## Configuration values with names

Some diagnostic sensors show text instead of a number:

| Sensor | Mapping |
|---|---|
| `measuring_system` (EM270/EM280) | 0 `3P 1.3P`, 1 `3P 2.3P`, 2 `3P 3.1P`, 3 `3P 6.1P`, 4 `1P 3.1P`, 5 `1P 6.1P` |
| `measuring_system` (EM24) | 0 `3Pn`, 1 `3P1`, 2 `2P`, 3 `1P` |
| `ct_primary`, `ct_primary_2` (EM270) | 0 `160 A`, 1 `250 A`, 2 `630 A`, 3 `65 A / no TCD detected (model dependent)`, 4 `No TCD detected` |
| `ct_primary`, `ct_primary_2` (EM280) | 0 `TCD06B`, 1 `TCD06S`, 4 `No TCD detected` |
| `sum_virtual` (EM270) | 0 `Disabled / virtual disabled`, 1 `SUM enabled`, 2 `DIF enabled` |
| `sum_virtual` (EM280) | 0 `Disabled`, 1 `Enabled` |
| `ton_time` | 0 `40 ms`, 1 `100 ms` |
| `ec_mode` | 0 `Enabled`, 1 `Disabled` |
| `tcd_phase_order_a1`, `_a2` | 0 `123`, 1 `321` |
| `rs485_baud` (EM270/EM280) | 0 `9600`, 1 `19200`, 2 `38400` |
| `rs485_baud` (EM24) | 0 `9600`, 1 `4800` |
| `rs485_parity` | 0 `None`, 1 `Even` |
| `keypad_lock` (EM270/EM280) | 0 `Unlocked`, 1 `Locked` |
| `keypad_lock` (EM24) | 0, 1, 2 `Unlocked`; 3 `Locked` |
| `current_tariff` (EM24) | 0-3 `Tariff 1`-`Tariff 4` |

A value with no mapping is shown as its number.

## Terms

- **Σ** - the meter-wide (system) value, from the meter's own measuring inputs.
- **TCDA1 / TCDA2** - values from the two TCD current-transformer modules; see [tcd-lines.md](tcd-lines.md).
- **DMD** - demand: the average over the demand integration time (`dmd_integration_time`). **MAXDMD** - the highest demand recorded.
- **W / VA / var** - active / apparent / reactive power. **kWh / kvarh** - active / reactive energy. **PF** - power factor.

## EM270 / EM280 (105 sensors)

| Key | Name | Register | Words | Decoding | Unit | Default | Meaning |
|---|---|---|---:|---|---|---|---|
| `v_l1_n` | V L1-N | `0x0000` | 2 | unsigned ÷ 10 | V | on | Voltage between phase L1 and neutral. |
| `v_l2_n` | V L2-N | `0x0002` | 2 | unsigned ÷ 10 | V | on | Voltage between phase L2 and neutral. |
| `v_l3_n` | V L3-N | `0x0004` | 2 | unsigned ÷ 10 | V | on | Voltage between phase L3 and neutral. |
| `v_l1_l2` | V L1-L2 | `0x0006` | 2 | unsigned ÷ 10 | V | off | Line-to-line voltage L1 to L2. |
| `v_l2_l3` | V L2-L3 | `0x0008` | 2 | unsigned ÷ 10 | V | off | Line-to-line voltage L2 to L3. |
| `v_l3_l1` | V L3-L1 | `0x000A` | 2 | unsigned ÷ 10 | V | off | Line-to-line voltage L3 to L1. |
| `a_l1_sum` | A L1 Σ | `0x000C` | 2 | unsigned ÷ 1000 | A | on | Current on phase L1 at the meter's own measuring inputs (the whole supply, not one TCD line). |
| `a_l2_sum` | A L2 Σ | `0x000E` | 2 | unsigned ÷ 1000 | A | on | Current on phase L2 at the meter's own measuring inputs. |
| `a_l3_sum` | A L3 Σ | `0x0010` | 2 | unsigned ÷ 1000 | A | on | Current on phase L3 at the meter's own measuring inputs. |
| `w_sum` | W Σ | `0x0012` | 2 | signed ÷ 10 | W | on | Total active power across all phases (negative = export). |
| `va_sum` | VA Σ | `0x0014` | 2 | unsigned ÷ 10 | VA | off | Total apparent power. |
| `var_sum` | VAR Σ | `0x0016` | 2 | signed ÷ 10 | var | off | Total reactive power. |
| `kwh_import_total` | kWh Import Total | `0x0018` | 2 | unsigned ÷ 10 | kWh | on | Total imported active energy (always rising). |
| `kvarh_import_total` | kvarh Import Total | `0x001A` | 2 | unsigned ÷ 10 | kvarh | off | Total imported reactive energy. |
| `w_dmd_sum` | W DMD Σ | `0x001C` | 2 | signed ÷ 10 | W | off | Average total active power over the demand integration time. |
| `va_dmd_sum` | VA DMD Σ | `0x001E` | 2 | unsigned ÷ 10 | VA | off | Average total apparent power over the demand integration time. |
| `w_maxdmd_sum` | W MAXDMD Σ | `0x0020` | 2 | signed ÷ 10 | W | off | Highest W demand recorded. |
| `va_maxdmd_sum` | VA MAXDMD Σ | `0x0022` | 2 | unsigned ÷ 10 | VA | off | Highest VA demand recorded. |
| `pf_sum` | PF Σ | `0x0024` | 2 | signed ÷ 1000 |  | off | Total power factor. |
| `tcda1_a_l1` | TCDA1 A L1 | `0x010C` | 2 | unsigned ÷ 1000 | A | off | Current measured by TCDA1 phase L1. |
| `tcda1_a_l2` | TCDA1 A L2 | `0x010E` | 2 | unsigned ÷ 1000 | A | off | Current measured by TCDA1 phase L2. |
| `tcda1_a_l3` | TCDA1 A L3 | `0x0110` | 2 | unsigned ÷ 1000 | A | off | Current measured by TCDA1 phase L3. |
| `tcda1_w_l1` | TCDA1 W L1 | `0x0112` | 2 | signed ÷ 10 | W | on | Active power measured by TCDA1 phase L1. |
| `tcda1_w_l2` | TCDA1 W L2 | `0x0114` | 2 | signed ÷ 10 | W | on | Active power measured by TCDA1 phase L2. |
| `tcda1_w_l3` | TCDA1 W L3 | `0x0116` | 2 | signed ÷ 10 | W | on | Active power measured by TCDA1 phase L3. |
| `tcda1_w_total` | TCDA1 W Total | `0x0118` | 2 | signed ÷ 10 | W | off | Active power measured by TCDA1 total. |
| `tcda1_va_total` | TCDA1 VA Total | `0x011A` | 2 | unsigned ÷ 10 | VA | off | Apparent power measured by TCDA1 total. |
| `tcda1_var_total` | TCDA1 VAR Total | `0x011C` | 2 | signed ÷ 10 | var | off | Reactive power measured by TCDA1 total. |
| `tcda1_kwh_total` | TCDA1 kWh Total | `0x011E` | 2 | unsigned ÷ 10 | kWh | off | Active energy measured by TCDA1 total. |
| `tcda1_kvarh_total` | TCDA1 kvarh Total | `0x0120` | 2 | unsigned ÷ 10 | kvarh | off | Reactive energy measured by TCDA1 total. |
| `tcda1_w_dmd_total` | TCDA1 W DMD Total | `0x0122` | 2 | signed ÷ 10 | W | off | Active power demand (average over the integration time) on TCDA1 total. |
| `tcda1_va_dmd_total` | TCDA1 VA DMD Total | `0x0124` | 2 | unsigned ÷ 10 | VA | off | Apparent power demand (average over the integration time) on TCDA1 total. |
| `tcda1_w_maxdmd_total` | TCDA1 W MAXDMD Total | `0x0126` | 2 | signed ÷ 10 | W | off | Highest active power demand recorded on TCDA1 total. |
| `tcda1_va_maxdmd_total` | TCDA1 VA MAXDMD Total | `0x0128` | 2 | unsigned ÷ 10 | VA | off | Highest apparent power demand recorded on TCDA1 total. |
| `tcda1_kwh_l1` | TCDA1 kWh L1 | `0x012A` | 2 | unsigned ÷ 10 | kWh | on | Active energy measured by TCDA1 phase L1. |
| `tcda1_kwh_l2` | TCDA1 kWh L2 | `0x012C` | 2 | unsigned ÷ 10 | kWh | on | Active energy measured by TCDA1 phase L2. |
| `tcda1_kwh_l3` | TCDA1 kWh L3 | `0x012E` | 2 | unsigned ÷ 10 | kWh | on | Active energy measured by TCDA1 phase L3. |
| `tcda1_w_dmd_l1` | TCDA1 W DMD L1 | `0x0130` | 2 | signed ÷ 10 | W | off | Active power demand (average over the integration time) on TCDA1 phase L1. |
| `tcda1_w_dmd_l2` | TCDA1 W DMD L2 | `0x0132` | 2 | signed ÷ 10 | W | off | Active power demand (average over the integration time) on TCDA1 phase L2. |
| `tcda1_w_dmd_l3` | TCDA1 W DMD L3 | `0x0134` | 2 | signed ÷ 10 | W | off | Active power demand (average over the integration time) on TCDA1 phase L3. |
| `tcda1_w_maxdmd_l1` | TCDA1 W MAXDMD L1 | `0x0136` | 2 | signed ÷ 10 | W | off | Highest active power demand recorded on TCDA1 phase L1. |
| `tcda1_w_maxdmd_l2` | TCDA1 W MAXDMD L2 | `0x0138` | 2 | signed ÷ 10 | W | off | Highest active power demand recorded on TCDA1 phase L2. |
| `tcda1_w_maxdmd_l3` | TCDA1 W MAXDMD L3 | `0x013A` | 2 | signed ÷ 10 | W | off | Highest active power demand recorded on TCDA1 phase L3. |
| `tcda1_var_l1` | TCDA1 VAR L1 | `0x013C` | 2 | signed ÷ 10 | var | off | Reactive power measured by TCDA1 phase L1. |
| `tcda1_var_l2` | TCDA1 VAR L2 | `0x013E` | 2 | signed ÷ 10 | var | off | Reactive power measured by TCDA1 phase L2. |
| `tcda1_var_l3` | TCDA1 VAR L3 | `0x0140` | 2 | signed ÷ 10 | var | off | Reactive power measured by TCDA1 phase L3. |
| `tcda1_pf_l1` | TCDA1 PF L1 | `0x0142` | 2 | signed ÷ 1000 |  | off | Power factor measured by TCDA1 phase L1. |
| `tcda1_pf_l2` | TCDA1 PF L2 | `0x0144` | 2 | signed ÷ 1000 |  | off | Power factor measured by TCDA1 phase L2. |
| `tcda1_pf_l3` | TCDA1 PF L3 | `0x0146` | 2 | signed ÷ 1000 |  | off | Power factor measured by TCDA1 phase L3. |
| `tcda1_pf_total` | TCDA1 PF Total | `0x0148` | 2 | signed ÷ 1000 |  | off | Power factor measured by TCDA1 total. |
| `tcda2_a_l1` | TCDA2 A L1 | `0x020C` | 2 | unsigned ÷ 1000 | A | off | Current measured by TCDA2 phase L1. |
| `tcda2_a_l2` | TCDA2 A L2 | `0x020E` | 2 | unsigned ÷ 1000 | A | off | Current measured by TCDA2 phase L2. |
| `tcda2_a_l3` | TCDA2 A L3 | `0x0210` | 2 | unsigned ÷ 1000 | A | off | Current measured by TCDA2 phase L3. |
| `tcda2_w_l1` | TCDA2 W L1 | `0x0212` | 2 | signed ÷ 10 | W | off | Active power measured by TCDA2 phase L1. |
| `tcda2_w_l2` | TCDA2 W L2 | `0x0214` | 2 | signed ÷ 10 | W | off | Active power measured by TCDA2 phase L2. |
| `tcda2_w_l3` | TCDA2 W L3 | `0x0216` | 2 | signed ÷ 10 | W | off | Active power measured by TCDA2 phase L3. |
| `tcda2_w_total` | TCDA2 W Total | `0x0218` | 2 | signed ÷ 10 | W | off | Active power measured by TCDA2 total. |
| `tcda2_va_total` | TCDA2 VA Total | `0x021A` | 2 | unsigned ÷ 10 | VA | off | Apparent power measured by TCDA2 total. |
| `tcda2_var_total` | TCDA2 VAR Total | `0x021C` | 2 | signed ÷ 10 | var | off | Reactive power measured by TCDA2 total. |
| `tcda2_kwh_total` | TCDA2 kWh Total | `0x021E` | 2 | unsigned ÷ 10 | kWh | off | Active energy measured by TCDA2 total. |
| `tcda2_kvarh_total` | TCDA2 kvarh Total | `0x0220` | 2 | unsigned ÷ 10 | kvarh | off | Reactive energy measured by TCDA2 total. |
| `tcda2_w_dmd_total` | TCDA2 W DMD Total | `0x0222` | 2 | signed ÷ 10 | W | off | Active power demand (average over the integration time) on TCDA2 total. |
| `tcda2_va_dmd_total` | TCDA2 VA DMD Total | `0x0224` | 2 | unsigned ÷ 10 | VA | off | Apparent power demand (average over the integration time) on TCDA2 total. |
| `tcda2_w_maxdmd_total` | TCDA2 W MAXDMD Total | `0x0226` | 2 | signed ÷ 10 | W | off | Highest active power demand recorded on TCDA2 total. |
| `tcda2_va_maxdmd_total` | TCDA2 VA MAXDMD Total | `0x0228` | 2 | unsigned ÷ 10 | VA | off | Highest apparent power demand recorded on TCDA2 total. |
| `tcda2_kwh_l1` | TCDA2 kWh L1 | `0x022A` | 2 | unsigned ÷ 10 | kWh | off | Active energy measured by TCDA2 phase L1. |
| `tcda2_kwh_l2` | TCDA2 kWh L2 | `0x022C` | 2 | unsigned ÷ 10 | kWh | off | Active energy measured by TCDA2 phase L2. |
| `tcda2_kwh_l3` | TCDA2 kWh L3 | `0x022E` | 2 | unsigned ÷ 10 | kWh | off | Active energy measured by TCDA2 phase L3. |
| `tcda2_w_dmd_l1` | TCDA2 W DMD L1 | `0x0230` | 2 | signed ÷ 10 | W | off | Active power demand (average over the integration time) on TCDA2 phase L1. |
| `tcda2_w_dmd_l2` | TCDA2 W DMD L2 | `0x0232` | 2 | signed ÷ 10 | W | off | Active power demand (average over the integration time) on TCDA2 phase L2. |
| `tcda2_w_dmd_l3` | TCDA2 W DMD L3 | `0x0234` | 2 | signed ÷ 10 | W | off | Active power demand (average over the integration time) on TCDA2 phase L3. |
| `tcda2_w_maxdmd_l1` | TCDA2 W MAXDMD L1 | `0x0236` | 2 | signed ÷ 10 | W | off | Highest active power demand recorded on TCDA2 phase L1. |
| `tcda2_w_maxdmd_l2` | TCDA2 W MAXDMD L2 | `0x0238` | 2 | signed ÷ 10 | W | off | Highest active power demand recorded on TCDA2 phase L2. |
| `tcda2_w_maxdmd_l3` | TCDA2 W MAXDMD L3 | `0x023A` | 2 | signed ÷ 10 | W | off | Highest active power demand recorded on TCDA2 phase L3. |
| `tcda2_var_l1` | TCDA2 VAR L1 | `0x023C` | 2 | signed ÷ 10 | var | off | Reactive power measured by TCDA2 phase L1. |
| `tcda2_var_l2` | TCDA2 VAR L2 | `0x023E` | 2 | signed ÷ 10 | var | off | Reactive power measured by TCDA2 phase L2. |
| `tcda2_var_l3` | TCDA2 VAR L3 | `0x0240` | 2 | signed ÷ 10 | var | off | Reactive power measured by TCDA2 phase L3. |
| `tcda2_pf_l1` | TCDA2 PF L1 | `0x0242` | 2 | signed ÷ 1000 |  | off | Power factor measured by TCDA2 phase L1. |
| `tcda2_pf_l2` | TCDA2 PF L2 | `0x0244` | 2 | signed ÷ 1000 |  | off | Power factor measured by TCDA2 phase L2. |
| `tcda2_pf_l3` | TCDA2 PF L3 | `0x0246` | 2 | signed ÷ 1000 |  | off | Power factor measured by TCDA2 phase L3. |
| `tcda2_pf_total` | TCDA2 PF Total | `0x0248` | 2 | signed ÷ 1000 |  | off | Power factor measured by TCDA2 total. |
| `measuring_system` | Measuring System | `0x1002` | 1 | unsigned |  | off | Wiring/measuring system the meter is configured for. _(diagnostic)_ |
| `ct_primary` | CT Primary | `0x1003` | 1 | unsigned |  | off | CT (TCD) type fitted on channel A1, or 'No TCD detected'. _(diagnostic)_ |
| `ct_primary_2` | CT Primary 2 | `0x1004` | 1 | unsigned |  | off | CT (TCD) type fitted on channel A2, or 'No TCD detected'. _(diagnostic)_ |
| `vt_ratio` | VT Ratio | `0x1005` | 1 | unsigned ÷ 10 |  | off | Voltage transformer ratio. _(diagnostic)_ |
| `sum_virtual` | SUM / Virtual | `0x1007` | 1 | unsigned |  | off | SUM/DIF (EM270) or SUM (EM280) virtual-channel mode. _(diagnostic)_ |
| `dmd_integration_time` | DMD Integration Time | `0x1010` | 1 | unsigned | min | off | Demand integration time. _(diagnostic)_ |
| `ton_time` | Ton Time | `0x1012` | 1 | unsigned |  | off | Pulse-output on-time (40 ms / 100 ms). _(diagnostic)_ |
| `kwh_per_pulse_out1` | kWh per Pulse OUT1 | `0x1020` | 1 | unsigned ÷ 100 | kWh | off | Energy represented by one pulse on output 1. _(diagnostic)_ |
| `kwh_per_pulse_out2` | kWh per Pulse OUT2 | `0x1022` | 1 | unsigned ÷ 100 | kWh | off | Energy represented by one pulse on output 2. _(diagnostic)_ |
| `ec_mode` | Easy Connection | `0x1103` | 1 | unsigned |  | off | Easy Connection mode (Enabled/Disabled). _(diagnostic)_ |
| `tcd_phase_order_a1` | TCD Phase Order A1 | `0x1300` | 1 | unsigned |  | off | Phase order of TCD A1 (123 or 321). _(diagnostic)_ |
| `tcd_phase_order_a2` | TCD Phase Order A2 | `0x1302` | 1 | unsigned |  | off | Phase order of TCD A2 (123 or 321). _(diagnostic)_ |
| `rs485_address` | RS485 Address | `0x2000` | 1 | unsigned |  | off | The meter's Modbus address. _(diagnostic)_ |
| `rs485_baud` | RS485 Baud | `0x2001` | 1 | unsigned |  | off | The meter's RS485 baud rate. _(diagnostic)_ |
| `rs485_parity` | RS485 Parity | `0x2002` | 1 | unsigned |  | off | The meter's RS485 parity. _(diagnostic)_ |
| `keypad_lock` | Keypad Lock | `0x0304` | 1 | unsigned |  | off | Whether the keypad is locked. _(diagnostic)_ |
| `production_year` | Production year | `0x5007` | 1 | unsigned |  | off | Year of manufacture. _(diagnostic)_ |
| `secondary_address` | Secondary address | `0x5100` | 2 | unsigned |  | off | Secondary Modbus address. _(diagnostic)_ |
| `tcda1_v_l1` | TCDA1 V L1 | `0x0000` | 2 | unsigned ÷ 10 | V | off | Meter's L1-N voltage shown for a TCDA1 line (alias of `v_l1_n`; no extra read). |
| `tcda1_v_l2` | TCDA1 V L2 | `0x0002` | 2 | unsigned ÷ 10 | V | off | Meter's L2-N voltage shown for a TCDA1 line (alias of `v_l2_n`; no extra read). |
| `tcda1_v_l3` | TCDA1 V L3 | `0x0004` | 2 | unsigned ÷ 10 | V | off | Meter's L3-N voltage shown for a TCDA1 line (alias of `v_l3_n`; no extra read). |
| `tcda2_v_l1` | TCDA2 V L1 | `0x0000` | 2 | unsigned ÷ 10 | V | off | Meter's L1-N voltage shown for a TCDA2 line (alias of `v_l1_n`; no extra read). |
| `tcda2_v_l2` | TCDA2 V L2 | `0x0002` | 2 | unsigned ÷ 10 | V | off | Meter's L2-N voltage shown for a TCDA2 line (alias of `v_l2_n`; no extra read). |
| `tcda2_v_l3` | TCDA2 V L3 | `0x0004` | 2 | unsigned ÷ 10 | V | off | Meter's L3-N voltage shown for a TCDA2 line (alias of `v_l3_n`; no extra read). |

## EM24 (64 sensors)

| Key | Name | Register | Words | Decoding | Unit | Default | Meaning |
|---|---|---|---:|---|---|---|---|
| `v_l1_n` | V L1-N | `0x0000` | 2 | unsigned ÷ 10 | V | on | Voltage between phase L1 and neutral. |
| `v_l2_n` | V L2-N | `0x0002` | 2 | unsigned ÷ 10 | V | on | Voltage between phase L2 and neutral. |
| `v_l3_n` | V L3-N | `0x0004` | 2 | unsigned ÷ 10 | V | on | Voltage between phase L3 and neutral. |
| `v_l1_l2` | V L1-L2 | `0x0006` | 2 | unsigned ÷ 10 | V | off | Line-to-line voltage L1 to L2. |
| `v_l2_l3` | V L2-L3 | `0x0008` | 2 | unsigned ÷ 10 | V | off | Line-to-line voltage L2 to L3. |
| `v_l3_l1` | V L3-L1 | `0x000A` | 2 | unsigned ÷ 10 | V | off | Line-to-line voltage L3 to L1. |
| `a_l1` | A L1 | `0x000C` | 2 | unsigned ÷ 1000 | A | on | Current on phase L1. |
| `a_l2` | A L2 | `0x000E` | 2 | unsigned ÷ 1000 | A | on | Current on phase L2. |
| `a_l3` | A L3 | `0x0010` | 2 | unsigned ÷ 1000 | A | on | Current on phase L3. |
| `w_l1` | W L1 | `0x0012` | 2 | signed ÷ 10 | W | on | Active power on phase L1. |
| `w_l2` | W L2 | `0x0014` | 2 | signed ÷ 10 | W | on | Active power on phase L2. |
| `w_l3` | W L3 | `0x0016` | 2 | signed ÷ 10 | W | on | Active power on phase L3. |
| `va_l1` | VA L1 | `0x0018` | 2 | unsigned ÷ 10 | VA | off | Apparent power on phase L1. |
| `va_l2` | VA L2 | `0x001A` | 2 | unsigned ÷ 10 | VA | off | Apparent power on phase L2. |
| `va_l3` | VA L3 | `0x001C` | 2 | unsigned ÷ 10 | VA | off | Apparent power on phase L3. |
| `var_l1` | VAR L1 | `0x001E` | 2 | signed ÷ 10 | var | off | Reactive power on phase L1. |
| `var_l2` | VAR L2 | `0x0020` | 2 | signed ÷ 10 | var | off | Reactive power on phase L2. |
| `var_l3` | VAR L3 | `0x0022` | 2 | signed ÷ 10 | var | off | Reactive power on phase L3. |
| `v_ln_sum` | V L-N Σ | `0x0024` | 2 | unsigned ÷ 10 | V | off | System phase-to-neutral voltage. |
| `v_ll_sum` | V L-L Σ | `0x0026` | 2 | unsigned ÷ 10 | V | off | System line-to-line voltage. |
| `w_sum` | W Σ | `0x0028` | 2 | signed ÷ 10 | W | on | Total active power across all phases (negative = export). |
| `va_sum` | VA Σ | `0x002A` | 2 | unsigned ÷ 10 | VA | off | Total apparent power. |
| `var_sum` | VAR Σ | `0x002C` | 2 | signed ÷ 10 | var | off | Total reactive power. |
| `w_dmd_sum` | W DMD Σ | `0x002E` | 2 | signed ÷ 10 | W | off | Average total active power over the demand integration time. |
| `va_dmd_sum` | VA DMD Σ | `0x0030` | 2 | unsigned ÷ 10 | VA | off | Average total apparent power over the demand integration time. |
| `pf_l1` | PF L1 | `0x0032` | 1 | signed ÷ 1000 |  | off | Power factor on phase L1. |
| `pf_l2` | PF L2 | `0x0033` | 1 | signed ÷ 1000 |  | off | Power factor on phase L2. |
| `pf_l3` | PF L3 | `0x0034` | 1 | signed ÷ 1000 |  | off | Power factor on phase L3. |
| `pf_sum` | PF Σ | `0x0035` | 1 | signed ÷ 1000 |  | off | Total power factor. |
| `phase_sequence` | Phase Sequence | `0x0036` | 1 | signed |  | off | Detected phase sequence indicator. _(diagnostic)_ |
| `frequency` | Frequency | `0x0037` | 1 | unsigned ÷ 10 | Hz | off | Mains frequency. |
| `w_dmd_max` | W DMD Max | `0x0038` | 2 | signed ÷ 10 | W | off | Highest W demand recorded. |
| `va_dmd_max` | VA DMD Max | `0x003A` | 2 | unsigned ÷ 10 | VA | off | Highest VA demand recorded. |
| `a_dmd_max` | A DMD Max | `0x003C` | 2 | unsigned ÷ 1000 | A | off | Highest current demand recorded. |
| `kwh_import_total` | kWh Import Total | `0x003E` | 2 | unsigned ÷ 10 | kWh | on | Total imported active energy (always rising). |
| `kvarh_import_total` | kvarh Import Total | `0x0040` | 2 | unsigned ÷ 10 | kvarh | off | Total imported reactive energy. |
| `kwh_partial` | kWh Partial | `0x0042` | 2 | unsigned ÷ 10 | kWh | off | Resettable partial active energy. |
| `kvarh_partial` | kvarh Partial | `0x0044` | 2 | unsigned ÷ 10 | kvarh | off | Resettable partial reactive energy. |
| `kwh_l1` | kWh L1 | `0x0046` | 2 | unsigned ÷ 10 | kWh | off | Active energy on phase L1. |
| `kwh_l2` | kWh L2 | `0x0048` | 2 | unsigned ÷ 10 | kWh | off | Active energy on phase L2. |
| `kwh_l3` | kWh L3 | `0x004A` | 2 | unsigned ÷ 10 | kWh | off | Active energy on phase L3. |
| `kwh_t1` | kWh T1 | `0x004C` | 2 | unsigned ÷ 10 | kWh | off | Active energy counted in tariff 1. |
| `kwh_t2` | kWh T2 | `0x004E` | 2 | unsigned ÷ 10 | kWh | off | Active energy counted in tariff 2. |
| `kwh_t3` | kWh T3 | `0x0050` | 2 | unsigned ÷ 10 | kWh | off | Active energy counted in tariff 3. |
| `kwh_t4` | kWh T4 | `0x0052` | 2 | unsigned ÷ 10 | kWh | off | Active energy counted in tariff 4. |
| `kvarh_t1` | kvarh T1 | `0x0054` | 2 | unsigned ÷ 10 | kvarh | off | Reactive energy counted in tariff 1. |
| `kvarh_t2` | kvarh T2 | `0x0056` | 2 | unsigned ÷ 10 | kvarh | off | Reactive energy counted in tariff 2. |
| `kvarh_t3` | kvarh T3 | `0x0058` | 2 | unsigned ÷ 10 | kvarh | off | Reactive energy counted in tariff 3. |
| `kvarh_t4` | kvarh T4 | `0x005A` | 2 | unsigned ÷ 10 | kvarh | off | Reactive energy counted in tariff 4. |
| `kwh_export_total` | kWh Export Total | `0x005C` | 2 | unsigned ÷ 10 | kWh | on | Total exported active energy. |
| `kvarh_export_total` | kvarh Export Total | `0x005E` | 2 | unsigned ÷ 10 | kvarh | off | Total exported reactive energy. |
| `hour_counter` | Hours | `0x0060` | 2 | unsigned ÷ 100 | h | off | Operating hours counter. |
| `counter_1` | Counter 1 | `0x0062` | 2 | unsigned ÷ 10 |  | off | Pulse/digital counter 1. |
| `counter_2` | Counter 2 | `0x0064` | 2 | unsigned ÷ 10 |  | off | Pulse/digital counter 2. |
| `counter_3` | Counter 3 | `0x0066` | 2 | unsigned ÷ 10 |  | off | Pulse/digital counter 3. |
| `digital_input_status` | Digital Input Status | `0x0300` | 1 | unsigned |  | off | State of the digital inputs. _(diagnostic)_ |
| `current_tariff` | Current Tariff | `0x0301` | 1 | unsigned |  | off | Active tariff. _(diagnostic)_ |
| `keypad_lock` | Keypad Lock | `0x0304` | 1 | unsigned |  | off | Whether the keypad is locked. _(diagnostic)_ |
| `measuring_system` | Measuring System | `0x1102` | 1 | unsigned |  | off | Wiring/measuring system the meter is configured for. _(diagnostic)_ |
| `dmd_integration_time` | DMD Integration Time | `0x1103` | 1 | unsigned | min | off | Demand integration time. _(diagnostic)_ |
| `rs485_address` | RS485 Address | `0x110A` | 1 | unsigned |  | off | The meter's Modbus address. _(diagnostic)_ |
| `rs485_baud` | RS485 Baud | `0x110B` | 1 | unsigned |  | off | The meter's RS485 baud rate. _(diagnostic)_ |
| `ct_ratio` | CT Ratio | `0x112C` | 2 | unsigned ÷ 10 |  | off | Current transformer ratio. _(diagnostic)_ |
| `vt_ratio` | VT Ratio | `0x112E` | 2 | unsigned |  | off | Voltage transformer ratio. _(diagnostic)_ |

## Which sensors are on by default

Meter with no TCD wired:

- **EM270 / EM280 (14):** `v_l1_n`, `v_l2_n`, `v_l3_n`, `a_l1_sum`, `a_l2_sum`, `a_l3_sum`, `w_sum`, `kwh_import_total`, `tcda1_w_l1`..`tcda1_w_l3`, `tcda1_kwh_l1`..`tcda1_kwh_l3`.
- **EM24 (12):** `v_l1_n`..`v_l3_n`, `a_l1`..`a_l3`, `w_l1`..`w_l3`, `w_sum`, `kwh_import_total`, `kwh_export_total`.

Meter with TCDs wired: only the W and kWh sensors of named lines (see [tcd-lines.md](tcd-lines.md)).

## Notes on specific sensors

- The six `tcdaN_v_lM` sensors are aliases of `v_lM_n`; they read nothing extra from the bus.
- The EM270/EM280 serial number, production year and secondary address, and all EM24/EM270/EM280 model, firmware and identification values are read once at discovery and shown as **device information**; `production_year` and `secondary_address` are also available as (off) diagnostic sensors.
- On the EM24, a single read is limited to 11 registers; on the EM270/EM280 to 18. The integration groups adjacent enabled registers into reads that respect that limit.
