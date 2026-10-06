from PySide6.QtWidgets import QHBoxLayout, QWidget, QButtonGroup
from PySide6.QtCore import Signal, QFile, Slot
from PySide6.QtUiTools import QUiLoader

class NavigationWidget(QWidget):
    navigate_to = Signal(int)

    STATE_CAT = {"SteamFlowing": "run", "Fault": "fault",
                 "FillWater": "startup", "PurgeVessel": "startup",
                 "SetDiffPressure": "startup", "InitMain": "startup", "CheckIfHot": "startup"}
    

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


        # 3. Navigation buttons as an exclusive group: one is always "checked"
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        # id = the page's index in the QStackedWidget
        for btn, page in ((self.ui.btn_to_RunScreen, 0),
                          (self.ui.btn_to_MaintScreen, 2),
                          (self.ui.btn_to_SystemScreen, 3)):
            btn.setCheckable(True)
            self.nav_group.addButton(btn, page)

        self.nav_group.idClicked.connect(self.navigate_to.emit)
        self.ui.btn_to_RunScreen.setChecked(True)     # app starts on the run screen


        # 3. Set up navigation buttons
        # From any screen, go to run screen
        #self.ui.btn_to_RunScreen.clicked.connect(lambda: self.navigate_to.emit(0))
        # From any screen, go to alarm screen
        #self.ui.btn_to_AlarmScreen.clicked.connect(lambda: self.navigate_to.emit(1))
        # From any screen, go to maintenance screen
        #self.ui.btn_to_MaintScreen.clicked.connect(lambda: self.navigate_to.emit(2))


    @Slot(dict)
    def update_values(self, values: dict):
        state = values["PLC_sMachineState"]
        self.ui.PLC_sMachineState.setText(state)

        cat = self.STATE_CAT.get(state, "idle")
        lbl = self.ui.PLC_sMachineState
        if lbl.property("cat") != cat:
            lbl.setProperty("cat", cat)
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)

    @Slot(bool)
    def set_connected(self, connected: bool):
        if not connected:
            self.ui.PLC_sMachineState.setText("PLC Disconnected")

    @Slot(int)
    def set_active_page(self, index: int):
        btn = self.nav_group.button(index)
        if btn:
            btn.setChecked(True)