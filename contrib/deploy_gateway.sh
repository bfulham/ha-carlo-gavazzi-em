#!/bin/bash
#
# deploy_gateway.sh - provision one gateway from this PC in a single command.
#
# Copies install_gateway.sh and modbus_rtu_proxy.py to the gateway, runs the
# installer there (static IP, disable Techbase/iMod, install the proxy service,
# scan the bus), reboots it, waits for it to come back on its new address and
# checks that the service is running.
#
# Easiest use - just run it and answer the questions:
#     ./deploy_gateway.sh
# Or give everything up front:
#     ./deploy_gateway.sh --from 192.168.0.101 --ip 172.16.29.60 --gateway 172.16.29.1
#
# Try a unit without changing anything:   add --dry-run
# Skip the password prompts:              export GW_PASSWORD=...   (needs sshpass)
#
# You will be asked for the gateway's root password once before the install and
# once after the reboot (factory default is in Techbase's documentation).

set -u

HERE=$(cd "$(dirname "$0")" && pwd)

FROM=""
NEWIP=""
GW=""
DNS=""
MASK="255.255.255.0"
USER_NAME="root"
SSH_PORT=22
YES=0
DRY=0
REBOOT=1
VERIFY=1
EXTRA=()

usage() {
    cat <<EOF
Usage: $0 [options] [-- extra install_gateway.sh options]
  --from ADDR      address the gateway has now (default 192.168.0.101 = factory)
  --ip ADDR        new static address to give it
  --gateway ADDR   default gateway (default: new address with last number 1)
  --dns ADDR       DNS server (default: same as the gateway)
  --netmask MASK   default $MASK
  --user NAME      ssh user, default $USER_NAME
  --ssh-port N     default $SSH_PORT
  --yes            do not ask for confirmation
  --dry-run        show what the installer would change, change nothing
  --no-reboot      do not reboot at the end (new IP then needs a manual reboot)
  --no-verify      do not wait for the gateway or check it after the reboot
  -- ...           anything after "--" is passed to install_gateway.sh
                   (for example: -- --scan-last 30 --baud 19200)
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --from) FROM=${2:-}; shift 2 ;;
        --ip) NEWIP=${2:-}; shift 2 ;;
        --gateway) GW=${2:-}; shift 2 ;;
        --dns) DNS=${2:-}; shift 2 ;;
        --netmask) MASK=${2:-}; shift 2 ;;
        --user) USER_NAME=${2:-}; shift 2 ;;
        --ssh-port) SSH_PORT=${2:-}; shift 2 ;;
        --yes|-y) YES=1; shift ;;
        --dry-run) DRY=1; shift ;;
        --no-reboot) REBOOT=0; shift ;;
        --no-verify) VERIFY=0; shift ;;
        -h|--help) usage; exit 0 ;;
        --) shift; EXTRA=("$@"); break ;;
        *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

say()  { printf '\n== %s\n' "$*"; }
info() { printf '   %s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

valid_ip() {
    local o n
    [[ $1 =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || return 1
    IFS=. read -r -a o <<< "$1"
    for n in "${o[@]}"; do [ "$n" -le 255 ] || return 1; done
}

ask() {                     # ask VAR "question" "default"  (no terminal: use the default, or fail)
    local var=$1 text=$2 def=${3:-} val
    if [ ! -t 0 ]; then
        [ -n "$def" ] || die "$text: not given and no terminal to ask on"
        printf -v "$var" '%s' "$def"
        return
    fi
    read -r -p "$text${def:+ [$def]}: " val
    printf -v "$var" '%s' "${val:-$def}"
}

for tool in ssh scp; do command -v "$tool" >/dev/null 2>&1 || die "$tool is not installed"; done
for f in install_gateway.sh modbus_rtu_proxy.py; do
    [ -f "$HERE/$f" ] || die "$f not found next to this script ($HERE)"
done

# ---- gather the details -----------------------------------------------------
[ -n "$FROM" ]  || ask FROM  "Gateway's current IP address" "192.168.0.101"
[ -n "$NEWIP" ] || ask NEWIP "New static IP address for it" ""
valid_ip "$FROM"  || die "bad current address: $FROM"
valid_ip "$NEWIP" || die "bad new address: $NEWIP"
valid_ip "$MASK"  || die "bad netmask: $MASK"
[ -n "$GW" ]  || ask GW  "Default gateway" "${NEWIP%.*}.1"
[ -n "$DNS" ] || ask DNS "DNS server" "$GW"
valid_ip "$GW"  || die "bad gateway: $GW"
valid_ip "$DNS" || die "bad DNS: $DNS"

say "Plan"
info "gateway now at     : $FROM (logging in as $USER_NAME, ssh port $SSH_PORT)"
info "will become        : $NEWIP / $MASK, gateway $GW, dns $DNS"
if [ "$DRY" = 1 ]; then
    info "mode               : DRY RUN (nothing is changed)"
else
    info "mode               : install, then $([ "$REBOOT" = 1 ] && echo reboot || echo 'NO reboot')"
fi
if [ "$YES" != 1 ] && [ -t 0 ]; then
    read -r -p "Go ahead? [y/N] " go
    case "$go" in y|Y|yes|YES) ;; *) echo "cancelled"; exit 1 ;; esac
fi

# ---- one ssh connection, reused (so the password is asked once) ---------------
CTL="/tmp/gwdeploy-$$"
SSH_OPTS=(-p "$SSH_PORT" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
          -o LogLevel=ERROR -o ConnectTimeout=8 -o ServerAliveInterval=15)
SCP_OPTS=(-P "$SSH_PORT" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR)
MUX=(-o ControlMaster=auto -o "ControlPath=$CTL-%h" -o ControlPersist=15m)
PASS=()
if [ -n "${GW_PASSWORD:-}" ] && command -v sshpass >/dev/null 2>&1; then
    export SSHPASS="$GW_PASSWORD"
    PASS=(sshpass -e)
fi
sshx() { "${PASS[@]+"${PASS[@]}"}" ssh "${SSH_OPTS[@]}" "${MUX[@]}" "$@"; }
scpx() { "${PASS[@]+"${PASS[@]}"}" scp "${SCP_OPTS[@]}" "${MUX[@]}" "$@"; }
close_mux() { ssh -o "ControlPath=$CTL-$1" -O exit "$USER_NAME@$1" >/dev/null 2>&1 || true; }

# ---- copy and run -----------------------------------------------------------
say "Copying the install files to $FROM"
if ! scpx "$HERE/install_gateway.sh" "$HERE/modbus_rtu_proxy.py" "$USER_NAME@$FROM:/root/"; then
    die "could not copy to $FROM - check the address, the password and that ssh is reachable"
fi

INSTALL_ARGS=(--ip "$NEWIP" --netmask "$MASK" --gateway "$GW" --dns "$DNS")
[ "$DRY" = 1 ] && INSTALL_ARGS+=(--dry-run)
[ "$DRY" != 1 ] && [ "$REBOOT" = 1 ] && INSTALL_ARGS+=(--reboot)
INSTALL_ARGS+=(${EXTRA[@]+"${EXTRA[@]}"})
REMOTE_CMD="chmod +x /root/install_gateway.sh && /root/install_gateway.sh $(printf '%q ' "${INSTALL_ARGS[@]}")"

say "Running the installer on the gateway (this takes a few minutes while it scans)"
sshx -tt "$USER_NAME@$FROM" "$REMOTE_CMD"
RC=$?
close_mux "$FROM"
if [ "$DRY" = 1 ]; then say "Dry run finished - nothing was changed"; exit 0; fi
if [ "$RC" != 0 ] && ! { [ "$REBOOT" = 1 ] && [ "$RC" = 255 ]; }; then
    die "the installer on the gateway failed (exit $RC) - read its output above"
fi

if [ "$REBOOT" != 1 ]; then
    say "Done (not rebooted)"
    info "the new address ($NEWIP) is applied after a reboot:  ssh $USER_NAME@$FROM reboot"
    exit 0
fi
if [ "$VERIFY" != 1 ]; then say "Done - gateway is rebooting onto $NEWIP"; exit 0; fi

# ---- wait for it, then check ----------------------------------------------------
say "Waiting for the gateway to come back on $NEWIP"
sleep 20
up=0
for _ in $(seq 1 60); do
    if timeout 3 bash -c "exec 3<>/dev/tcp/$NEWIP/$SSH_PORT" 2>/dev/null; then up=1; break; fi
    printf '.'; sleep 5
done
echo
[ "$up" = 1 ] || die "the gateway did not answer on $NEWIP within 5 minutes - check its network settings"

say "Checking the gateway on $NEWIP"
sleep 5
CHECK_CMD='echo "service: $(systemctl is-active modbus-rtu-proxy 2>&1)";
echo "listening on 502: $(netstat -tln 2>/dev/null | grep -c ":502 ")";
echo "iMod java processes: $(ps ax 2>/dev/null | grep -c "[p]l.techbase.imod")";
grep -E "scanned|meters answering" /var/log/modbus-gateway-scan.txt 2>/dev/null'
OUT=$(sshx "$USER_NAME@$NEWIP" "$CHECK_CMD" 2>&1)
close_mux "$NEWIP"
printf '%s\n' "$OUT" | sed 's/^/   /'

ok=1
printf '%s\n' "$OUT" | grep -q '^service: active' || ok=0
printf '%s\n' "$OUT" | grep -q '^listening on 502: [1-9]' || ok=0
printf '%s\n' "$OUT" | grep -q '^iMod java processes: 0' || ok=0
echo
if [ "$ok" = 1 ]; then
    say "PASS - $NEWIP is serving Modbus TCP on port 502, iMod is off"
    info "add it in Home Assistant with host $NEWIP, port 502, and a scan range that matches the meters above"
else
    say "CHECK FAILED - see the lines above (ssh $USER_NAME@$NEWIP, then: journalctl -u modbus-rtu-proxy)"
    exit 1
fi
