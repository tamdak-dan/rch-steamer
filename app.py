from PySide6.QtWidgets import QApplication
from ui.screen_setup import MainWindow
import sys

def main():
    # 1. Initialize the Qt Application framework
    app = QApplication(sys.argv)

    # 2. Create the main window instance (which builds the tabs internally)
    window = MainWindow()
    
    # 3. Render the window on the RPI screen
    window.show()
    
    # 4. Start the clean event loop execution
    sys.exit(app.exec())

# The __main__ safety check ensuring this script was run directly
if __name__ == "__main__":
    main()