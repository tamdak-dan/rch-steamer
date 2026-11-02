#!/usr/bin/env bash
# =============================================================================
# RCH Steamer HMI - Raspberry Pi kiosk installer
# =============================================================================
# Turns a fresh "Raspberry Pi OS Lite (64-bit)" SD card into a unit that boots
# straight into the HMI, full screen, with no desktop.
#
# Run it on the Pi, with Ethernet plugged into a network that has internet:
#
#     git clone https://github.com/tamdak-dan/rch-steamer.git
#     sudo rch-steamer/deploy/install.sh
#
# Options (all optional; defaults shown):
#   --pi-ip ADDR/PREFIX  This Pi's fixed address on the machine network
#                        (192.168.137.20/24)
#   --gateway ADDR       Gateway for the machine network (none)
#   --plc-ip ADDR        CX7000 IP address (192.168.137.6)
#   --plc-netid ID       CX7000 AMS Net ID (5.177.96.78.1.1)
#   --display MODE       auto | hdmi-800x480 | dsi-5inch (auto)
#   --cpu-mhz N          Max CPU speed, lower runs cooler (1200; 0 = Pi default)
#   --keep-network       Don't set a fixed IP; leave networking as it is
#   --no-lock            Leave the SD card writable (for development)
#   --user NAME          Account that runs the HMI (the one that ran sudo)
#   --yes                Don't ask for confirmation
#   --refresh            Only reinstall the launcher, services and updater from
#                        this folder (used by the USB updater)
#
# Safe to run again: it replaces its own settings rather than adding twice.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$(dirname "$SCRIPT_DIR")"
APP_DIR=/opt/rch-steamer
VENV=/opt/rch-steamer-venv
STATE=/var/lib/rch-steamer
CONF=/etc/rch-steamer.conf
MARK_BEGIN="# >>> rch-steamer >>>"
MARK_END="# <<< rch-steamer <<<"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33mWARNING: %s\033[0m\n' "$*" >&2; }
die()  { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

overlay_active() { grep -qw 'boot=overlay' /proc/cmdline; }

# Copy a file into place atomically. A running copy of the file (e.g. the
# updater replacing itself) keeps working because it still has the old one.
install_file() {  # src dst mode
    local tmp="$2.tmp.$$"
    cp "$1" "$tmp"
    chmod "$3" "$tmp"
    mv -f "$tmp" "$2"
}

# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------
# Start from the template, then any settings already on this Pi, then options.
# shellcheck disable=SC1091
. "$SCRIPT_DIR/rch-steamer.conf"
# shellcheck disable=SC1090
[ -r "$CONF" ] && . "$CONF"

DISPLAY_MODE=auto
CPU_MHZ=1200
KEEP_NETWORK=no
NO_LOCK=no
ASSUME_YES=no
REFRESH_ONLY=no
RUN_USER="${SUDO_USER:-}"

while [ $# -gt 0 ]; do
    case "$1" in
        --pi-ip)        PI_IP="${2%/*}"
                        [[ "$2" == */* ]] && PI_PREFIX="${2#*/}"
                        shift ;;
        --gateway)      PI_GATEWAY="$2"; shift ;;
        --plc-ip)       RCH_PLC_IP="$2"; shift ;;
        --plc-netid)    RCH_PLC_AMS_NETID="$2"; shift ;;
        --display)      DISPLAY_MODE="$2"; shift ;;
        --cpu-mhz)      CPU_MHZ="$2"; shift ;;
        --keep-network) KEEP_NETWORK=yes ;;
        --no-lock)      NO_LOCK=yes ;;
        --user)         RUN_USER="$2"; shift ;;
        --yes|-y)       ASSUME_YES=yes ;;
        --refresh)      REFRESH_ONLY=yes ;;
        -h|--help)      sed -n '2,30p' "$0"; exit 0 ;;
        *)              die "Unknown option: $1 (try --help)" ;;
    esac
    shift
done

case "$DISPLAY_MODE" in auto|hdmi-800x480|dsi-5inch) ;; *)
    die "--display must be auto, hdmi-800x480 or dsi-5inch" ;; esac
[[ "$CPU_MHZ" =~ ^[0-9]+$ ]] || die "--cpu-mhz must be a number"
[[ "$PI_PREFIX" =~ ^[0-9]+$ ]] || die "--pi-ip must look like 192.168.137.20/24"

[ "$(id -u)" -eq 0 ] || die "Run this with sudo:  sudo $0"

if overlay_active; then
    die "The SD card is locked (read-only), so changes would vanish on reboot.
Unlock it first, then run this again:
    sudo raspi-config nonint disable_overlayfs && sudo reboot"
fi

# ---------------------------------------------------------------------------
# Launcher, services and updater. Also used by the USB updater (--refresh).
# ---------------------------------------------------------------------------
install_system_files() {
    local src="$1/deploy" user="$2"
    install_file "$src/kiosk-launch.sh"  /usr/local/bin/rch-kiosk-launch 755
    install_file "$src/add-plc-route.sh" /usr/local/bin/rch-add-route    755
    install_file "$src/usb-update.sh"    /usr/local/bin/rch-usb-update  755

    sed "s/@USER@/$user/" "$src/systemd/rch-kiosk.service" > /etc/systemd/system/rch-kiosk.service.tmp
    mv -f /etc/systemd/system/rch-kiosk.service.tmp /etc/systemd/system/rch-kiosk.service
    install_file "$src/systemd/rch-usb-update.service" /etc/systemd/system/rch-usb-update.service 644

    systemctl daemon-reload
    systemctl enable rch-usb-update.service rch-kiosk.service >/dev/null 2>&1
    # The kiosk takes over the screen's first console instead of a login prompt.
    systemctl disable getty@tty1.service >/dev/null 2>&1 || true
}

if [ "$REFRESH_ONLY" = yes ]; then
    user="$(cat "$STATE/hmi-user" 2>/dev/null || true)"
    [ -n "$user" ] || user="$(sed -n 's/^User=//p' /etc/systemd/system/rch-kiosk.service 2>/dev/null || true)"
    [ -n "$user" ] || die "Can't tell which account runs the HMI. Run a full install."
    install_system_files "$SRC_DIR" "$user"
    exit 0
fi

# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
[ -n "$RUN_USER" ] && [ "$RUN_USER" != root ] \
    || die "Run with sudo from your normal account, or pass --user NAME."
id "$RUN_USER" >/dev/null 2>&1 || die "Account '$RUN_USER' doesn't exist."

[ "$(uname -m)" = aarch64 ] \
    || die "This needs the 64-bit Raspberry Pi OS. Re-flash the card with
'Raspberry Pi OS Lite (64-bit)' using Raspberry Pi Imager."

# PySide6 for the Pi needs glibc 2.39+, i.e. Raspberry Pi OS based on
# Debian 13 "Trixie" or newer. Older "Bookworm" images can't install it.
GLIBC="$(ldd --version 2>/dev/null | head -1 | awk '{print $NF}')"
# shellcheck disable=SC1091
. /etc/os-release
if [ "$(printf '%s\n' 2.39 "$GLIBC" | sort -V | head -1)" != 2.39 ]; then
    die "This OS is too old (${PRETTY_NAME:-unknown}). Re-flash the card with
the current 'Raspberry Pi OS Lite (64-bit)' (Trixie or newer) using Raspberry Pi Imager."
fi

MODEL="$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo unknown)"
[[ "$MODEL" == *"Raspberry Pi 4"* ]] || warn "Built and tested for a Raspberry Pi 4; this is: $MODEL"

getent hosts pypi.org >/dev/null 2>&1 \
    || die "No internet. Setup downloads software once: plug the Pi's Ethernet
into a network with internet and try again. (The finished unit needs no internet.)"

BOOT=/boot/firmware
[ -f "$BOOT/config.txt" ] || BOOT=/boot
[ -f "$BOOT/config.txt" ] || die "Can't find config.txt in /boot/firmware or /boot."

cat <<EOF

RCH Steamer HMI installer
  Pi model .......... $MODEL
  OS ................ ${PRETTY_NAME:-unknown}
  HMI runs as ....... $RUN_USER
  Pi fixed IP ....... $( [ "$KEEP_NETWORK" = yes ] && echo "(unchanged)" || echo "$PI_IP/$PI_PREFIX${PI_GATEWAY:+ via $PI_GATEWAY}")
  PLC ............... $RCH_PLC_IP  (AMS Net ID $RCH_PLC_AMS_NETID)
  Display ........... $DISPLAY_MODE
  Max CPU ........... $( [ "$CPU_MHZ" = 0 ] && echo "Pi default" || echo "$CPU_MHZ MHz")
  Wi-Fi, Bluetooth .. turned off
  SD card ........... $( [ "$NO_LOCK" = yes ] && echo "writable" || echo "locked read-only after setup")
EOF
if [ "$ASSUME_YES" != yes ] && [ -t 0 ]; then
    read -rp $'\nContinue? [y/N] ' answer
    [[ "$answer" =~ ^[Yy] ]] || die "Cancelled."
fi

# ---------------------------------------------------------------------------
# 1. System packages (no desktop; just what Qt + cage need)
# ---------------------------------------------------------------------------
say "Installing system packages (a few minutes)"
apt-get update -q
WANTED=(
    cage                                   # one-app display server (kiosk)
    python3-venv python3-pip
    unzip rsync git ca-certificates raspi-config console-setup
    libgl1-mesa-dri libegl-mesa0 libgbm1   # GPU drivers
    libegl1 libgl1 libgles2
    libwayland-client0 libwayland-cursor0 libwayland-egl1
    libxkbcommon0 libfontconfig1 libfreetype6 libdbus-1-3
    "libglib2.0-0t64|libglib2.0-0"
    fonts-dejavu-core
)
PKGS=()
for entry in "${WANTED[@]}"; do
    found=""
    IFS='|' read -ra choices <<< "$entry"
    for p in "${choices[@]}"; do
        if apt-cache show "$p" >/dev/null 2>&1; then found="$p"; break; fi
    done
    if [ -n "$found" ]; then PKGS+=("$found"); else warn "Package not available, skipping: $entry"; fi
done
DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends "${PKGS[@]}"
command -v cage >/dev/null || die "cage didn't install; it's required for the kiosk."

# ---------------------------------------------------------------------------
# 2. App files and Python packages
# ---------------------------------------------------------------------------
say "Copying the HMI to $APP_DIR"
if [ "$SRC_DIR" != "$APP_DIR" ]; then
    mkdir -p "$APP_DIR"
    rsync -a --delete --exclude '.git/' --exclude '__pycache__/' --exclude 'deploy/wheels/' \
        "$SRC_DIR/" "$APP_DIR/"
fi
chown -R root:root "$APP_DIR"

say "Installing Python packages (PySide6, pyads)"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --disable-pip-version-check -r "$APP_DIR/requirements.txt"
"$VENV/bin/python" -c "import PySide6.QtWidgets, PySide6.QtUiTools, pyads" \
    || die "Python packages didn't import correctly."
"$VENV/bin/python" -m compileall -q "$APP_DIR" >/dev/null || true

mkdir -p "$STATE"
cp "$APP_DIR/requirements.txt" "$STATE/requirements.installed"
echo "$RUN_USER" > "$STATE/hmi-user"
rm -f "$STATE/applied-sha" "$STATE/failed-sha"
{
    echo "installed $(date '+%Y-%m-%d %H:%M')"
    git -C "$SRC_DIR" log -1 --format='commit %h  %s  (%cd)' --date=short 2>/dev/null || true
} > "$STATE/version"

# ---------------------------------------------------------------------------
# 3. Settings file, launcher and services
# ---------------------------------------------------------------------------
say "Writing settings to $CONF and installing the kiosk service"
set_key() {  # key value: replace the value, keep any comment after it
    sed -i -E "s|^$1=[^#]*(#.*)?$|$1=$2  \1|; s|[[:space:]]+$||" "$CONF"
}
cp "$SCRIPT_DIR/rch-steamer.conf" "$CONF"
set_key PI_IP "$PI_IP"
set_key PI_PREFIX "$PI_PREFIX"
set_key PI_GATEWAY "$PI_GATEWAY"
set_key RCH_PLC_IP "$RCH_PLC_IP"
set_key RCH_PLC_AMS_NETID "$RCH_PLC_AMS_NETID"
set_key RCH_LOCAL_AMS_NETID "${RCH_LOCAL_AMS_NETID:-}"
set_key LOCK_SD "$( [ "$NO_LOCK" = yes ] && echo no || echo yes )"
chmod 644 "$CONF"

install_system_files "$APP_DIR" "$RUN_USER"
usermod -aG video,render,input "$RUN_USER"

# ---------------------------------------------------------------------------
# 4. Boot settings: Wi-Fi/Bluetooth off, CPU cap, display, quiet boot
# ---------------------------------------------------------------------------
say "Updating boot settings in $BOOT"
sed -i "/^$MARK_BEGIN/,/^$MARK_END/d" "$BOOT/config.txt"
{
    echo "$MARK_BEGIN  (managed by rch-steamer deploy/install.sh)"
    echo "[all]"
    echo "dtoverlay=disable-wifi"
    echo "dtoverlay=disable-bt"
    echo "disable_splash=1"
    [ "$CPU_MHZ" != 0 ] && echo "arm_freq=$CPU_MHZ"
    case "$DISPLAY_MODE" in
        hdmi-800x480) echo "hdmi_force_hotplug=1" ;;
        dsi-5inch)    echo "dtoverlay=vc4-kms-dsi-waveshare-panel,5_0_inch" ;;
    esac
    echo "$MARK_END"
} >> "$BOOT/config.txt"

# cmdline.txt is a single line of space-separated settings.
CMDLINE="$BOOT/cmdline.txt"
read -r -a tokens < "$CMDLINE"
new=()
for t in "${tokens[@]}"; do
    [[ "$t" == video=HDMI-A-1:* ]] && continue      # we re-add it below if needed
    new+=("$t")
done
for t in quiet loglevel=3 logo.nologo; do
    [[ " ${new[*]} " == *" $t "* ]] || new+=("$t")
done
[ "$DISPLAY_MODE" = hdmi-800x480 ] && new+=("video=HDMI-A-1:800x480@60D")
echo "${new[*]}" > "$CMDLINE"

# ---------------------------------------------------------------------------
# 5. Lighter, sturdier system
# ---------------------------------------------------------------------------
say "Turning off unused services, enabling the watchdog"
for svc in bluetooth.service hciuart.service ModemManager.service dphys-swapfile.service; do
    systemctl disable --now "$svc" >/dev/null 2>&1 || true
done

# Hardware watchdog: if the Pi ever freezes, it reboots itself.
mkdir -p /etc/systemd/system.conf.d
cat > /etc/systemd/system.conf.d/rch-watchdog.conf <<'EOF'
[Manager]
RuntimeWatchdogSec=14
RebootWatchdogSec=2min
EOF

# Keep logs in memory rather than writing them to the SD card.
mkdir -p /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/rch.conf <<'EOF'
[Journal]
Storage=volatile
RuntimeMaxUse=32M
EOF

# ---------------------------------------------------------------------------
# 6. Fixed IP on the machine network (takes effect at next boot)
# ---------------------------------------------------------------------------
if [ "$KEEP_NETWORK" = no ]; then
    if command -v nmcli >/dev/null; then
        say "Setting fixed IP $PI_IP/$PI_PREFIX (takes effect after reboot)"
        nmcli connection delete rch-machine-net >/dev/null 2>&1 || true
        args=(type ethernet ifname eth0 con-name rch-machine-net
              ipv4.method manual ipv4.addresses "$PI_IP/$PI_PREFIX"
              ipv6.method disabled
              connection.autoconnect yes connection.autoconnect-priority 100)
        if [ -n "$PI_GATEWAY" ]; then args+=(ipv4.gateway "$PI_GATEWAY")
        else args+=(ipv4.never-default yes); fi
        nmcli connection add "${args[@]}" >/dev/null
        # Stop the normal "get an address automatically" profile from taking over.
        while IFS=: read -r name type; do
            [ "$type" = 802-3-ethernet ] && [ "$name" != rch-machine-net ] \
                && nmcli connection modify "$name" connection.autoconnect no
        done < <(nmcli -t -f NAME,TYPE connection show)
    else
        warn "NetworkManager (nmcli) not found; fixed IP not set."
    fi
fi

# ---------------------------------------------------------------------------
# 7. Lock the SD card read-only (takes effect at next boot)
# ---------------------------------------------------------------------------
if [ "$NO_LOCK" = no ]; then
    say "Locking the SD card read-only (takes a minute)"
    raspi-config nonint enable_overlayfs \
        || warn "Couldn't enable the read-only lock. Try: sudo raspi-config > Performance > Overlay File System"
fi

cat <<EOF

$(printf '\033[1;32m')Done.$(printf '\033[0m') Reboot to start the HMI:   sudo reboot

After rebooting, the Pi only talks on the machine network at $PI_IP.
Next steps (see deploy/README.md):
  - If the PLC doesn't have a route for this Pi yet, plug the Pi into the
    machine and run:  rch-add-route
  - To make copies, shut down (sudo poweroff) and save the card as an image.
EOF
