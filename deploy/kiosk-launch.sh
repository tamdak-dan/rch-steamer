#!/usr/bin/env bash
# Starts the RCH Steamer HMI full screen. Run by the kiosk service inside
# "cage" (a tiny display server that shows exactly one app, no desktop).
# Installed on the Pi as /usr/local/bin/rch-kiosk-launch.
set -euo pipefail

APP_DIR=/opt/rch-steamer
VENV=/opt/rch-steamer-venv

# shellcheck disable=SC1091
[ -r /etc/rch-steamer.conf ] && . /etc/rch-steamer.conf

export RCH_KIOSK=1
export RCH_PLC_IP="${RCH_PLC_IP:-}"
export RCH_PLC_AMS_NETID="${RCH_PLC_AMS_NETID:-}"
if [ -z "${RCH_LOCAL_AMS_NETID:-}" ] && [ -n "${PI_IP:-}" ]; then
    RCH_LOCAL_AMS_NETID="${PI_IP}.1.1"
fi
export RCH_LOCAL_AMS_NETID="${RCH_LOCAL_AMS_NETID:-}"

# Unset values would override the app's built-in defaults with "", so drop them.
[ -n "$RCH_PLC_IP" ] || unset RCH_PLC_IP
[ -n "$RCH_PLC_AMS_NETID" ] || unset RCH_PLC_AMS_NETID
[ -n "$RCH_LOCAL_AMS_NETID" ] || unset RCH_LOCAL_AMS_NETID

# Draw through cage (Wayland), with no window title bar.
export QT_QPA_PLATFORM=wayland
export QT_WAYLAND_DISABLE_WINDOWDECORATION=1

# Rotate the screen if asked (SCREEN_ROTATE in /etc/rch-steamer.conf).
# cage has no rotate option of its own; wlr-randr asks it to rotate each
# output. Touch input follows the rotation.
if [ "${SCREEN_ROTATE:-0}" != 0 ] && command -v wlr-randr >/dev/null; then
    for output in $(wlr-randr 2>/dev/null | awk '/^[^ \t]/ {print $1}'); do
        wlr-randr --output "$output" --transform "$SCREEN_ROTATE" || true
    done
fi

cd "$APP_DIR"
exec "$VENV/bin/python" app.py
