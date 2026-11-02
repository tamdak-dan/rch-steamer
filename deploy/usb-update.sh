#!/usr/bin/env bash
# =============================================================================
# RCH Steamer HMI - offline updater (no Wi-Fi or internet needed)
# =============================================================================
# Installed on the Pi as /usr/local/bin/rch-usb-update. Runs at every boot,
# before the HMI starts.
#
# How a technician uses it:
#   1. Put the GitHub ZIP (named rch-steamer-<something>.zip, e.g. the
#      "rch-steamer-main.zip" GitHub gives you) in the top folder of a USB stick.
#   2. Plug the stick into the Pi and power-cycle it.
#   3. Wait. The screen shows progress; the Pi may reboot twice.
#   4. When the HMI appears, remove the stick.
#
# Other uses (from a keyboard or SSH):
#   sudo rch-usb-update /path/to/rch-steamer-main.zip   install a ZIP now
#   sudo rch-usb-update --rollback                      go back one version
#   rch-usb-update --status                             show installed version
#
# If the SD card is locked (read-only), the updater unlocks it, reboots,
# installs, locks it again and reboots. Each ZIP is installed only once, so
# leaving the stick plugged in doesn't cause repeat updates.
# =============================================================================
set -uo pipefail

APP_DIR=/opt/rch-steamer
VENV=/opt/rch-steamer-venv
STATE=/var/lib/rch-steamer
CONF=/etc/rch-steamer.conf
WORK=/run/rch-update
MNT=/run/rch-usb
ZIP_PATTERN='rch-steamer-*.zip'     # hyphen: won't match rch-steamer_TwinCAT
WHEELS_DIR_NAME=rch-wheels          # optional folder on the stick (new packages)

LOCK_SD=yes
# shellcheck disable=SC1090
[ -r "$CONF" ] && . "$CONF"

TTY=/dev/tty1
SCREEN=no      # show messages on the touchscreen (boot mode)

# ---------------------------------------------------------------------------
# Messages: to the log, and in large text on the touchscreen during boot
# ---------------------------------------------------------------------------
say() {
    echo "$*"
    if [ "$SCREEN" = yes ]; then printf '  %s\n' "$*" > "$TTY" 2>/dev/null || true; fi
}
screen_start() {
    SCREEN=yes
    setfont -C "$TTY" Uni3-TerminusBold32x16 2>/dev/null || true
    printf '\033c\n  RCH STEAMER - SOFTWARE UPDATE\n\n' > "$TTY" 2>/dev/null || true
}
log_history() {
    mkdir -p "$STATE"
    echo "$(date '+%Y-%m-%d %H:%M')  $*" >> "$STATE/update-history.log"
}

overlay_active() { grep -qw 'boot=overlay' /proc/cmdline; }

reboot_now() {
    say "$1"
    sleep 4
    systemctl reboot
    exit 0
}

# Lock the card again if this unit is set up to be locked.
relock_if_needed() {
    if [ "$LOCK_SD" = yes ] && ! overlay_active; then
        say "Locking SD card (about 1 minute)..."
        raspi-config nonint enable_overlayfs >/dev/null 2>&1 \
            || say "WARNING: could not lock SD card."
        return 0
    fi
    return 1
}

# ---------------------------------------------------------------------------
# Find an update ZIP on any USB stick. Copies it (and any rch-wheels folder)
# into $WORK, which is in memory. Sets PKG_NAME. Returns 1 if none found.
# ---------------------------------------------------------------------------
find_usb_package() {
    local waited=0 devs dev found
    # USB sticks show up a moment after boot; wait up to ~3 s for one.
    udevadm settle --timeout=5 >/dev/null 2>&1 || true
    while :; do
        devs=$(ls /dev/disk/by-id/usb-* 2>/dev/null || true)
        [ -n "$devs" ] && break
        [ "$waited" -ge 3 ] && return 1
        sleep 1; waited=$((waited + 1))
    done
    udevadm settle --timeout=5 >/dev/null 2>&1 || true
    devs=$(ls /dev/disk/by-id/usb-* 2>/dev/null || true)

    mkdir -p "$MNT" "$WORK"
    for dev in $(for d in $devs; do readlink -f "$d"; done | sort -u); do
        mount -o ro "$dev" "$MNT" 2>/dev/null || continue
        found=$(find "$MNT" -maxdepth 1 -type f -iname "$ZIP_PATTERN" -printf '%T@ %p\n' 2>/dev/null \
                | sort -nr | head -1 | cut -d' ' -f2-)
        if [ -n "$found" ]; then
            PKG_NAME=$(basename "$found")
            cp "$found" "$WORK/update.zip"
            rm -rf "$WORK/wheels"
            [ -d "$MNT/$WHEELS_DIR_NAME" ] && cp -r "$MNT/$WHEELS_DIR_NAME" "$WORK/wheels"
            umount "$MNT"
            return 0
        fi
        umount "$MNT"
    done
    return 1
}

# ---------------------------------------------------------------------------
# Install $WORK/update.zip. Old version is kept in $APP_DIR.prev.
# ---------------------------------------------------------------------------
apply_package() {
    local x="$WORK/x" root new="$APP_DIR.new" wheels=""

    say "Checking update file..."
    rm -rf "$x" && mkdir -p "$x"
    unzip -q "$WORK/update.zip" -d "$x" 2>/dev/null || { say "ERROR: file is not a valid ZIP."; return 1; }
    root=$(find "$x" -maxdepth 2 -type f -name app.py -printf '%h\n' | head -1)
    if [ -z "$root" ] || [ ! -f "$root/deploy/install.sh" ]; then
        say "ERROR: this ZIP is not the RCH Steamer HMI."
        return 1
    fi

    rm -rf "$new"
    cp -a "$root/." "$new/"
    find "$new" -name __pycache__ -type d -prune -exec rm -rf {} +

    # New Python packages? The Pi has no internet, so they must come with the
    # update: in deploy/wheels inside the ZIP, or an rch-wheels folder on the stick.
    if ! cmp -s "$new/requirements.txt" "$STATE/requirements.installed"; then
        say "Installing new Python packages..."
        [ -d "$new/deploy/wheels" ] && wheels="$new/deploy/wheels"
        [ -d "$WORK/wheels" ] && wheels="$WORK/wheels"
        if [ -z "$wheels" ] || ! "$VENV/bin/pip" install -q --disable-pip-version-check \
                --no-index --find-links "$wheels" -r "$new/requirements.txt"; then
            say "ERROR: this update needs Python packages"
            say "that were not on the USB stick."
            say "See deploy/UPDATING.md. Old version kept."
            rm -rf "$new"
            return 1
        fi
        cp "$new/requirements.txt" "$STATE/requirements.installed"
    fi
    rm -rf "$new/deploy/wheels"
    chown -R root:root "$new"
    "$VENV/bin/python" -m compileall -q "$new" >/dev/null 2>&1 || true

    say "Installing new version..."
    rm -rf "$APP_DIR.prev"
    [ -d "$APP_DIR" ] && mv "$APP_DIR" "$APP_DIR.prev"
    mv "$new" "$APP_DIR"

    # Pick up any changes to the launcher, services or this updater.
    if ! "$APP_DIR/deploy/install.sh" --refresh; then
        say "ERROR: setup step failed. Restoring old version."
        rm -rf "$APP_DIR"
        mv "$APP_DIR.prev" "$APP_DIR"
        "$APP_DIR/deploy/install.sh" --refresh || true
        return 1
    fi
    return 0
}

do_rollback() {
    [ -d "$APP_DIR.prev" ] || { echo "No previous version to go back to."; exit 1; }
    if overlay_active; then
        echo "The SD card is locked. Unlock it first:"
        echo "  sudo raspi-config nonint disable_overlayfs && sudo reboot"
        exit 1
    fi
    mv "$APP_DIR" "$APP_DIR.rollback-tmp"
    mv "$APP_DIR.prev" "$APP_DIR"
    mv "$APP_DIR.rollback-tmp" "$APP_DIR.prev"
    "$APP_DIR/deploy/install.sh" --refresh || true
    # The previous version's requirements may differ; record what's in place.
    cp "$APP_DIR/requirements.txt" "$STATE/requirements.installed" 2>/dev/null || true
    rm -f "$STATE/applied-sha"
    echo "rolled back $(date '+%Y-%m-%d %H:%M') to the previous version" > "$STATE/version"
    log_history "rolled back (swapped current and previous version)"
    echo "Rolled back. Restarting the HMI..."
    systemctl restart rch-kiosk.service
    echo "Remember to lock the SD card again if this unit is normally locked:"
    echo "  sudo raspi-config nonint enable_overlayfs && sudo reboot"
}

show_status() {
    echo "Installed: $(cat "$STATE/version" 2>/dev/null || echo unknown)"
    echo "SD card:   $(overlay_active && echo 'locked (read-only)' || echo 'unlocked (writable)')"
    [ -d "$APP_DIR.prev" ] && echo "A previous version is kept (rollback available)."
    echo "Recent updates:"
    tail -5 "$STATE/update-history.log" 2>/dev/null || echo "  (none)"
}

# ---------------------------------------------------------------------------
main() {
    local mode="${1:-}" sha
    case "$mode" in
        --status)   show_status; exit 0 ;;
        --rollback) [ "$(id -u)" -eq 0 ] || { echo "Run with sudo."; exit 1; }
                    do_rollback; exit 0 ;;
        -h|--help)  sed -n '2,24p' "$0"; exit 0 ;;
    esac
    [ "$(id -u)" -eq 0 ] || { echo "Run with sudo."; exit 1; }

    mkdir -p "$WORK" "$STATE"
    PKG_NAME=""
    if [ "$mode" = --boot ]; then
        find_usb_package || exit 0          # no stick or no ZIP: normal boot
        screen_start
    elif [ -n "$mode" ] && [ -f "$mode" ]; then
        PKG_NAME=$(basename "$mode")
        cp "$mode" "$WORK/update.zip"
    else
        echo "Usage: sudo rch-usb-update /path/to/rch-steamer-<version>.zip  (or --help)"
        exit 1
    fi

    sha=$(sha256sum "$WORK/update.zip" | cut -c1-64)

    if [ "$sha" = "$(cat "$STATE/applied-sha" 2>/dev/null)" ]; then
        say "$PKG_NAME is already installed."
        [ "$SCREEN" = yes ] && { say "You can remove the USB stick."; sleep 4; }
        exit 0
    fi
    if [ "$sha" = "$(cat "$STATE/failed-sha" 2>/dev/null)" ]; then
        say "$PKG_NAME failed to install before."
        say "Remove the USB stick. Starting old version."
        [ "$SCREEN" = yes ] && sleep 10
        exit 0
    fi

    say "Found update: $PKG_NAME"

    if overlay_active && [ "$mode" != --boot ]; then
        echo "The SD card is locked. Either use the USB stick method (plug in,"
        echo "power-cycle), or unlock first and run this again:"
        echo "  sudo raspi-config nonint disable_overlayfs && sudo reboot"
        exit 1
    fi
    if overlay_active; then
        # Can't write while locked: unlock, reboot, and we'll be back here.
        say "Unlocking SD card (about 1 minute)..."
        if ! raspi-config nonint disable_overlayfs >/dev/null 2>&1; then
            say "ERROR: could not unlock SD card."
            say "Starting old version."
            sleep 10
            exit 0
        fi
        reboot_now "Restarting to continue the update..."
    fi

    if apply_package; then
        echo "$sha" > "$STATE/applied-sha"
        rm -f "$STATE/failed-sha"
        echo "updated $(date '+%Y-%m-%d %H:%M') from $PKG_NAME" > "$STATE/version"
        log_history "installed $PKG_NAME (sha256 ${sha:0:12})"
        say "Update installed."
        say "REMOVE THE USB STICK NOW."
        relock_if_needed && reboot_now "Restarting..."
        [ "$mode" != --boot ] && systemctl restart rch-kiosk.service
    else
        echo "$sha" > "$STATE/failed-sha"
        log_history "FAILED to install $PKG_NAME (sha256 ${sha:0:12})"
        say "Remove the USB stick."
        relock_if_needed && reboot_now "Restarting with the old version..."
        [ "$SCREEN" = yes ] && sleep 10
    fi
    exit 0
}

main "$@"
exit $?
