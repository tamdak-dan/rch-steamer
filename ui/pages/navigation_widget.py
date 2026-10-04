from PySide6.QtWidgets import QHBoxLayout, QWidget
from PySide6.QtCore import Signal, QFile, Slot
from PySide6.QtUiTools import QUiLoader

class NavigationWidget(QWidget):
    navigate_to = Signal(int)

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        # 1. Open the .ui file safely
        ui_file_path = "ui/resources/Navigation_widget.ui"
        ui_file = QFile(ui_file_path)

        # 2. Instantiate the loader and load the layout
        loader = QUiLoader()
        self.ui = loader.load(ui_file, self)
        ui_file.close()

        nav_layout = QHBoxLayout(self)
        nav_layout.addWidget(self.ui)  
        nav_layout.setContentsMargins(0, 0, 0, 5)

        # 3. Set up navigation buttons
        # From any screen, go to run screen
        self.ui.btn_to_RunScreen.clicked.connect(lambda: self.navigate_to.emit(0))
        # From any screen, go to alarm screen
        #self.ui.btn_to_AlarmScreen.clicked.connect(lambda: self.navigate_to.emit(1))
        # From any screen, go to maintenance screen
        #self.ui.btn_to_MaintScreen.clicked.connect(lambda: self.navigate_to.emit(2))

    # alarm LED function for changing colors/states
    def _set_led(self, state: str):
        led = self.ui.Alarm_LED
        if led.property("state") == state:
            return                          # skip restyling every 250 ms poll
        led.setProperty("state", state)
        led.style().unpolish(led)           # make Qt re-read the stylesheet
        led.style().polish(led)

    @Slot(dict)
    def update_values(self, values: dict):
        self.ui.PLC_sMachineState.setText(values["PLC_sMachineState"])
        self._set_led("alarm" if values["PLC_bAnyFault"] else "ok")

    @Slot(bool)
    def set_connected(self, connected: bool):
        if not connected:
            self.ui.PLC_sMachineState.setText("PLC Disconnected")
            self._set_led("unknown")        # no matching rule, so it falls back to grey