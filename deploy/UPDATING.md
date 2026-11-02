# Updating and Modifying the RCH Steamer HMI

The Pis have no Wi-Fi or internet, so new software goes in on a **USB stick**. The Pi checks for a stick every time it starts.

## Part 1 — Update a screen (technician, about 5 minutes)

**Get the latest software (on any PC with internet):**

1. Go to https://github.com/tamdak-dan/rch-steamer
2. Click the green **Code** button → **Download ZIP**. You get `rch-steamer-main.zip`.
   - For a specific released version instead: open **Releases** on the right, and under *Assets* download **Source code (zip)** (e.g. `rch-steamer-1.2.zip`).

**Put it on a USB stick:**

3. Copy the ZIP into the **top folder** of a USB stick (FAT32 or exFAT, which is how most sticks come). **Don't unzip it.** You can rename it, but the name must start with `rch-steamer-` and end in `.zip`.

**Install it:**

4. Plug the stick into the Pi and turn the power off and on.
5. The screen shows **RCH STEAMER – SOFTWARE UPDATE** and progress messages. The Pi may restart **twice** (it unlocks the SD card, installs, then locks it again). This takes 2–4 minutes. Don't turn the power off.
6. When the screen says **REMOVE THE USB STICK NOW**, or when the HMI appears, remove the stick.

If you forget the stick, nothing bad happens: each ZIP is installed only once.

**If the screen shows an error,** the old version stays installed and keeps running. Remove the stick and tell engineering what the screen said. The most common causes are a ZIP that isn't the HMI, or an update that needs new Python packages (see Part 2).

## Part 2 — Make changes to the software (engineering)

**Normal workflow:**

1. Edit the code on your PC and test it there with `python app.py`. It opens as a normal window. (Your PC needs an ADS route on the PLC to connect, same as before.)
2. Commit and push to GitHub. `main` is what technicians get from **Download ZIP**, so push there only when it's ready for the floor.
3. Optional but recommended: make a **Release** on GitHub (e.g. tag `v1.2`). Technicians can then grab a known version, and you can tell which version a unit runs.
4. Test on one bench Pi with a USB stick (Part 1) before rolling out.

**Rules that keep USB updates working:**

- Keep `app.py`, `requirements.txt` and the `deploy/` folder at the top of the repo. The updater refuses ZIPs without them.
- The app can't download anything at runtime. No internet in the field.
- Don't rely on files the app writes to the Pi. The SD card is read-only while running, so anything written is lost at the next restart. Settings that need to stick belong in the PLC, as they are today.
- Changes to the launcher, services or updater in `deploy/` are picked up automatically by the next USB update.

**If you add a Python package:** add it to `requirements.txt`, then download Pi-compatible copies of the packages on your PC (with internet):

```
pip download -r requirements.txt --only-binary=:all: --platform manylinux_2_39_aarch64 --python-version 3.13 -d rch-wheels
```

Copy the resulting **`rch-wheels`** folder onto the USB stick, next to the ZIP. The updater installs the packages from there. Without it, the update stops and keeps the old version. (`3.13` is the Python on Raspberry Pi OS Trixie; check with `python3 --version` on a Pi.)

## Part 3 — Service tasks on a unit

**Getting to a command line:** plug a USB keyboard into the Pi and press **Ctrl+Alt+F2**, then log in. **Ctrl+Alt+F1** returns to the HMI. (Or SSH from a laptop on the machine network, if SSH was turned on when the master card was built.)

| Task | Command |
|---|---|
| See installed version and update history | `rch-usb-update --status` |
| Restart the HMI | `sudo systemctl restart rch-kiosk` |
| See the HMI's error messages | `journalctl -u rch-kiosk -n 50` |
| Add the Pi's ADS route to a PLC | `rch-add-route` |
| Unlock the SD card (then reboot) | `sudo raspi-config nonint disable_overlayfs && sudo reboot` |
| Lock the SD card (then reboot) | `sudo raspi-config nonint enable_overlayfs && sudo reboot` |
| Go back to the previous version (unlock first) | `sudo rch-usb-update --rollback` |
| Install a ZIP from a mounted stick (unlock first) | `sudo rch-usb-update /path/to/rch-steamer-main.zip` |

**Changing a unit's settings** (its IP address, or the PLC's address and AMS Net ID). No new software needed:

1. Unlock the SD card (command above) and reboot.
2. `sudo nano /etc/rch-steamer.conf`, change the values, save with Ctrl+O, exit with Ctrl+X.
3. If you changed `PI_IP` or `PI_PREFIX`, also apply it to the network:
   ```
   sudo nmcli connection modify rch-machine-net ipv4.addresses NEW_IP/24
   ```
4. Lock the SD card again (command above) and reboot.
5. If the Pi's IP changed, the PLC needs a new route: run `rch-add-route`.

**Bigger system changes** (different screen, OS updates): build a new master card with `install.sh` on a fresh card (README.md, Part A) and save a new image. It's quicker and safer than changing units in the field.

## What's in `deploy/`

| File | What it does |
|---|---|
| `install.sh` | One-time setup of a fresh Raspberry Pi OS Lite card |
| `kiosk-launch.sh` | Starts the HMI full screen (installed as `rch-kiosk-launch`) |
| `usb-update.sh` | The USB updater (installed as `rch-usb-update`) |
| `add-plc-route.sh` | Adds the Pi's ADS route to the PLC (installed as `rch-add-route`) |
| `rch-steamer.conf` | Default settings, copied to `/etc/rch-steamer.conf` |
| `systemd/` | Boot services for the HMI and the updater |
