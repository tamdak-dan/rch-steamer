# RCH Steamer HMI on a Raspberry Pi — Setup Guide

The goal: one **master SD card image** that boots straight into the HMI, full screen, with no desktop. You build it once, save it to a file, and copy that file onto a new card for every unit. To update software later, see **[UPDATING.md](UPDATING.md)** (USB stick, no Wi-Fi needed).

**What the finished unit does:** boots to the HMI in about 30 seconds · no desktop, Wi-Fi or Bluetooth (runs cool) · CPU capped at 1.2 GHz · restarts the app if it ever crashes · reboots itself if it ever freezes · SD card locked read-only so power cuts can't corrupt it.

## You need

- Raspberry Pi 4, touchscreen, power supply, heatsink case (passive aluminum recommended)
- A **high-endurance or industrial SD card** (16 GB or larger). Buy the same model for every unit.
- For the one-time build only: a USB keyboard, and an Ethernet cable to a network **with internet**
- A Windows or Mac PC with [Raspberry Pi Imager](https://www.raspberrypi.com/software/)

## Part A — Build the master card (once, about 20 minutes)

1. **Flash the OS.** In Raspberry Pi Imager choose *Raspberry Pi 4* → *Raspberry Pi OS (other)* → **Raspberry Pi OS Lite (64-bit)** → your SD card. When asked to customise, set a **username and password** (write them down). Skip Wi-Fi. Turn on SSH only if you want laptop access later.
2. **Boot the Pi** with the keyboard, screen and internet Ethernet plugged in. Log in with the username and password from step 1.
3. **Run the installer** (type these exactly):
   ```
   sudo apt install -y git
   git clone https://github.com/tamdak-dan/rch-steamer.git
   sudo rch-steamer/deploy/install.sh
   ```
   It shows a summary and asks to continue. The defaults match the bench setup: Pi at `192.168.137.20`, PLC at `192.168.137.6`. If your machine network is different, add options, for example:
   ```
   sudo rch-steamer/deploy/install.sh --pi-ip 192.168.1.20/24 --plc-ip 192.168.1.10 --plc-netid 5.177.96.78.1.1
   ```
   Run `rch-steamer/deploy/install.sh --help` for all options.
4. **Reboot:** `sudo reboot`. The HMI should fill the screen. If the picture is wrong, see *Screen troubleshooting* below.
5. **Connect to the PLC.** Plug the Pi into the machine network. If the HMI shows "disconnected", the PLC needs a route for this Pi (once per PLC). Press **Ctrl+Alt+F2**, log in, run `rch-add-route`, and enter the PLC's login. Press **Ctrl+Alt+F1** to go back to the HMI.

## Part B — Save the master image

1. On the Pi: press Ctrl+Alt+F2, log in, run `sudo poweroff`. Wait for the green light to stop, then remove the card.
2. Put the card in your PC and save it to a file:
   - **Windows:** install [Win32 Disk Imager](https://sourceforge.net/projects/win32diskimager/). Type a file name like `rch-steamer-2026-11-01.img`, pick the SD card's drive letter, tick **Read Only Allocated Partitions**, click **Read**.
   - **Mac:** in Terminal, `diskutil list` to find the card (e.g. `/dev/disk4`), then `diskutil unmountDisk /dev/disk4` and `sudo dd if=/dev/rdisk4 of=rch-steamer-2026-11-01.img bs=4m`.
3. Keep this `.img` file somewhere safe (a shared drive). It is your master copy.

## Part C — Make a new unit (5 minutes, no Linux needed)

1. In Raspberry Pi Imager: *Choose OS* → **Use custom** → pick the `.img` file → pick the new SD card.
2. When asked about OS customisation, choose **No** (the image already has everything).
3. Write, put the card in the Pi, power on. Done.

Every unit made this way has the same IP address. That's fine when each machine has its own network. If two Pis ever share a network, change one unit's address (UPDATING.md, *Changing a unit's settings*).

## Screen troubleshooting

The installer assumes a touchscreen that works when plugged in ("auto"). If the screen stays black or the picture is the wrong size, rerun the installer with the option for your screen (needs the internet cable again, and unlock first: `sudo raspi-config nonint disable_overlayfs && sudo reboot`):

| Screen | Option |
|---|---|
| Waveshare 5" **HDMI** (800×480) | `--display hdmi-800x480` |
| Waveshare 5" **DSI** (ribbon cable) | `--display dsi-5inch` |

For other screens, check the maker's setup page for the `config.txt` lines it needs.
