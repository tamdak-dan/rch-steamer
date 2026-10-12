from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QSizePolicy, QStyledItemDelegate, QTableWidgetItem, QVBoxLayout, QWidget, QAbstractScrollArea, QStyleOptionViewItem, QStyle
from PySide6.QtCore import Qt, Signal, QFile, Slot
from PySide6.QtUiTools import QUiLoader 
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtCore import QRectF, Qt
from datetime import datetime

# Function to format fault timestamps
def format_fault_time(ts: str) -> str:
    """'2026-10-06-13:12:55.762' -> '2026-10-06 13:12:55'"""
    if not ts:
        return ""                      # empty fault slot
    try:
        return datetime.strptime(ts, "%Y-%m-%d-%H:%M:%S.%f").strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ts                      # unexpected format: show it as-is rather than crash

# Delegate for painting alarm tags in the fault table
class AlarmTagDelegate(QStyledItemDelegate):
    TAG_W = 5          # bar width
    TAG_INSET = 4      # gap from table edge and from top/bottom of the row
    TEXT_GAP = 10      # gap between bar and text
    TAG_COLOR = QColor("#c62828")

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text

        # 1. draw the cell background/border with no text
        opt.text = ""
        style = opt.widget.style() if opt.widget else None
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        if not text:
            return

        r = option.rect
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # 2. rounded tag
        tag = QRectF(r.left() + self.TAG_INSET, r.top() + self.TAG_INSET,
                     self.TAG_W, r.height() - 2 * self.TAG_INSET)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.TAG_COLOR)
        painter.drawRoundedRect(tag, self.TAG_W / 2, self.TAG_W / 2)

        # 3. text, offset past the tag, with "..." if it doesn't fit
        text_rect = r.adjusted(self.TAG_INSET + self.TAG_W + self.TEXT_GAP, 0, -4, 0)
        painter.setPen(opt.palette.color(QPalette.Text))
        painter.setFont(opt.font)
        elided = opt.fontMetrics.elidedText(text, Qt.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, elided)

        painter.restore()

class RunScreen(QWidget):
    # EXAMPLE BUTTON HMI_bRun = Signal(bool)          # carries the checked state
    flow_setpoint_changed = Signal(float)   # SLM, emitted when the operator commits a value
    ses_toggled = Signal(bool)   # True = SES On requested, False = SES Off requested
    delivery_toggled = Signal(bool)   # True = Delivery On requested, False = Delivery Off requested
    reset_clicked = Signal()   # emitted when the reset button is clicked
    DELIVERY_UNLOCKED_STATES = {"SteamFlowing"}   # states where the System button can be used
    SES_UNLOCKED_STATES = {"SteamFlowing", "SesOff", "CheckIfHot", "FillWater", "PurgeVessel",
                           "SetDiffPressure", "InitMain"}   # states where the SES button can be used

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        # 1. Open the .ui file safely
        #ui_file_path = "ui/resources/RunPage_widget.ui"                ui_file_path = "ui/resources/RunPage_widget.ui"
        ui_file_path = "ui/resources/RunPage_widget.ui"
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



        # capture value after release of slider
        self.ui.horizontalSlider.setTracking(False)
        self.ui.horizontalSlider.sliderMoved.connect(
            lambda v: self.ui.PLC_nSteamFlowStpt.setText(f"{v / 4:.2f}"))
        self.ui.horizontalSlider.valueChanged.connect(self._on_flow_slider_committed)

        # setup fault table
        ROW_H = 30
        t = self.ui.tableWidget
        t.setColumnCount(2)
        t.setRowCount(5)
        t.setFixedHeight(ROW_H * t.rowCount() + 2 * t.frameWidth())
        t.horizontalHeader().setVisible(False)
        t.verticalHeader().setVisible(False)
        t.setShowGrid(False)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionMode(QAbstractItemView.NoSelection)
        t.setItemDelegateForColumn(0, AlarmTagDelegate(t))   
        self._last_faults = None

        # buttons request a change; what they show comes from the PLC in update_values
        self._ses_on = False
        self._delivery_on = False
        self.ui.PLC_bCmdSes.clicked.connect(self._on_ses_clicked)
        self.ui.PLC_bCmdDelivery.clicked.connect(self._on_delivery_clicked)

        # set up reset signal
        self.ui.PLC_bCmdReset.clicked.connect(self.reset_clicked.emit)

    @Slot(dict)
    def update_values(self, values: dict):
        self.ui.PLC_nSteamFlowMeasured.setText(str(values['PLC_nSteamFlowMeasured']))

        faults = tuple((values[f"PLC_sFault{i}"], values[f"PLC_sFaultTime{i}"]) for i in range(1, 6))
        if faults != self._last_faults:          # only redraw when the list actually changes
            self._last_faults = faults
            for row, (name, ts) in enumerate(faults):
                self.ui.tableWidget.setItem(row, 0, QTableWidgetItem(name))
                time_item = QTableWidgetItem(format_fault_time(ts))
                time_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)   # right justify
                self.ui.tableWidget.setItem(row, 1, time_item)

        state = values["PLC_sMachineState"]
        self.ui.PLC_bCmdSes.setEnabled(state in self.SES_UNLOCKED_STATES)
        self.ui.PLC_bCmdDelivery.setEnabled(state in self.DELIVERY_UNLOCKED_STATES)

        # buttons follow the PLC: a fault or reset turns them off on its own
        self._ses_on = state in self.SES_UNLOCKED_STATES
        self._delivery_on = state == "SteamFlowing"
        self._show_toggle(self.ui.PLC_bCmdSes, self._ses_on, "System Enabled", "System Disabled")
        self._show_toggle(self.ui.PLC_bCmdDelivery, self._delivery_on, "Delivery Enabled", "Delivery Disabled")


    @Slot(int)
    def _on_flow_slider_committed(self, value: int):
        sp = value / 4.0                      # 0–100 ticks -> 0–25 SLM
        self.flow_setpoint_changed.emit(sp)

    def _on_ses_clicked(self):
        self.ui.PLC_bCmdSes.setChecked(self._ses_on)        # undo the tap's own flip; PLC decides
        self.ses_toggled.emit(not self._ses_on)

    def _on_delivery_clicked(self):
        self.ui.PLC_bCmdDelivery.setChecked(self._delivery_on)
        self.delivery_toggled.emit(not self._delivery_on)

    @staticmethod
    def _show_toggle(btn, on: bool, on_text: str, off_text: str):
        btn.setChecked(on)
        btn.setText(on_text if on else off_text)