import os
import sys

# The UI loads its .ui and .qss files with paths like "ui/resources/...",
# which are relative to the project folder. Switch to that folder first so
# the app works no matter where it's launched from (e.g. a boot service).
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from ui.screen_setup import MainWindow

# Set by deploy/kiosk-launch.sh on the Raspberry Pi. When it's not set
# (e.g. running on your desktop), the app opens as a normal window.
KIOSK = os.environ.get("RCH_KIOSK") == "1"


def main():
    # 0. On Linux, pyads needs to know this machine's own AMS Net ID before it
    #    opens a connection. The Pi's launcher sets it (Pi IP + ".1.1").
    local_net_id = os.environ.get("RCH_LOCAL_AMS_NETID")
    if local_net_id and sys.platform.startswith("linux"):
        import pyads
        pyads.set_local_address(local_net_id)

    # 1. Initialize the Qt Application framework
    app = QApplication(sys.argv)

    # 2. Create the main window instance (which builds the tabs internally)
    window = MainWindow()
<<<<<<< HEAD
    
    # 3. Render the window on the RPI screen
    window.showFullScreen()
    
=======

    # 3. Render the window. On the Pi: full screen, no mouse pointer.
    if KIOSK:
        app.setOverrideCursor(Qt.BlankCursor)
        window.showFullScreen()
    else:
        window.show()

>>>>>>> b5a223f5f46f7e57d1f4b6d2edc166e6cb3a749d
    # 4. Start the clean event loop execution
    sys.exit(app.exec())


# The __main__ safety check ensuring this script was run directly
if __name__ == "__main__":
    main()
