from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from PySide6.QtCore import Signal, QFile, Slot
from PySide6.QtUiTools import QUiLoader

class RunScreen(QWidget):
    # EXAMPLE BUTTON HMI_bRun = Signal(bool)          # carries the checked state

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        # 1. Open the .ui file safely
        #ui_file_path = "ui/resources/RunPage_widget.ui"                ui_file_path = "ui/resources/RunPage_widget.ui"
        ui_file_path = "ui/resources/RunPage_test.ui"
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

        # EXAMPLE BUTTON self.ui.HMI_bRun.toggled.connect(self.HMI_bRun.emit)
        

    #@Slot(dict)
    #def update_values(self, values: dict):
    #    self.ui.HMI_nPT1.setText(f"{values['nPT1'] / 10:.1f}")
    @Slot(dict)
    def update_values(self, values: dict):
        self.ui.PLC_nUpstreamPress.setText(str(values['PLC_nUpstreamPress']))