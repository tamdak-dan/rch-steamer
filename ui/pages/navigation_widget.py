from PySide6.QtWidgets import QHBoxLayout, QWidget
from PySide6.QtCore import Signal, QFile
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
        ui_widget = loader.load(ui_file, self)
        ui_file.close()

        nav_layout = QHBoxLayout(self)
        nav_layout.addWidget(ui_widget)  
        nav_layout.setContentsMargins(0, 0, 0, 5)

        # 3. Set up navigation buttons
        # From any screen, go to run screen
        ui_widget.btn_to_RunScreen.clicked.connect(lambda: self.navigate_to.emit(0))
        # From any screen, go to alarm screen
        ui_widget.btn_to_AlarmScreen.clicked.connect(lambda: self.navigate_to.emit(1))
        # From any screen, go to maintenance screen
        ui_widget.btn_to_MaintScreen.clicked.connect(lambda: self.navigate_to.emit(2))