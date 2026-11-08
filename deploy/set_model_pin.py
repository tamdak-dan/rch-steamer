"""Set the model-change PIN on this Pi.

Installed as `rch-set-pin`. Run it from a login prompt (maintenance stick):

    sudo rch-set-pin            set a new PIN (asks twice)
    sudo rch-set-pin --default  go back to the built-in default PIN
    rch-set-pin --status        show whether a custom PIN is set

Works while the SD card is locked: the PIN lives on the boot partition.
"""
import getpass
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui.pin_store import PIN_MAX, PIN_MIN, has_custom_pin, hash_pin, pin_file, valid_pin  # noqa: E402


def boot_mount_options(path):
    """Mount options of the filesystem holding path, e.g. 'rw,relatime,...'."""
    try:
        return subprocess.run(["findmnt", "-n", "-o", "OPTIONS", "--target", os.path.dirname(path)],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def write_boot_file(path, text):
    """Write path atomically; remount its partition read-write if needed."""
    mount_point = os.path.dirname(path)
    was_ro = boot_mount_options(path).split(",")[0] == "ro"
    if was_ro:
        subprocess.run(["mount", "-o", "remount,rw", mount_point], check=True)
    try:
        if text is None:
            if os.path.exists(path):
                os.remove(path)
        else:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="ascii") as f:
                f.write(text + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        os.sync()
    finally:
        if was_ro:
            subprocess.run(["mount", "-o", "remount,ro", mount_point], check=False)


def main(argv):
    arg = argv[1] if len(argv) > 1 else ""
    path = pin_file()

    if arg in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    if arg == "--status":
        print("Model-change PIN:", "custom PIN is set" if has_custom_pin() else "built-in default")
        print("Stored in:", path)
        return 0
    if arg not in ("", "--default"):
        print(f"Unknown option: {arg}  (try --help)")
        return 1
    if os.geteuid() != 0:
        print("Run this with sudo:  sudo rch-set-pin" + (f" {arg}" if arg else ""))
        return 1

    if arg == "--default":
        write_boot_file(path, None)
        print("Done. The model-change PIN is back to the built-in default.")
        return 0

    print(f"Set the PIN for changing the steamer model (25/50 SLM) on the System page.")
    print(f"Use {PIN_MIN}-{PIN_MAX} digits. Nothing shows on screen while you type.")
    for _ in range(3):
        try:
            pin = getpass.getpass("New PIN: ")
            if not valid_pin(pin):
                print(f"The PIN must be {PIN_MIN}-{PIN_MAX} digits (0-9 only). Try again.")
                continue
            if getpass.getpass("Same PIN again: ") != pin:
                print("The two PINs didn't match. Try again.")
                continue
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled. PIN not changed.")
            return 1
        write_boot_file(path, hash_pin(pin))
        print("Done. The new PIN works right away; no restart needed.")
        return 0
    print("PIN not changed.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
