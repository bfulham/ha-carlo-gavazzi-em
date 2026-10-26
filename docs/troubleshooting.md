# Troubleshooting

## First, get the evidence

1. **Debug log.** Add to `configuration.yaml`, restart, reproduce, then download the log from **Settings -> System -> Logs**:

   ```yaml
   logger:
     default: warning
     logs:
       custom_components.carlo_gavazzi_em: debug
       pymodbus: debug
   ```

   The integration logs each failed read at debug level as `Read attempt N/M failed for slave S at 0xADDR` or `No response from slave S at 0xADDR`.
2. **Diagnostics.** On the integration entry choose **Download diagnostics**. The gateway host and serial numbers are redacted; the TCD layout (names, short names, board names) is not, so check it before posting.
3. Note the meter model and firmware (from the device page), the gateway model and framing, serial settings, and slave addresses.

Never post unredacted network details or credentials in a public issue; for security matters use GitHub's private security advisory (see `SECURITY.md`).

## Setup problems

### The config flow does not open / "Invalid handler specified"

Confirm `/config/custom_components/carlo_gavazzi_em/manifest.json` shows the version you installed, then do a **full restart** of Home Assistant (not just a reload).

### "Could not communicate with the gateway"

The TCP connection to the gateway failed. Check the address and port, that the gateway is powered and on the network, that nothing else holds its only TCP connection, and try a larger **Request timeout** under advanced settings.

### "No compatible EM270, EM280, or EM24 meters were found"

The gateway answered but no meter replied to the identification read.

1. Check gateway baud rate, parity, stop bits and RS-485 two-wire mode against the meters.
2. Check A/B polarity, the common reference and termination; check each meter has a unique address.
3. Choose **Modbus TCP** or **RTU over TCP** explicitly instead of *Auto detect*.
4. Raise **Request timeout** and **Delay between requests**.
5. Narrow **Limit discovery to an address range** to the addresses you expect.
6. Scan the bus without Home Assistant to see what answers: `python3 contrib/scan_slaves.py <gateway-ip> 1 247` ([gateway.md](gateway.md)).

### Setup takes a long time

Every empty address waits for the timeout, three times over (three passes). Limit the address range.

## Running problems

### Every sensor is "unavailable"

| Likely cause | What to check |
|---|---|
| The whole poll fails | Log shows `No meter returned any register data` or `Unable to connect to gateway`: gateway down, address changed, or the bus is dead. |
| Gateway has a single connection slot | Another client (a second Home Assistant, a logger, an old iMod) holds it. Stop the other client. |
| The integration itself failed | Log shows a Python error from `custom_components.carlo_gavazzi_em`. Version 1.3.0 had such a bug (`CarloGavazziSensor.__init__() takes 4 positional arguments but 5 were given`); update to 1.3.1 or newer. |

### One sensor is "unavailable", others work

Normal when the meter reports "not available" for it: a TCD that is not fitted, a quantity your measuring system does not provide, or a register the model does not have (the log shows `No response from slave N at 0x....` for it). Either disable the sensor (disabled sensors are not read) or fix the wiring choice if you marked a TCD as connected that is not. See [sensors.md](sensors.md#values-that-read-as-unavailable).

### Values update slowly, or the log shows overlapping polls

The poll takes longer than the interval. Open **Configure** and use the **Recommended update interval** shown, or disable sensors you do not need. If the shown time is far above the model, look for retries: a meter that is slow or off the bus makes every read wait for the timeout several times. Lower **Polling retries**, fix the wiring, or remove the dead meter by re-running Reconfigure with a narrower range.

### A sensor I enabled turned itself off

Reconfigure and the upgrade migrations switch off TCD sensors and default meter-wide sensors that the TCD layout says should be off, including ones enabled by hand. Enable them again in the entity settings. See [tcd-lines.md](tcd-lines.md#when-entity-ids-change).

### Entity IDs are not what I expected after Reconfigure

IDs are only renamed when the current ID is one the integration generated and the target is free. If you ever edited the ID, it is kept. To get the new ID, rename the entity yourself under **Entity settings -> Entity ID**. Two lines with the same short name on one board get `_2`.

### The sensors are on the wrong device

A line sensor sits under the device you linked (or the meter if none). Run Reconfigure and change **Or link to device**. The line's name is copied from that device at setup time; run Reconfigure to refresh it after renaming the device.

### Energy readings jump or reset

Energy counters are `total_increasing`. If you changed an entity ID, history continues under the old ID and a new series starts under the new ID. A meter whose counters were reset on the meter itself will show a drop that Home Assistant treats as a reset.

## Gateway (Techbase iMod) problems

| Symptom | Cause / fix |
|---|---|
| New IP did not apply after `deploy_gateway.sh` | The script prints the gateway's network configuration when it comes back on the old address; something else (DHCP client, `interfaces.d`) overrides `/etc/network/interfaces`. Remove the override and reboot. |
| `TCP self-test FAILED` at the end of the installer | The proxy could not read the first meter. Check `journalctl -u modbus-rtu-proxy`, the baud/parity and that nothing else has the serial port open (the installer lists holders of the port). |
| `iMod java processes` is not 0 after reboot | A boot-time starter was not found. Run `ps ax | grep -i [j]ava` and `crontab -l` and disable what restarts it. |
| Timeouts for silent meters | Expected: the proxy answers `0x0B` after the retry budget (`--timeout` x (`--retries`+1)). Disable sensors for meters that are not there. |

## Reporting an issue

Open an issue at <https://github.com/bfulham/ha-carlo-gavazzi-em/issues> with: the integration version, Home Assistant version, meter model/firmware, gateway model and framing, serial settings, the debug log around the failure and the (reviewed) diagnostics file. Hardware test reports are especially welcome.
