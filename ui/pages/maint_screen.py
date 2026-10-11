from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidgetItem, QVBoxLayout, QWidget
from PySide6.QtCore import Signal, QFile, Slot, Qt
from PySide6.QtGui import QColor
from PySide6.QtUiTools import QUiLoader


class MaintScreen(QWidget):
    maint_toggled = Signal(bool)            # True = enter maintenance requested, False = exit requested
    output_requested = Signal(str, bool)    # (TAG_MAP command key, requested state) for valves and modes

    # Match these to GVL_HMI.stHmiStatus.sStateName
    MAINT_STATE = "Maintenance"             # state name while in maintenance
    MAINT_ENTRY_STATES = {"SesOff"}         # manual: maintenance can only be entered from SES Off

    PT_CHECK_TORR = 5.0                     # manual: PT-1 and PT-2 within 5 Torr of each other (cold, SES Off)
    PT_CHECK_MAX_C = 30.0                   # only run the PT check when TC-1 and TC-2 are below this
    TC_OPEN_C = 250.0                       # legacy PLC shows "No Thermocouple" at or above this

    # button object name: (feedback key, label, on text, off text)
    # The button object name doubles as the command key in TAG_MAP, same as the run screen.
    OUTPUTS = {
        "PLC_bMaintSV1":       ("PLC_bSV1",              "SV-1 Drain",     "Open",    "Closed"),
        "PLC_bMaintSV2":       ("PLC_bSV2",              "SV-2 Main",      "Open",    "Closed"),
        "PLC_bMaintSV3":       ("PLC_bSV3",              "SV-3 Steam out", "Open",    "Closed"),
        "PLC_bMaintSV4":       ("PLC_bSV4",              "SV-4 Water in",  "Open",    "Closed"),
        "PLC_bMaintDrainMode": (None,                    "Drain mode",     "Running", "N2 under 5 psig"),
        "PLC_bMaintLoopback":  ("PLC_bLoopbackOn",       "Loopback test",  "Active",  "DSUB15"),
        "PLC_bMaintInitPurge": ("PLC_bInitPurgeEnabled", "Init purge",     "On",      "Off"),
    }

    # readings table rows: (label, value key)
    READINGS = (
        ("PT-1 upstream",   "PLC_rPT1"),
        ("PT-2 downstream", "PLC_rPT2"),
        ("PT check",        None),          # calculated from PT-1 and PT-2
        ("LS-1 upper level", "PLC_bLS1"),
        ("LS-3 lower level", "PLC_bLS3"),
        ("TC-1 SPA",        "PLC_rTC1"),
        ("TC-2 flow meter", "PLC_rTC2"),
        ("TC-3 ext line",   "PLC_rTC3"),
        ("TC-4 process out", "PLC_rTC4"),
    )

    COLOR_OK = QColor("#1e8e3e")            # same green as the run state pill
    COLOR_WARN = QColor("#c77c00")          # same amber as the startup state pill

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        # 1. Open the .ui file safely
        ui_file_path = "ui/resources/MaintPage_widget_test.ui"
        ui_file = QFile(ui_file_path)

        # 2. Instantiate the loader and load the layout
        loader = QUiLoader()
        self.ui = loader.load(ui_file, self)
        ui_file.close()

        # Wrap ui_widget in a layout on self instead of stripping its layout
        container_layout = QVBoxLayout(self)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(self.ui)

        # enter / exit maintenance
        self.ui.btn_MaintEnterExit.clicked.connect(self._on_maint_clicked)

        # valve and mode buttons all share one handler; the button's object name is the command key
        self._buttons = {name: getattr(self.ui, name) for name in self.OUTPUTS}
        for name, btn in self._buttons.items():
            btn.clicked.connect(lambda _checked, n=name: self._on_output_clicked(n))

        # setup readings table
        t = self.ui.tbl_MaintReadings
        t.setColumnCount(2)
        t.setRowCount(len(self.READINGS))
        t.horizontalHeader().setVisible(False)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        t.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)   # rows fill the table, no white space
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionMode(QAbstractItemView.NoSelection)
        t.setFocusPolicy(Qt.NoFocus)
        t.setShowGrid(False)

        # create the items once and only change their text on update
        for row, (label, _key) in enumerate(self.READINGS):
            t.setItem(row, 0, QTableWidgetItem(label))
            value_item = QTableWidgetItem("--")
            value_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            t.setItem(row, 1, value_item)
        self._last_readings = None

        # start locked until the first poll says otherwise
        self._in_maint = False
        self._feedback = {name: False for name in self.OUTPUTS}
        self._apply_lock(False, "")

    @Slot(dict)
    def update_values(self, values: dict):
        state = values["PLC_sMachineState"]
        self._in_maint = state == self.MAINT_STATE
        self._apply_lock(self._in_maint, state)

        # output feedback comes from the PLC, never from the button's own toggle
        sv = {i: bool(values[f"PLC_bSV{i}"]) for i in range(1, 5)}
        for name, (fb_key, label, on_text, off_text) in self.OUTPUTS.items():
            if fb_key is None:
                # drain mode = SV-1, SV-2, SV-4 open and SV-3 closed (same test as the legacy PLC)
                on = sv[1] and sv[2] and not sv[3] and sv[4]
            else:
                on = bool(values[fb_key])
            self._feedback[name] = on
            btn = self._buttons[name]
            btn.setChecked(on)
            btn.setText(f"{label}\n{on_text if on else off_text}")

        # readings: only redraw when something actually changes
        readings = tuple(values[key] if key else None for _label, key in self.READINGS)
        if readings != self._last_readings:
            self._last_readings = readings
            self._draw_readings(values)

    def _apply_lock(self, in_maint: bool, state: str):
        can_enter = state in self.MAINT_ENTRY_STATES

        btn = self.ui.btn_MaintEnterExit
        btn.setChecked(in_maint)
        btn.setText("Exit maintenance" if in_maint else "Enter maintenance")
        btn.setEnabled(in_maint or can_enter)

        if in_maint:
            hint = "Manual control active. Outputs are driven from this screen."
        elif can_enter:
            hint = "Machine is in SES Off. Enter maintenance to unlock manual controls."
        else:
            hint = "Turn the system off (SES Off) before entering maintenance."
        self.ui.lbl_MaintHint.setText(hint)

        for b in self._buttons.values():
            b.setEnabled(in_maint)

    def _draw_readings(self, values: dict):
        t = self.ui.tbl_MaintReadings
        pt1, pt2 = values["PLC_rPT1"], values["PLC_rPT2"]

        for row, (_label, key) in enumerate(self.READINGS):
            item = t.item(row, 1)
            item.setData(Qt.ForegroundRole, None)      # back to the default text color

            if key is None:                            # PT check row
                # only meaningful cold; legacy PLC compares PT-1/PT-2 only when TC-1 and TC-2 < 30 C
                if values["PLC_rTC1"] < self.PT_CHECK_MAX_C and values["PLC_rTC2"] < self.PT_CHECK_MAX_C:
                    diff = abs(pt1 - pt2)
                    item.setText(f"{diff:.0f} Torr")
                    item.setForeground(self.COLOR_OK if diff <= self.PT_CHECK_TORR else self.COLOR_WARN)
                else:
                    item.setText("Hot, n/a")
            elif key.startswith("PLC_rPT"):
                item.setText(f"{values[key]:.0f} Torr")
            elif key.startswith("PLC_rTC"):
                tc = values[key]
                item.setText("No TC" if tc >= self.TC_OPEN_C else f"{tc:.0f} °C")
            else:                                      # level sensors: True = water at the sensor
                item.setText("Water" if values[key] else "Dry")

    @Slot()
    def _on_maint_clicked(self):
        # ask the PLC; the button state follows sMachineState on the next poll
        self.ui.btn_MaintEnterExit.setChecked(self._in_maint)
        self.maint_toggled.emit(not self._in_maint)

    def _on_output_clicked(self, name: str):
        # put the button back to the PLC's state until feedback confirms the change
        requested = not self._feedback[name]
        self._buttons[name].setChecked(self._feedback[name])
        self.output_requested.emit(name, requested)
