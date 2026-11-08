from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QSizePolicy, QStyledItemDelegate, QTableWidgetItem, QVBoxLayout, QWidget, QAbstractScrollArea, QStyleOptionViewItem, QStyle
from PySide6.QtCore import Qt, Signal, QFile, Slot
from PySide6.QtUiTools import QUiLoader 
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtCore import QRectF, Qt
from datetime import datetime

# Function to format fault timestamps
def format_fault_time(ts: str) -> str:
    """'DT#2026-10-12-14:39:00' or '2026-10-06-13:12:55.762' -> '2026-10-12 14:39:00'"""
    if not ts:
        return ""                                   # empty fault slot
    ts = ts.removeprefix("DT#")
    for fmt in ("%Y-%m-%d-%H:%M:%S", "%Y-%m-%d-%H:%M:%S.%f"):
        try:
            return datetime.strptime(ts, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return ts                                       # unexpected format: show it as-is rather than crash

# Delegate for painting alarm tags in the fault table
class AlarmTagDelegate(QStyledItemDelegate):
    TAG_W = 5          # bar width
    TAG_INSET = 4      # gap from table edge and from top/bottom of the row
    TEXT_GAP = 10      # gap between bar and text
    TAG_COLOR = QColor("#c62828")
    PLACEHOLDER_COLOR = QColor("#777777")
    PLACEHOLDER = "placeholder"     # Qt.UserRole marker for the "No active faults" row

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

        # "No active faults": centered grey text, no tag
        if index.data(Qt.UserRole) == self.PLACEHOLDER:
            painter.save()
            painter.setPen(self.PLACEHOLDER_COLOR)
            painter.setFont(opt.font)
            painter.drawText(option.rect, Qt.AlignCenter, text)
            painter.restore()
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
    TICKS_PER_SLM = 4   # slider steps per SLM: 0.25 SLM resolution
    DELIVERY_UNLOCKED_STATES = {"SteamFlowing"}   # states where the Delivery button can be used
    SES_UNLOCKED_STATES = {"SteamFlowing", "SesOff", "CheckIfHot", "FillWater", "PurgeVessel",
                           "SetDiffPressure", "InitMain"}   # states where the SES button can be used
    SES_ON_STATES = SES_UNLOCKED_STATES - {"SesOff"}   # same list minus SesOff: "is the system on?"

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
            lambda v: self.ui.PLC_nSteamFlowStpt.setText(f"{v / self.TICKS_PER_SLM:.2f}"))
        self.ui.horizontalSlider.valueChanged.connect(self._on_flow_slider_committed)

        # slider spans the model's rated flow: 0-25 SLM (102B-25) or 0-50 SLM (102B-50)
        self._model_slm = None
        self._set_flow_range(25)

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
        # Two decimals, like the setpoint. The PLC sends a 32-bit REAL, so str()
        # would show e.g. 0.1 as "0.10000000149011612" and widen the whole
        # window past the 800px screen.
        self.ui.PLC_nSteamFlowMeasured.setText(f"{values['PLC_nSteamFlowMeasured']:.2f}")

        faults = tuple((values[f"PLC_sFault{i}"], values[f"PLC_sFaultTime{i}"]) for i in range(1, 6))
        if faults != self._last_faults:          # only redraw when the list actually changes
            self._last_faults = faults
            t = self.ui.tableWidget
            t.clearContents()
            t.clearSpans()
            active = [(name, ts) for name, ts in faults if name]
            if not active:
                # one row spanning both columns, drawn grey and untagged by AlarmTagDelegate
                item = QTableWidgetItem("No active faults")
                item.setData(Qt.UserRole, AlarmTagDelegate.PLACEHOLDER)
                t.setSpan(0, 0, 1, 2)
                t.setItem(0, 0, item)
            for row, (name, ts) in enumerate(active):
                t.setItem(row, 0, QTableWidgetItem(name))
                time_item = QTableWidgetItem(format_fault_time(ts))
                time_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)   # right justify
                t.setItem(row, 1, time_item)

        # -50 only when its size bit alone is set; otherwise (incl. "Model not
        # set") use the -25 range, the safer of the two.
        is_50 = values.get("PLC_bSetSize50L") and not values.get("PLC_bSetSize25L")
        self._set_flow_range(50 if is_50 else 25)

        state = values["PLC_sMachineState"]
        # Remote (set on the System page): the EtherNet/IP tool owns these, so lock them here.
        # A missing tag reads as Local so the page still works before the PLC has the variable.
        local = not values.get("PLC_bRemoteMode", False)
        self.ui.PLC_bCmdSes.setEnabled(local and state in self.SES_UNLOCKED_STATES)
        self.ui.PLC_bCmdDelivery.setEnabled(local and state in self.DELIVERY_UNLOCKED_STATES)
        self.ui.horizontalSlider.setEnabled(local)
        self.ui.PLC_bCmdReset.setEnabled(local)
        self.ui.lbl_RemoteBanner.setVisible(not local)

        # buttons follow the PLC: a fault or reset turns them off on its own
        self._ses_on = state in self.SES_ON_STATES
        # Delivery is its own request in the PLC (off each time steam starts
        # flowing), so follow the PLC's delivery feedback, not the state.
        self._delivery_on = bool(values["PLC_bDeliveryActive"])
        self._show_toggle(self.ui.PLC_bCmdSes, self._ses_on, "System Enabled", "System Disabled")
        self._show_toggle(self.ui.PLC_bCmdDelivery, self._delivery_on, "Delivery Enabled", "Delivery Disabled")


    def _set_flow_range(self, slm: int):
        if slm == self._model_slm:
            return
        self._model_slm = slm
        slider = self.ui.horizontalSlider
        # Changing the range must not send a setpoint by itself (switching
        # 50 -> 25 clamps the handle), so keep valueChanged quiet here.
        slider.blockSignals(True)
        slider.setMaximum(slm * self.TICKS_PER_SLM)
        slider.blockSignals(False)
        self.ui.PLC_nSteamFlowStpt.setText(f"{slider.value() / self.TICKS_PER_SLM:.2f}")

    @Slot(int)
    def _on_flow_slider_committed(self, value: int):
        sp = value / self.TICKS_PER_SLM       # 0-100 ticks -> 0-25 SLM, 0-200 -> 0-50 SLM
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