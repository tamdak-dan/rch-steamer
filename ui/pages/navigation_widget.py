from PySide6.QtWidgets import QHBoxLayout, QWidget, QButtonGroup
from PySide6.QtCore import Signal, QFile, Slot
from PySide6.QtUiTools import QUiLoader

class NavigationWidget(QWidget):
    navigate_to = Signal(int)

    STATE_CAT = {"SteamFlowing": "run", "Fault": "fault",
                 "FillWater": "startup", "PurgeVessel": "startup",
                 "SetDiffPressure": "startup", "InitMain": "startup", "CheckIfHot": "startup"}

    # retained size bits in the PLC; exactly one should be TRUE
    SIZE_TAGS = {25: "PLC_bSetSize25L", 50: "PLC_bSetSize50L"}
    MODEL_PREFIX = "102B"          # shown as 102B-25 / 102B-50 under the title
    

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
                          (self.ui.btn_to_MaintScreen, 1),
                          (self.ui.btn_to_SystemScreen, 2)):
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

        self._show_model(values)

        cat = self.STATE_CAT.get(state, "idle")
        lbl = self.ui.PLC_sMachineState
        if lbl.property("cat") != cat:
            lbl.setProperty("cat", cat)
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)

    def _show_model(self, values: dict):
        # .get so missing size tags can't stop the state pill from updating
        bits = {slm: values.get(tag) for slm, tag in self.SIZE_TAGS.items()}
        on = [slm for slm, b in bits.items() if b]
        if None in bits.values():
            text, warn = "--", False                     # tags not in TAG_MAP yet
        elif len(on) == 1:
            text, warn = f"{self.MODEL_PREFIX}-{on[0]}", False
        else:
            text, warn = "Model not set", True           # neither or both set: see System page
        self._set_model_tag(text, warn)

    def _set_model_tag(self, text: str, warn: bool):
        lbl = self.ui.lbl_SteamerModel
        lbl.setVisible(text != "--")                     # hide when the size is unknown (no tags / disconnected)
        lbl.setText(text)
        if lbl.property("warn") != warn:
            lbl.setProperty("warn", warn)
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)

    @Slot(bool)
    def set_connected(self, connected: bool):
        if not connected:
            self.ui.PLC_sMachineState.setText("PLC Disconnected")
            self._set_model_tag("--", False)             # don't show a size we can no longer confirm

    @Slot(int)
    def set_active_page(self, index: int):
        btn = self.nav_group.button(index)
        if btn:
            btn.setChecked(True)