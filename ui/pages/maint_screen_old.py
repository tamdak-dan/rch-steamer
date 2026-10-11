from PySide6.QtWidgets import QVBoxLayout, QWidget
from PySide6.QtCore import Signal, QFile
from PySide6.QtUiTools import QUiLoader

class MaintScreen(QWidget):
    navigate_to = Signal(int)

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        # 1. Open the .ui file safely
        ui_file_path = "ui/resources/MaintPage_widget.ui"
        ui_file = QFile(ui_file_path)

        # 2. Instantiate the loader and load the layout
        loader = QUiLoader()
        ui_widget = loader.load(ui_file, self)
        ui_file.close()

        # Wrap ui_widget in a layout on self instead of stripping its layout
        container_layout = QVBoxLayout(self)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(ui_widget)