import pyads

# --- Fill these in for your network ---
PI_IP        = "192.168.1.20"        # the RPi's IP
PI_NETID     = "192.168.1.20.1.1"    # RPi AMS Net ID = its IP + ".1.1"
PLC_IP       = "192.168.1.10"        # the CX7000's IP
PLC_USER     = "Administrator"       # CX7000 Windows/CE login
PLC_PASS     = "1"                   # default CX7000 password is often "1"
ROUTE_NAME   = "HMI"                 # any label you like

pyads.open_port()

# 1. Tell pyads what THIS machine's AMS Net ID is
pyads.set_local_address(PI_NETID)

# 2. Push a route INTO the CX7000's route table so it will accept us
pyads.add_route_to_plc(
    sending_net_id=PI_NETID,
    adding_host_name=PI_IP,      # how the PLC will reach back to the Pi
    ip_address=PLC_IP,           # the PLC we're adding the route to
    username=PLC_USER,
    password=PLC_PASS,
    route_name=ROUTE_NAME,
)

pyads.close_port()
print("Route added.")