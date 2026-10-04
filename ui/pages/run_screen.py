from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QSizePolicy, QTableWidgetItem, QVBoxLayout, QWidget, QAbstractScrollArea
from PySide6.QtCore import Signal, QFile, Slot
from PySide6.QtUiTools import QUiLoader


class RunScreen(QWidget):
    # EXAMPLE BUTTON HMI_bRun = Signal(bool)          # carries the checked state
    flow_setpoint_changed = Signal(float)   # SLM, emitted when the operator commits a value


    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        # 1. Open the .ui file safely
        #ui_file_path = "ui/resources/RunPage_widget.ui"                ui_file_path = "ui/resources/RunPage_widget.ui"
        ui_file_path = "ui/resources/RunPage_test3.ui"
        ui_file = QFile(ui_file_path)

        # 2. Instantiate the loader and load the layout
        loader = QUiLoader()
        #ui_widget = loader.load(ui_file, self)
        self.ui = loader.load(ui_file, self)
        ui_file.close()

        # Wrap ui_widget in a layout on self instead of stripping its layout
        container_layout = QVBoxLayout(self)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(self.ui)


        # change text on button presses
        self.ui.PLC_bCmdSes.toggled.connect(
            lambda checked: self.ui.PLC_bCmdSes.setText("System Enabled" if checked else "System Disabled"))
        self.ui.PLC_bCmdDelivery.toggled.connect(
            lambda checked: self.ui.PLC_bCmdDelivery.setText("Delivery Enabled" if checked else "Delivery Disabled"))

        # capture value after release of slider
        self.ui.horizontalSlider.setTracking(False)
        self.ui.horizontalSlider.sliderMoved.connect(
            lambda v: self.ui.PLC_nSteamFlowStpt.setText(f"{v / 4:.2f}"))
        self.ui.horizontalSlider.valueChanged.connect(self._on_flow_slider_committed)

        # setup fault table
        t = self.ui.tableWidget
        t.setColumnCount(2)
        t.setRowCount(5)
        t.setHorizontalHeaderLabels(["Fault", "Time"])
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionMode(QAbstractItemView.NoSelection)   
        self._last_faults = None

        # EXAMPLE BUTTON self.ui.HMI_bRun.toggled.connect(self.HMI_bRun.emit)
        

    #@Slot(dict)
    #def update_values(self, values: dict):
    #    self.ui.HMI_nPT1.setText(f"{values['nPT1'] / 10:.1f}")
    @Slot(dict)
    def update_values(self, values: dict):
        self.ui.PLC_nSteamFlowMeasured.setText(str(values['PLC_nSteamFlowMeasured']))

        faults = tuple((values[f"PLC_sFault{i}"], values[f"PLC_sFaultTime{i}"]) for i in range(1, 6))
        if faults != self._last_faults:          # only redraw when the list actually changes
            self._last_faults = faults
            for row, (name, ts) in enumerate(faults):
                self.ui.tableWidget.setItem(row, 0, QTableWidgetItem(name))
                self.ui.tableWidget.setItem(row, 1, QTableWidgetItem(ts))

    @Slot(int)
    def _on_flow_slider_committed(self, value: int):
        sp = value / 4.0                      # 0–100 ticks -> 0–25 SLM
        self.flow_setpoint_changed.emit(sp)