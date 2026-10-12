import hashlib
import ipaddress
from datetime import datetime, timedelta
from PySide6.QtWidgets import QVBoxLayout, QWidget
from PySide6.QtCore import Signal, QFile, Slot
from PySide6.QtUiTools import QUiLoader
from ui.pages.touch_dialogs import TouchConfirm, TouchKeypad


class SystemScreen(QWidget):
    # EtherNet/IP settings for the EL6652-0010, as UDINTs with the first octet in the
    # most significant byte (192.168.1.10 -> 0xC0A8010A). The PLC writes them to CoE 0xF800:21..23.
    # object, not int: Qt's int is signed 32-bit and 192.x.x.x as a UDINT is ~3.2 billion
    eip_apply_requested = Signal(object, object, object)   # (ip, subnet mask, gateway)
    time_set_requested = Signal(object)               # new PLC clock as a DT value (seconds since 1970-01-01, local time)
    model_change_requested = Signal(int)              # rated flow in SLM: 25 or 50

    # Match these to GVL_HMI.stHmiStatus.sStateName
    MODEL_CHANGE_STATES = {"SesOff"}       # rated flow can only change while the steamer is off
    EIP_CHANGE_STATES = {"SesOff"}         # the terminal drops its EtherNet/IP connection while it restarts

    # GVL_HMI.stHmiStatus.stEip.nApplyState
    EIP_IDLE, EIP_BUSY, EIP_DONE, EIP_ERROR = 0, 1, 2, 3
    # GVL_HMI.stHmiStatus.nSetTimeState uses the same values

    DT_EPOCH = datetime(1970, 1, 1)        # TwinCAT DT = seconds since this, in the PLC's local time

    MODELS = (25, 50)

    # SHA-256 of the model-change PIN (default 2550). To change it:
    #   python -c "import hashlib; print(hashlib.sha256(b'NEWPIN').hexdigest())"
    MODEL_PIN_SHA256 = "a025f0314b164d72f92e11bd860ebbc0558addbeb5cf3ae1f06c4eded1d63ddc"

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        # 1. Open the .ui file safely
        ui_file_path = "ui/resources/SystemPage_widget.ui"
        ui_file = QFile(ui_file_path)

        # 2. Instantiate the loader and load the layout
        loader = QUiLoader()
        self.ui = loader.load(ui_file, self)
        ui_file.close()

        # Wrap ui_widget in a layout on self instead of stripping its layout
        container_layout = QVBoxLayout(self)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(self.ui)

        # EtherNet/IP fields open the keypad; Apply validates, confirms, then hands off to the PLC
        self._eip_fields = (self.ui.btn_IpAddress, self.ui.btn_SubnetMask, self.ui.btn_Gateway)
        self.ui.btn_IpAddress.clicked.connect(lambda: self._edit_eip(self.ui.btn_IpAddress, "IP address"))
        self.ui.btn_SubnetMask.clicked.connect(lambda: self._edit_eip(self.ui.btn_SubnetMask, "Subnet mask"))
        self.ui.btn_Gateway.clicked.connect(lambda: self._edit_eip(self.ui.btn_Gateway, "Gateway"))
        self.ui.btn_ApplyNetwork.clicked.connect(self._on_apply_eip)

        # time fields use fixed templates so the keypad only has to take digits
        self.ui.btn_Date.clicked.connect(lambda: self._edit_time(self.ui.btn_Date, "Date (YYYY-MM-DD)", "####-##-##"))
        self.ui.btn_Time.clicked.connect(lambda: self._edit_time(self.ui.btn_Time, "Time (HH:MM:SS, 24-hour)", "##:##:##"))
        self.ui.btn_SetTime.clicked.connect(self._on_set_time)

        # model buttons: checked state always follows the PLC, never the tap itself
        self._model_buttons = {25: self.ui.btn_Model25, 50: self.ui.btn_Model50}
        for slm, btn in self._model_buttons.items():
            btn.clicked.connect(lambda _checked, s=slm: self._on_model_clicked(s))

        self._state = ""
        self._connected = False
        self._rated_flow = None
        self._eip_active = None        # (ip, mask, gw) strings the terminal is actually using
        self._eip_edited = False       # True once the operator changes a field; stops live values overwriting it
        self._eip_apply_state = self.EIP_IDLE
        self._plc_now = None           # PLC clock (datetime); the PLC is the only clock this HMI shows
        self._time_edited = False      # True once the operator changes date/time; stops the PLC clock refilling them
        self._time_state = self.EIP_IDLE
        self._apply_locks()

    # ---- values from the PLC ------------------------------------------------
    @Slot(dict)
    def update_values(self, values: dict):
        self._state = values["PLC_sMachineState"]

        # .get so a missing tag can't stop the rest of the page from updating
        rated = values.get("PLC_nRatedFlow")
        self._rated_flow = int(round(rated)) if rated is not None else None
        for slm, btn in self._model_buttons.items():
            btn.setChecked(self._rated_flow == slm)

        # active EtherNet/IP settings (read by the PLC from CoE 0xF900)
        raw = (values.get("PLC_nEipIpActive"), values.get("PLC_nEipMaskActive"), values.get("PLC_nEipGwActive"))
        if None not in raw:
            self._eip_active = tuple(str(ipaddress.IPv4Address(n)) for n in raw)
            if not self._eip_edited:
                for btn, text in zip(self._eip_fields, self._eip_active):
                    btn.setText(text)

        self._show_eip_apply_state(values.get("PLC_nEipApplyState", self.EIP_IDLE))

        # PLC clock: shown live, and used to pre-fill the date/time fields until the operator edits them
        self._show_time_state(values.get("PLC_nSetTimeState", self.EIP_IDLE))
        dt_raw = values.get("PLC_dtNow")
        if dt_raw is not None:
            self._plc_now = self.DT_EPOCH + timedelta(seconds=int(dt_raw))
            self.ui.lbl_CurrentTime.setText(self._plc_now.strftime("%Y-%m-%d %H:%M:%S"))
            if not self._time_edited:
                self._prefill_time()
        self._apply_locks()

    @Slot(bool)
    def set_connected(self, connected: bool):
        self._connected = connected
        self._apply_locks()

    def _apply_locks(self):
        # time lives in the PLC, so it can only be shown or set while connected
        time_ok = self._connected and self._plc_now is not None and self._time_state != self.EIP_BUSY
        for btn in (self.ui.btn_Date, self.ui.btn_Time, self.ui.btn_SetTime):
            btn.setEnabled(time_ok)
        if not self._connected:
            self.ui.lbl_CurrentTime.setText("--")
            if self._time_state == self.EIP_IDLE:
                self._set_status(self.ui.lbl_TimeStatus, "PLC disconnected.")
        elif self.ui.lbl_TimeStatus.text() == "PLC disconnected.":
            self._set_status(self.ui.lbl_TimeStatus, "24-hour clock.")

        model_ok = self._connected and self._state in self.MODEL_CHANGE_STATES
        for btn in self._model_buttons.values():
            btn.setEnabled(model_ok)
        if not self._connected:
            self._set_status(self.ui.lbl_ModelStatus, "PLC disconnected.")
        elif model_ok:
            self._set_status(self.ui.lbl_ModelStatus, "PIN required to change the model.")
        else:
            self._set_status(self.ui.lbl_ModelStatus, "Turn the system off (SES Off) to change the model.")

        # the settings go through the PLC, so it has to be connected; SES Off because the
        # terminal's EtherNet/IP link to the tool drops while it restarts with the new address
        eip_ok = (self._connected and self._state in self.EIP_CHANGE_STATES
                  and self._eip_apply_state != self.EIP_BUSY)
        for btn in (*self._eip_fields, self.ui.btn_ApplyNetwork):
            btn.setEnabled(eip_ok)
        if self._eip_apply_state == self.EIP_IDLE and not self._eip_edited:
            if not self._connected:
                self._set_status(self.ui.lbl_NetworkStatus, "PLC disconnected.")
            elif not eip_ok:
                self._set_status(self.ui.lbl_NetworkStatus, "Turn the system off (SES Off) to change.")
            else:
                self._set_status(self.ui.lbl_NetworkStatus, "Tap a field to edit.")

    def _show_eip_apply_state(self, state: int):
        if state == self._eip_apply_state:
            return
        self._eip_apply_state = state
        if state == self.EIP_BUSY:
            self._set_status(self.ui.lbl_NetworkStatus, "Applying, terminal restarting...")
        elif state == self.EIP_DONE:
            self._eip_edited = False          # fields follow the terminal's active values again
            self._set_status(self.ui.lbl_NetworkStatus, "EtherNet/IP settings applied.", True)
        elif state == self.EIP_ERROR:
            self._set_status(self.ui.lbl_NetworkStatus, "PLC couldn't apply the settings.", False)

    def _show_time_state(self, state: int):
        if state == self._time_state:
            return
        self._time_state = state
        if state == self.EIP_BUSY:
            self._set_status(self.ui.lbl_TimeStatus, "Setting PLC clock...")
        elif state == self.EIP_DONE:
            self._time_edited = False         # fields follow the PLC clock again
            self._set_status(self.ui.lbl_TimeStatus, "PLC clock set.", True)
        elif state == self.EIP_ERROR:
            self._set_status(self.ui.lbl_TimeStatus, "PLC couldn't set its clock.", False)
        else:
            self._set_status(self.ui.lbl_TimeStatus, "24-hour clock.")

    # ---- editing ----------------------------------------------------------
    def _edit_field(self, btn, title: str, mode: str):
        value = TouchKeypad.get_value(self, title, mode, btn.text())
        if value is not None:
            btn.setText(value)
        return value

    def _edit_eip(self, btn, title: str):
        if self._edit_field(btn, title, "ip") is not None:
            self._eip_edited = True
            self._set_status(self.ui.lbl_NetworkStatus, "Not applied yet.")

    def _on_apply_eip(self):
        ip, mask, gw = (b.text().strip() for b in self._eip_fields)
        try:
            addr = ipaddress.IPv4Address(ip)
            net = ipaddress.IPv4Network(f"{ip}/{mask}", strict=False)   # rejects masks like 255.0.255.0
            gw_addr = ipaddress.IPv4Address(gw)
        except ValueError:
            self._set_status(self.ui.lbl_NetworkStatus, "Check all three addresses.", False)
            return
        # 0.0.0.0 in any field switches the terminal to DHCP, so all three must be real addresses
        if int(addr) == 0 or net.prefixlen == 0 or int(gw_addr) == 0:
            self._set_status(self.ui.lbl_NetworkStatus, "0.0.0.0 isn't allowed (it turns on DHCP).", False)
            return
        if addr in (net.network_address, net.broadcast_address):
            self._set_status(self.ui.lbl_NetworkStatus, "That IP is the network or broadcast address.", False)
            return
        if gw_addr not in net:
            self._set_status(self.ui.lbl_NetworkStatus, "Gateway must be in the same subnet.", False)
            return
        if self._eip_active == (ip, str(net.netmask), gw):
            self._set_status(self.ui.lbl_NetworkStatus, "Those are already the active settings.")
            return

        message = (f"Set the EL6652-0010 EtherNet/IP adapter to {ip} / {net.netmask}, gateway {gw}.\n\n"
                   "The terminal restarts and the tool's EtherNet/IP connection drops briefly. "
                   "The tool must use the new address afterward.")
        if not TouchConfirm.ask(self, "Apply EtherNet/IP settings", message, "Apply"):
            return
        self._set_status(self.ui.lbl_NetworkStatus, "Sending to PLC...")
        self.eip_apply_requested.emit(int(addr), int(net.netmask), int(gw_addr))

    def _edit_time(self, btn, title: str, mode: str):
        if self._edit_field(btn, title, mode) is not None:
            self._time_edited = True
            self._set_status(self.ui.lbl_TimeStatus, "Not set yet.")

    def _on_set_time(self):
        text = f"{self.ui.btn_Date.text()} {self.ui.btn_Time.text()}"
        try:
            dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            self._set_status(self.ui.lbl_TimeStatus, "That date or time isn't valid.", False)
            return
        if dt < self.DT_EPOCH:
            self._set_status(self.ui.lbl_TimeStatus, "Date must be 1970 or later.", False)
            return
        if not TouchConfirm.ask(self, "Set PLC clock",
                                f"Set the PLC clock to {text}? Fault timestamps use this clock.", "Set time"):
            return
        self._set_status(self.ui.lbl_TimeStatus, "Sending to PLC...")
        self.time_set_requested.emit(int((dt - self.DT_EPOCH).total_seconds()))

    def _on_model_clicked(self, slm: int):
        # put the buttons back to the PLC's value until feedback confirms a change
        for s, btn in self._model_buttons.items():
            btn.setChecked(self._rated_flow == s)
        if slm == self._rated_flow:
            return

        pin = TouchKeypad.get_value(self, "Enter PIN to change model", "pin")
        if pin is None:
            return
        if hashlib.sha256(pin.encode()).hexdigest() != self.MODEL_PIN_SHA256:
            self._set_status(self.ui.lbl_ModelStatus, "Wrong PIN.", False)
            return
        if not TouchConfirm.ask(self, "Change steamer model",
                                f"Change the rated flow to {slm} SLM? Only do this if the hardware is a {slm} SLM unit.",
                                f"Set {slm} SLM"):
            return
        self.model_change_requested.emit(slm)

    # ---- helpers ------------------------------------------------------------
    def _prefill_time(self):
        if self._plc_now is None:
            return
        self.ui.btn_Date.setText(self._plc_now.strftime("%Y-%m-%d"))
        self.ui.btn_Time.setText(self._plc_now.strftime("%H:%M:%S"))

    def showEvent(self, event):
        # each time the page opens: drop unapplied date/time and EtherNet/IP edits
        self._time_edited = False
        self._prefill_time()
        if self._eip_edited and self._eip_active:
            self._eip_edited = False
            for btn, text in zip(self._eip_fields, self._eip_active):
                btn.setText(text)
            self._apply_locks()
        super().showEvent(event)

    @staticmethod
    def _set_status(label, text: str, ok=None):
        # ok=True green, ok=False amber, None default hint color (see style.qss)
        label.setText(text)
        state = "" if ok is None else ("ok" if ok else "warn")
        if label.property("status") != state:
            label.setProperty("status", state)
            label.style().unpolish(label)
            label.style().polish(label)
