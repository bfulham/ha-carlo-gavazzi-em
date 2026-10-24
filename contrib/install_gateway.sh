#!/bin/bash
#
# install_gateway.sh - turn a stock Techbase NPE/iMod gateway into a plain,
# read-only Modbus TCP <-> RTU bridge for the Carlo Gavazzi EM integration.
#
# What it does, in order:
#   1. writes a static IP into /etc/network/interfaces (applied on next reboot)
#   2. disables the Techbase/iMod software: cron jobs, running processes and
#      anything it finds that starts them at boot (nothing is deleted)
#   3. installs modbus_rtu_proxy.py as a systemd service that starts at boot and
#      restarts itself, and puts the RS-485 controller in RS-485 mode
#   4. scans the serial bus for meters and logs the result
#   5. starts the service and tests it over TCP
#
# Copy this script and modbus_rtu_proxy.py into the same folder on the gateway:
#   scp install_gateway.sh modbus_rtu_proxy.py root@<current-ip>:/root/
# then, on the gateway (try --dry-run first on one unit):
#   sh -c 'chmod +x install_gateway.sh && ./install_gateway.sh --ip 172.16.29.60 \
#       --gateway 172.16.29.1 --dns 172.16.29.1 --dry-run'
#
# Safe to re-run. The first copy of every file it changes is kept in
# /root/modbus-installer-backups/ and the crontab is saved to
# /root/crontab.backup-<time>.

set -u

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=${ROOT:-}                      # test hook: prefix for every path it writes
STAMP=$(date +%Y%m%d-%H%M%S)

IP=""
NETMASK="255.255.255.0"
GATEWAY=""
DNS=""
IFACE="eth0"
SERIAL="/dev/ttySC0"
BAUD=9600
PARITY="N"
CONTROLLER=2
TCP_PORT=502
SCAN_FIRST=1
SCAN_LAST=247
SKIP_SCAN=0
DRY=0
REBOOT=0

INSTALL_DIR="$ROOT/opt/modbus-rtu-proxy"
UNIT_NAME="modbus-rtu-proxy"
UNIT_FILE="$ROOT/etc/systemd/system/$UNIT_NAME.service"
SCAN_LOG="$ROOT/var/log/modbus-gateway-scan.txt"
MARK="#DISABLED-BY-MODBUS-INSTALLER"

usage() {
    cat <<EOF
Usage: $0 [options]
  --ip ADDR          static IPv4 address for $IFACE (omit to leave networking alone)
  --netmask MASK     default $NETMASK
  --gateway ADDR     default gateway (optional)
  --dns ADDR         DNS server (optional)
  --iface NAME       default $IFACE
  --serial DEV       serial device for the RS-485 port, default $SERIAL
  --baud N           meter baud rate, default $BAUD
  --parity N|E|O     default $PARITY
  --controller N     comctrl controller for that port (COM3 = 2), default $CONTROLLER
  --port N           TCP port to listen on, default $TCP_PORT
  --scan-first N     first unit id to scan, default $SCAN_FIRST
  --scan-last N      last unit id to scan, default $SCAN_LAST
  --skip-scan        do not scan the bus
  --reboot           reboot 10 s after finishing (needed to apply the new IP)
  --dry-run          show what would change, change nothing
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --ip) IP=${2:-}; shift 2 ;;
        --netmask) NETMASK=${2:-}; shift 2 ;;
        --gateway) GATEWAY=${2:-}; shift 2 ;;
        --dns) DNS=${2:-}; shift 2 ;;
        --iface) IFACE=${2:-}; shift 2 ;;
        --serial) SERIAL=${2:-}; shift 2 ;;
        --baud) BAUD=${2:-}; shift 2 ;;
        --parity) PARITY=${2:-}; shift 2 ;;
        --controller) CONTROLLER=${2:-}; shift 2 ;;
        --port) TCP_PORT=${2:-}; shift 2 ;;
        --scan-first) SCAN_FIRST=${2:-}; shift 2 ;;
        --scan-last) SCAN_LAST=${2:-}; shift 2 ;;
        --skip-scan) SKIP_SCAN=1; shift ;;
        --reboot) REBOOT=1; shift ;;
        --dry-run) DRY=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

say()  { printf '\n== %s\n' "$*"; }
info() { printf '   %s\n' "$*"; }
warn() { printf '   WARNING: %s\n' "$*" >&2; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

run() {
    if [ "$DRY" = 1 ]; then info "[dry-run] $*"; return 0; fi
    "$@"
}

write_file() {              # write_file DEST MODE  (content on stdin)
    local dest=$1 mode=$2
    if [ "$DRY" = 1 ]; then info "[dry-run] would write $dest"; cat >/dev/null; return 0; fi
    mkdir -p "$(dirname "$dest")" && cat > "$dest" && chmod "$mode" "$dest"
}

BACKUP_DIR="$ROOT/root/modbus-installer-backups"

backup_once() {             # first copy of a file is kept, outside any directory we scan
    local dest="$BACKUP_DIR/$(printf '%s' "${1#$ROOT}" | tr '/' '_')"
    if [ -e "$1" ] && [ ! -e "$dest" ]; then
        run mkdir -p "$BACKUP_DIR" && run cp -p "$1" "$dest"
    fi
}

valid_ip() {
    local o n
    [[ $1 =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || return 1
    IFS=. read -r -a o <<< "$1"
    for n in "${o[@]}"; do [ "$n" -le 255 ] || return 1; done
}

PYTHON=$(command -v python || command -v python2 || command -v python3 || true)
FOUND=""

preflight() {
    say "Pre-flight"
    if [ -z "$ROOT" ] && [ "$(id -u)" != 0 ]; then die "run as root"; fi
    [ -n "$PYTHON" ] || die "no python found"
    PROXY_SRC=""
    for c in "$HERE/modbus_rtu_proxy.py" "$HERE/../modbus_rtu_proxy.py"; do
        if [ -f "$c" ]; then PROXY_SRC=$c; break; fi
    done
    [ -n "$PROXY_SRC" ] || die "modbus_rtu_proxy.py not found next to this script"
    if [ -n "$IP" ]; then
        valid_ip "$IP" || die "bad --ip: $IP"
        valid_ip "$NETMASK" || die "bad --netmask: $NETMASK"
        if [ -n "$GATEWAY" ]; then valid_ip "$GATEWAY" || die "bad --gateway: $GATEWAY"; fi
        if [ -n "$DNS" ]; then valid_ip "$DNS" || die "bad --dns: $DNS"; fi
    fi
    info "python: $PYTHON    proxy: $PROXY_SRC"
    if [ "$DRY" = 1 ]; then info "DRY RUN - nothing will be changed"; fi
}

configure_network() {
    say "Static IP"
    if [ -z "$IP" ]; then info "no --ip given, leaving networking alone"; return; fi
    local f="$ROOT/etc/network/interfaces" tmp
    if [ ! -f "$f" ]; then warn "$f not found, skipping"; return; fi
    tmp=$(mktemp)
    awk -v ifc="$IFACE" '
        { line = $0 }
        line ~ "^[ \t]*(auto|allow-[a-z-]+)[ \t]+" ifc "([ \t]|$)" { next }
        line ~ "^[ \t]*iface[ \t]+" ifc "[ \t]" { skip = 1; next }
        skip {
            if (line ~ /^[ \t]*(auto|allow-[a-z-]+|iface|source|source-directory|mapping)[ \t]/) { skip = 0 }
            else { next }
        }
        { print line }
    ' "$f" > "$tmp"
    {
        printf '\nauto %s\nallow-hotplug %s\niface %s inet static\n' "$IFACE" "$IFACE" "$IFACE"
        printf '    address %s\n    netmask %s\n' "$IP" "$NETMASK"
        if [ -n "$GATEWAY" ]; then printf '    gateway %s\n' "$GATEWAY"; fi
        if [ -n "$DNS" ]; then printf '    dns-nameservers %s\n' "$DNS"; fi
    } >> "$tmp"
    if [ "$DRY" = 1 ]; then
        info "[dry-run] $f would change as follows:"
        diff -u "$f" "$tmp" | sed 's/^/      /'
    else
        backup_once "$f"
        cp "$tmp" "$f"
        info "wrote $f (original kept in $BACKUP_DIR)"
    fi
    rm -f "$tmp"
    if command -v dhcpcd >/dev/null 2>&1 && [ -f "$ROOT/etc/dhcpcd.conf" ] \
        && ! grep -q "^denyinterfaces.*$IFACE" "$ROOT/etc/dhcpcd.conf"; then
        backup_once "$ROOT/etc/dhcpcd.conf"
        if [ "$DRY" = 1 ]; then info "[dry-run] would add 'denyinterfaces $IFACE' to dhcpcd.conf"
        else echo "denyinterfaces $IFACE" >> "$ROOT/etc/dhcpcd.conf"; fi
    fi
    info "the new address ($IP) takes effect after a reboot - not applied now so this session survives"
}

comment_techbase_lines() {      # comment_techbase_lines FILE
    local f=$1
    grep -Eq '^[^#].*(/home/(imod|imodcloud|npe_tuneup)/|pl\.techbase)' "$f" 2>/dev/null || return 0
    info "$f:"
    grep -E '^[^#].*(/home/(imod|imodcloud|npe_tuneup)/|pl\.techbase)' "$f" | sed 's/^/      disabling: /'
    backup_once "$f"
    if [ "$DRY" != 1 ]; then
        sed -E -i "s@^([^#].*(/home/(imod|imodcloud|npe_tuneup)/|pl\\.techbase).*)\$@$MARK \\1@" "$f"
    fi
}

disable_cron() {
    say "Techbase/iMod cron jobs"
    local cur new
    cur=$(crontab -l 2>/dev/null || true)
    if [ -z "$cur" ]; then
        info "root crontab is empty"
    elif printf '%s\n' "$cur" | grep -Eq '^[^#].*/home/(imod|imodcloud|npe_tuneup)/'; then
        printf '%s\n' "$cur" | grep -E '^[^#].*/home/(imod|imodcloud|npe_tuneup)/' | sed 's/^/      disabling: /'
        if [ "$DRY" != 1 ]; then
            printf '%s\n' "$cur" > "$ROOT/root/crontab.backup-$STAMP" 2>/dev/null \
                || printf '%s\n' "$cur" > "/root/crontab.backup-$STAMP"
            new=$(printf '%s\n' "$cur" | sed -E "s@^([^#].*/home/(imod|imodcloud|npe_tuneup)/.*)\$@$MARK \\1@")
            printf '%s\n' "$new" | crontab -
            info "crontab updated (backup: /root/crontab.backup-$STAMP)"
        fi
    else
        info "no Techbase/iMod entries in the root crontab"
    fi
    comment_techbase_lines "$ROOT/etc/crontab"
    local f
    for f in "$ROOT"/etc/cron.d/*; do [ -f "$f" ] && comment_techbase_lines "$f"; done
}

techbase_processes() {          # prints "pid command-line" for iMod / iModCloud programs only
    ps ax -o pid=,args= 2>/dev/null | awk -v me="$$" '
        $1 == me { next }
        {
            cmd = $2
            if (cmd ~ /(^|\/)(sh|bash|dash|python[0-9.]*|perl)$/) cmd = $3
            if (cmd ~ /^\/home\/(imod|imodcloud)\// || cmd == "/bin/imod" \
                || ($2 ~ /java$/ && $0 ~ /pl\.techbase\.imod\.Main/)) print
        }'
}

stop_techbase() {
    say "Stop iMod and Techbase processes"
    local pids p n
    if command -v imod >/dev/null 2>&1; then run imod stop >/dev/null 2>&1; else info "no imod command found"; fi
    if [ "$DRY" != 1 ]; then echo STOPPED > "$ROOT/tmp/status" 2>/dev/null || true; fi
    pids=$(techbase_processes | awk '{print $1}')
    if [ -z "$pids" ]; then info "no Techbase/iMod processes running"; return; fi
    techbase_processes | cut -c1-120 | sed 's/^/      /'
    if [ "$DRY" = 1 ]; then info "[dry-run] would stop the processes above"; return; fi
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null
    for n in 1 2 3 4 5 6 7 8 9 10; do
        sleep 1
        for p in $pids; do kill -0 "$p" 2>/dev/null && continue 2; done
        break
    done
    for p in $pids; do kill -0 "$p" 2>/dev/null && { warn "pid $p ignored TERM, killing"; kill -9 "$p"; }; done
    info "stopped"
    ps ax -o pid=,args= | grep -i -E 'openvpn|vpn' | grep -v grep | cut -c1-120 \
        | sed 's/^/      still running (left alone, check if you need it): /'
}

disable_boot_start() {
    say "Anything that starts Techbase/iMod at boot"
    local u s found=0
    if command -v systemctl >/dev/null 2>&1; then
        for u in $(systemctl list-unit-files --no-legend 2>/dev/null | awk '{print $1}' \
                   | grep -i -E '(imod|nxs|techbase|npe[-_]).*\.(service|timer)$'); do
            found=1; info "systemd unit: $u"
            run systemctl disable "$u" >/dev/null 2>&1
            run systemctl stop "$u" >/dev/null 2>&1
        done
    fi
    for s in $(ls "$ROOT/etc/init.d" 2>/dev/null | grep -i -E 'imod|nxs|techbase'); do
        found=1; info "init script: $s"
        run update-rc.d "$s" disable >/dev/null 2>&1
    done
    if [ -f "$ROOT/etc/rc.local" ] && grep -Eiq '^[^#].*(imod|nxs|techbase)' "$ROOT/etc/rc.local"; then
        found=1; info "/etc/rc.local:"
        grep -Ei '^[^#].*(imod|nxs|techbase)' "$ROOT/etc/rc.local" | sed 's/^/      disabling: /'
        backup_once "$ROOT/etc/rc.local"
        if [ "$DRY" != 1 ]; then
            sed -E -i "s@^([^#].*(imod|nxs|techbase).*)\$@$MARK \\1@I" "$ROOT/etc/rc.local"
        fi
    fi
    if [ "$found" = 0 ]; then
        warn "found no boot-time starter for iMod (cron respawn was the only one seen)."
        warn "after the first reboot check:  ps ax | grep -i [j]ava"
    fi
}

install_proxy() {
    say "Install the proxy service"
    run mkdir -p "$INSTALL_DIR"
    run install -m 755 "$PROXY_SRC" "$INSTALL_DIR/modbus_rtu_proxy.py"
    local comctrl pre=""
    comctrl=$(command -v comctrl || true)
    if [ -n "$comctrl" ]; then
        run "$comctrl" "$CONTROLLER" RS-485
        if [ "$DRY" != 1 ] && ! "$comctrl" -r 2>/dev/null | grep -q "Controller $CONTROLLER in RS-485"; then
            warn "comctrl does not report Controller $CONTROLLER in RS-485 mode"
        fi
        pre="ExecStartPre=-$comctrl $CONTROLLER RS-485"
    else
        warn "comctrl not found - make sure the serial port is in RS-485 mode"
    fi
    write_file "$UNIT_FILE" 644 <<EOF
[Unit]
Description=Modbus TCP to RTU proxy for Carlo Gavazzi energy meters
After=network.target

[Service]
$pre
ExecStart=$PYTHON $INSTALL_DIR/modbus_rtu_proxy.py --serial $SERIAL --baud $BAUD --parity $PARITY --port $TCP_PORT -v
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF
    run systemctl daemon-reload
    run systemctl enable "$UNIT_NAME"
}

scan_bus() {
    say "Scan the bus for meters (units $SCAN_FIRST-$SCAN_LAST)"
    if [ "$SKIP_SCAN" = 1 ]; then info "skipped (--skip-scan)"; return; fi
    if [ "$DRY" = 1 ]; then info "[dry-run] would scan $SERIAL"; return; fi
    mkdir -p "$(dirname "$SCAN_LOG")"
    "$PYTHON" "$INSTALL_DIR/modbus_rtu_proxy.py" --serial "$SERIAL" --baud "$BAUD" --parity "$PARITY" \
        --scan --first "$SCAN_FIRST" --last "$SCAN_LAST" 2>&1 | tee "$SCAN_LOG"
    if [ "${PIPESTATUS[0]}" != 0 ]; then
        warn "the scan failed - is $SERIAL the right port and is anything else using it?"
        return
    fi
    FOUND=$(grep -E 'meters answering' "$SCAN_LOG" | sed -E 's/.*units \[([^]]*)\].*/\1/')
    info "scan log: $SCAN_LOG"
}

start_service() {
    say "Start the proxy and test it over TCP"
    run systemctl restart "$UNIT_NAME"
    if [ "$DRY" = 1 ]; then info "[dry-run] would test TCP port $TCP_PORT"; return; fi
    sleep 3
    local first=${FOUND%%,*}
    first=${first// /}
    "$PYTHON" - "$TCP_PORT" "${first:-0}" <<'PY'
import socket, struct, sys
port, unit = int(sys.argv[1]), int(sys.argv[2])
try:
    s = socket.create_connection(("127.0.0.1", port), timeout=3)
except Exception as err:
    print("   TCP self-test FAILED: cannot connect to port %d (%s)" % (port, err))
    sys.exit(1)
if not unit:
    print("   TCP self-test: port %d is accepting connections (no meter to read)" % port)
    sys.exit(0)
s.sendall(struct.pack(">HHHBBHH", 1, 0, 6, unit, 3, 11, 1))
s.settimeout(4)
d = bytearray(s.recv(64))
if len(d) >= 11 and d[7] == 3:
    print("   TCP self-test PASSED: unit %d register 11 = %d" % (unit, d[9] * 256 + d[10]))
    sys.exit(0)
print("   TCP self-test FAILED: unit %d reply %r" % (unit, list(d)))
sys.exit(1)
PY
}

summary() {
    say "Summary"
    info "meters found on the bus : ${FOUND:-none}"
    if [ -n "$IP" ]; then info "static IP               : $IP/$NETMASK (after reboot)"; fi
    info "service                 : systemctl status $UNIT_NAME   |   journalctl -u $UNIT_NAME"
    info "scan log                : $SCAN_LOG"
    info "undo cron changes       : crontab /root/crontab.backup-$STAMP"
    info "undo other changes       : originals are in $BACKUP_DIR (interfaces, cron.d, rc.local)"
    if [ -z "$FOUND" ] && [ "$SKIP_SCAN" != 1 ] && [ "$DRY" != 1 ]; then
        warn "no meters answered. Check wiring, A/B polarity, baud/parity ($BAUD/$PARITY) and unit ids."
    fi
    if [ "$REBOOT" = 1 ] && [ "$DRY" != 1 ]; then
        info "rebooting in 10 s ..."
        ( sleep 10; reboot ) >/dev/null 2>&1 &
    elif [ -n "$IP" ]; then
        info "reboot to apply the new IP:  reboot"
    fi
}

preflight
configure_network
disable_cron
stop_techbase
disable_boot_start
install_proxy
scan_bus
start_service
summary
