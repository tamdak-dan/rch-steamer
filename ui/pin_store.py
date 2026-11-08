"""Model-change PIN: where it's stored and how it's checked.

The PIN is set on the Pi with `sudo rch-set-pin` (deploy/set_model_pin.py)
and stored as a salted, slow hash in a small file on the SD card's boot
partition. That partition isn't covered by the read-only lock, so a new PIN
sticks without unlocking the card, and USB updates never overwrite it.

File format (one line):
    pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>

With no PIN file (e.g. on a development PC), the built-in default PIN is used.
"""
import hashlib
import hmac
import os
import secrets

# Override with RCH_PIN_FILE (e.g. for testing on a PC).
PIN_FILES = ("/boot/firmware/rch-model-pin", "/boot/rch-model-pin")

PIN_MIN, PIN_MAX = 4, 8          # PIN_MAX matches the on-screen keypad
ITERATIONS = 200_000             # ~0.3 s per check on a Pi 4

# Default PIN when no PIN file exists: SHA-256 of "2550".
DEFAULT_PIN_SHA256 = "a025f0314b164d72f92e11bd860ebbc0558addbeb5cf3ae1f06c4eded1d63ddc"


def pin_file():
    """Path of the PIN file to use (it may not exist yet)."""
    override = os.environ.get("RCH_PIN_FILE")
    if override:
        return override
    for path in PIN_FILES:
        if os.path.isdir(os.path.dirname(path)) and os.path.ismount(os.path.dirname(path)):
            return path
    return PIN_FILES[0]


def valid_pin(pin: str) -> bool:
    return pin.isdigit() and PIN_MIN <= len(pin) <= PIN_MAX


def hash_pin(pin: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}"


def _read_stored():
    """The stored hash line, or None if there's no usable PIN file."""
    try:
        with open(pin_file(), encoding="ascii") as f:
            line = f.read().strip()
    except (OSError, UnicodeDecodeError):
        return None
    return line if line.startswith("pbkdf2_sha256$") else None


def has_custom_pin() -> bool:
    return _read_stored() is not None


def check_pin(pin: str) -> bool:
    stored = _read_stored()
    if stored is None:
        attempt = hashlib.sha256(pin.encode()).hexdigest()
        return hmac.compare_digest(attempt, DEFAULT_PIN_SHA256)
    try:
        _, iterations, salt_hex, digest_hex = stored.split("$")
        attempt = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(attempt.hex(), digest_hex)
    except ValueError:            # damaged file: refuse rather than fall back to the default
        return False
