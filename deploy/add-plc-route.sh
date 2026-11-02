#!/usr/bin/env bash
# Adds this Pi to the CX7000's list of allowed ADS connections ("route").
# Needed once per PLC, with the Pi plugged into the machine network.
# Installed on the Pi as /usr/local/bin/rch-add-route.
#
# Alternative: add the route permanently in the TwinCAT project instead,
# then this step is never needed in the field.
set -euo pipefail

# shellcheck disable=SC1091
. /etc/rch-steamer.conf
LOCAL_NETID="${RCH_LOCAL_AMS_NETID:-}"
[ -n "$LOCAL_NETID" ] || LOCAL_NETID="${PI_IP}.1.1"

echo "Adding a route on the PLC at ${RCH_PLC_IP}"
echo "  for this Pi: ${PI_IP}  (AMS Net ID ${LOCAL_NETID})"
read -rp "PLC user name [Administrator]: " PLC_USER
PLC_USER="${PLC_USER:-Administrator}"
read -rsp "PLC password: " PLC_PASS
echo

# Pass secrets through the environment rather than the command line, so
# they don't show up in the process list.
RCH_ROUTE_USER="$PLC_USER" RCH_ROUTE_PASS="$PLC_PASS" \
RCH_ROUTE_LOCAL="$LOCAL_NETID" RCH_ROUTE_PI_IP="$PI_IP" RCH_ROUTE_PLC_IP="$RCH_PLC_IP" \
/opt/rch-steamer-venv/bin/python - <<'EOF'
import os
import sys

import pyads

env = os.environ
try:
    pyads.open_port()
    pyads.set_local_address(env["RCH_ROUTE_LOCAL"])
    pyads.add_route_to_plc(
        sending_net_id=env["RCH_ROUTE_LOCAL"],
        adding_host_name=env["RCH_ROUTE_PI_IP"],
        ip_address=env["RCH_ROUTE_PLC_IP"],
        username=env["RCH_ROUTE_USER"],
        password=env["RCH_ROUTE_PASS"],
        route_name="RCH-HMI-" + env["RCH_ROUTE_PI_IP"],
    )
    pyads.close_port()
except Exception as e:  # show a plain message instead of a traceback
    print(f"Could not add the route: {e}")
    print("Check the PLC IP, the cable, and the user name/password.")
    sys.exit(1)
print("Route added. The HMI should connect within a few seconds.")
EOF
