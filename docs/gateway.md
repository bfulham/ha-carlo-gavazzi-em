# Setting up the gateway

The integration speaks **Modbus TCP** (or RTU framing carried over TCP) to a gateway, and the gateway speaks **Modbus RTU** to the meters over RS-485. The integration cannot configure the gateway: a generic gateway has no standard Modbus way to change its own baud rate, parity or stop bits. Set those on the gateway first.

## 1. The RS-485 bus

Before anything else, on the meters and the gateway:

| Item | Requirement |
|---|---|
| Baud rate | The same on every meter and the gateway. Meter options: EM270/EM280 9600 / 19200 / 38400; EM24 9600 / 4800. |
| Parity / stop bits | The same on every meter and the gateway. |
| Slave address | A **unique** Modbus address (1-247) on every meter. |
| Wiring | Two-wire RS-485, A/B polarity correct, common reference connected, termination at the ends of long runs. |
| Gateway mode | RS-485 two-wire mode. |
| Gateway RTU timeout | Long enough for a meter to answer (a few hundred ms). |

The meter's own serial settings can be read back by the integration as diagnostic sensors (`rs485_address`, `rs485_baud`, `rs485_parity`), but they are off by default; enable them if you need to check what a meter is set to.

## 2. Using any transparent gateway

Any gateway that exposes the serial bus as Modbus TCP works: point the integration at its IP and port (normally 502). During setup, leave **TCP framing** on **Auto detect**; the integration tries Modbus TCP and RTU-over-TCP against a real meter and remembers which answered (see [setup.md](setup.md#step-2---advanced-gateway-settings-only-if-ticked)).

If you are not sure which addresses the meters use, scan the bus from any PC with the bundled script before you add the integration:

```bash
python3 contrib/scan_slaves.py <gateway-ip> 1 247 [port]
```

It reads the identification register (`11`) from each unit id over one TCP connection, prints each unit as `meter`, `empty` (the gateway answered with a Modbus exception, nobody home) or `silent` (no reply within 10 s) with its time in milliseconds, and ends with a summary of the meters found and the five slowest addresses. It only reads. Note that the host argument defaults to `172.16.29.51` (the author's gateway), so always pass your own.

## 3. Replacing a Techbase iMod gateway's software (optional)

The Techbase NPE/iMod gateways run Linux and ship with the iMod data-logger software, which sits between Home Assistant and the meters. On the gateways this integration was developed against, iMod answered from a cache and learned every register it was asked for into its own configuration, and it could stall for about a minute and be restarted by its watchdog; that made polling unreliable. The `contrib/` folder replaces it with a tiny bridge.

> **This is optional and changes the gateway.** It disables the Techbase software on that unit (nothing is deleted, originals are backed up) and installs a service. Try `--dry-run` on one unit first. You are responsible for the warranty/support position of the gateway.

### What the proxy does (`contrib/modbus_rtu_proxy.py`)

- Standard library only; runs on **Python 2.7 and Python 3**.
- Listens for Modbus TCP on `--port` and forwards each request to the serial port as RTU.
- **Serialises** all requests behind one lock, so several TCP clients can share the bus safely.
- **Read-only:** only functions `0x01`-`0x04` are forwarded. Anything else is answered with Modbus exception `0x01` (illegal function), so a write can never reach a meter.
- A unit id outside 1-247, or a meter that does not answer (after the configured retries), is answered at once with exception `0x0B` (gateway target device failed to respond) carrying the request's own unit id.
- Validates the RTU reply (unit id, CRC, function) before returning it.

Options (all have defaults):

| Option | Default | Meaning |
|---|---|---|
| `--serial` | _(required)_ | Serial device, e.g. `/dev/ttySC0`. |
| `--baud` | `9600` | One of 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200. |
| `--parity` | `N` | `N`, `E` or `O`. |
| `--stop-bits` | `1` | `1` or `2`. |
| `--port` | `502` | TCP listen port. |
| `--bind` | `0.0.0.0` | Listen address. |
| `--timeout` | `0.3` | Seconds to wait for a meter per try. |
| `--retries` | `1` | Extra tries per request. |
| `--gap` | `0.01` | Idle seconds between requests. |
| `--max-clients` | `16` | Simultaneous TCP clients; extra connections are closed. |
| `--probe UNIT` | | Read one register (`--addr`, default 11) from that unit and exit. |
| `--scan` | | Time every unit id (`--first`/`--last`, default 1-247) on the serial bus and exit. |
| `-v` | off | Log unanswered requests. |

`--probe` and `--scan` use the serial port directly, so stop the proxy first.

### One-command deployment (`contrib/deploy_gateway.sh`)

Run from a PC that can reach the gateway over SSH (needs `ssh` and `scp`):

```bash
./deploy_gateway.sh                         # asks for the details
./deploy_gateway.sh --from 192.168.0.101 --ip 172.16.29.60 --gateway 172.16.29.1
./deploy_gateway.sh --dry-run ...           # show what would change, change nothing
```

| Option | Meaning |
|---|---|
| `--from ADDR` | Address the gateway has now (default `192.168.0.101`, the factory address). |
| `--ip ADDR` | New static address to give it. |
| `--gateway ADDR` | Default gateway (default: the new address with the last number `1`). |
| `--dns ADDR` | DNS server (default: the same as the gateway). |
| `--netmask MASK` | Default `255.255.255.0`. |
| `--user NAME`, `--ssh-port N` | SSH login (default `root`, port 22). |
| `--yes` | Do not ask for confirmation. |
| `--dry-run` | Change nothing. |
| `--no-reboot` | Do not reboot (the new IP then needs a manual reboot). |
| `--no-verify` | Do not wait for the gateway or check it afterwards. |
| `-- ...` | Everything after `--` goes to `install_gateway.sh`, e.g. `-- --scan-last 30 --baud 19200`. |

It copies `install_gateway.sh` and `modbus_rtu_proxy.py` to `/root/` on the gateway, runs the installer, reboots, waits for the gateway to return on the new address and checks that the service is active, port 502 is listening and no iMod Java process is running. You are asked for the gateway's root password before the install and again after the reboot; set `GW_PASSWORD` (and install `sshpass`) to skip the prompts. The SSH connection uses `StrictHostKeyChecking=no` because the gateway's host key changes when you re-flash or replace a unit.

The gateway's login credentials are not in this repository. Use the ones from your gateway's documentation or your own records.

### What the installer does (`contrib/install_gateway.sh`)

It can also be run directly on the gateway (as root, with `modbus_rtu_proxy.py` next to it). In order:

1. **Static IP** - rewrites the `eth0` stanza of `/etc/network/interfaces` (only when `--ip` is given). It is applied on the next reboot so your session survives. If `dhcpcd` is present, `denyinterfaces eth0` is added. It warns if the current address is also set elsewhere under `/etc`.
2. **Disable the Techbase cron jobs** - comments out entries pointing at `/home/imod/`, `/home/imodcloud/` or `/home/npe_tuneup/` in the root crontab, `/etc/crontab` and `/etc/cron.d/*`, marked `#DISABLED-BY-MODBUS-INSTALLER`. The root crontab is saved to `/root/crontab.backup-<time>`.
3. **Stop iMod** - runs `imod stop` if present and ends the iMod/iModCloud processes (VPN processes are left alone and reported).
4. **Disable boot-time starters** - systemd units / init scripts / `rc.local` lines matching imod, nxs or techbase.
5. **Install the proxy** - copies it to `/opt/modbus-rtu-proxy/`, sets the RS-485 controller to RS-485 mode with `comctrl <controller> RS-485` if `comctrl` exists, and writes the systemd service `modbus-rtu-proxy` (`Restart=always`).
6. **Scan the bus** (unless `--skip-scan`) and save the result to `/var/log/modbus-gateway-scan.txt`.
7. **Start the service and self-test** over TCP (reads register 11 of the first meter found).
8. **Summary**, and a reboot after about 10 s if `--reboot` was given.

Installer options: `--ip`, `--netmask` (default `255.255.255.0`), `--gateway`, `--dns`, `--iface` (`eth0`), `--serial` (`/dev/ttySC0`), `--baud` (`9600`), `--parity` (`N`), `--controller` (`2`, which is COM3), `--port` (`502`), `--scan-first` (`1`), `--scan-last` (`247`), `--skip-scan`, `--reboot`, `--dry-run`. It is safe to re-run. The first copy of every file it changes is kept in `/root/modbus-installer-backups/`.

### Undoing it

- Cron: `crontab /root/crontab.backup-<time>` (the exact file name is printed in the summary).
- `interfaces`, `cron.d`, `rc.local`: copy the originals back from `/root/modbus-installer-backups/`.
- Service: `systemctl disable --now modbus-rtu-proxy`.

### Checking the running proxy

```bash
systemctl status modbus-rtu-proxy
journalctl -u modbus-rtu-proxy
```

Because the service runs with `-v`, every request that gets no answer from a meter is logged as `no reply from unit N (<client ip>)`.

## 4. Gateway tips for this integration

- A gateway that allows only **one TCP connection** will refuse extra ones. The integration keeps a single connection open and closes stale ones (fixed in 1.1.2), so do not run other Modbus clients against the same gateway at the same time unless the gateway supports several.
- Silent addresses are slow: a scan of 1-247 against a bus with few meters waits for the timeout on every empty address. Use **Limit discovery to an address range** when you know the meters' addresses.
