from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget
from PySide6.QtCore import Qt

# Import the custom pages from your subfolders
from ui.pages.run_screen import RunScreen
from ui.pages.alarm_screen import AlarmScreen
from ui.pages.maint_screen import MaintScreen
from ui.pages.navigation_widget import NavigationWidget

class MainWindow(QMainWindow):
    def __init__(self):
        # Initialize the parent QMainWindow
        super().__init__()
        
        # Configure window properties optimized for an RPI4 display
        self.setWindowTitle("RPI4 Equipment Controller")
        self.resize(800, 480)  # Standard resolution for waveshare 5" display

        # Set up layout and central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # QStackedWidget holds multiple screens and shows one at a time
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setContentsMargins(10, 0, 10, 10)

        # Instantiate and register screens
        self.run_screen = RunScreen()
        self.alarm_screen = AlarmScreen()
        self.maint_screen = MaintScreen()

        self.stacked_widget.addWidget(self.run_screen)   # index 0
        self.stacked_widget.addWidget(self.alarm_screen) # index 1
        self.stacked_widget.addWidget(self.maint_screen) # index 2


        # Show the first screen
        self.stacked_widget.setCurrentIndex(0)

        #set up navigation widget
        self.navigation_bar = NavigationWidget()
        self.navigation_bar.setObjectName("navigation_bar") # for styling purposes

        # link the navigation signals from nav screen to the stack's setCurrentIndex method
        self.navigation_bar.navigate_to.connect(self.stacked_widget.setCurrentIndex)

        # add widgets to the main layout
        main_layout.addWidget(self.navigation_bar, stretch=1)
        main_layout.addWidget(self.stacked_widget, stretch=3)

        self.apply_styles()

    def apply_styles(self):
        # 2. set up global style for the app
        APPLICATION_STYLE = {
            "__main_bg_color__": "#181818",  # Light gray background to save RPI rendering power
            "__proj_font__": "'Roboto', 'Arial', sans-serif",  # Main font for the project
            "__proj_font_color__": "#D1D1D1",  # Main font color for the project
            "__widget_bg_color__": "#484848",  # White background for screens
            "__widget_border__": "2px solid #000000",  # Black border for widgets
            "__widget_border_radius__": "5px",  # Rounded corners for widgets
            "__button_bg_color__": "#acacac",  # Background color for buttons
            "__button_font_color__": "#000000",  # Font color for buttons
            "__button_border__": "2px solid #000000",  # Border for buttons
            "__button_border_radius__": "5px",  # Rounded corners for buttons
            "__H1-font-size__": "22px",  # Font size for H1 headers
            "__H2-font-size__": "18px",  # Font size for H2 headers
            "__B1-font-size__": "16px",  # Font size for body text
        }

        # open css files and replace style vars with actual values
        with open("ui/resources/style.css", "r") as f:
            style = f.read()

        for var_name, var_value in APPLICATION_STYLE.items():
            style = style.replace(var_name, var_value)

        self.setStyleSheet(style)
