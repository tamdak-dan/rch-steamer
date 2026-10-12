from PySide6.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from PySide6.QtCore import Qt


# ===========================================================================
# Touch keypad and confirm dialogs for the 800x480 touchscreen (no keyboard).
# Styled from style.qss through the object names TouchDialog, td_* below.
# ===========================================================================

def _center_on_parent(dlg: QDialog, parent):
    """Frameless dialogs don't get placed by a window manager, so center them ourselves."""
    if parent is None:
        return
    win = parent.window()
    dlg.adjustSize()
    geo = win.frameGeometry()
    dlg.move(geo.center() - dlg.rect().center())


class TouchKeypad(QDialog):
    """
    Numeric keypad for entering values on the touchscreen.

    mode:
      "ip"       digits and '.', e.g. 192.168.137.10
      "pin"      digits only, shown as dots
      a template made of '#' plus separators, e.g. "####-##-##" or "##:##:##".
                 Digits fill the '#' slots in order; OK unlocks once every slot is filled.
    """
    PIN_MAX = 8
    IP_MAX = 15

    def __init__(self, parent, title: str, mode: str = "ip", initial: str = ""):
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint)
        self.setObjectName("TouchDialog")
        self.setModal(True)
        self._mode = mode
        self._is_template = mode not in ("ip", "pin")
        self._text = "" if self._is_template or mode == "pin" else initial
        self._fresh = bool(self._text)          # first key replaces a pre-filled value

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(8)

        lbl_title = QLabel(title)
        lbl_title.setObjectName("td_Title")
        layout.addWidget(lbl_title)

        self._display = QLabel()
        self._display.setObjectName("td_Display")
        self._display.setMinimumHeight(48)
        layout.addWidget(self._display)

        grid = QGridLayout()
        grid.setSpacing(6)
        keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "0", "⌫"]
        for i, key in enumerate(keys):
            btn = QPushButton(key)
            btn.setObjectName("td_Key")
            btn.setMinimumSize(80, 52)
            btn.setFocusPolicy(Qt.NoFocus)
            if key == ".":
                btn.setVisible(mode == "ip")    # keeps its grid cell so the layout doesn't shift
                btn.setEnabled(mode == "ip")
            btn.clicked.connect(lambda _c=False, k=key: self._on_key(k))
            grid.addWidget(btn, i // 3, i % 3)
        layout.addLayout(grid)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("td_Cancel")
        btn_cancel.setMinimumHeight(52)
        btn_cancel.setFocusPolicy(Qt.NoFocus)
        btn_cancel.clicked.connect(self.reject)
        self._btn_ok = QPushButton("OK")
        self._btn_ok.setObjectName("td_Ok")
        self._btn_ok.setMinimumHeight(52)
        self._btn_ok.setFocusPolicy(Qt.NoFocus)
        self._btn_ok.clicked.connect(self.accept)
        actions.addWidget(btn_cancel)
        actions.addWidget(self._btn_ok)
        layout.addLayout(actions)

        self._refresh()
        _center_on_parent(self, parent)

    # ---- key handling -----------------------------------------------------
    def _slots(self) -> int:
        return self._mode.count("#")

    def _on_key(self, key: str):
        if key == "⌫":
            self._fresh = False
            self._text = self._text[:-1]
        else:
            if self._fresh:                     # typing replaces the pre-filled value
                self._text = ""
                self._fresh = False
            if self._is_template:
                if len(self._text) < self._slots() and key.isdigit():
                    self._text += key
            elif self._mode == "pin":
                if len(self._text) < self.PIN_MAX:
                    self._text += key
            else:                               # ip
                if len(self._text) < self.IP_MAX:
                    self._text += key
        self._refresh()

    def _refresh(self):
        if self._mode == "pin":
            shown = "•" * len(self._text)
            ok = len(self._text) > 0
        elif self._is_template:
            digits = iter(self._text)
            shown = "".join(next(digits, "_") if c == "#" else c for c in self._mode)
            ok = len(self._text) == self._slots()
        else:
            shown = self._text
            ok = len(self._text) > 0
        self._display.setText(shown)
        self._btn_ok.setEnabled(ok)

    def value(self) -> str:
        """Entered value; templates come back with their separators filled in."""
        if self._is_template:
            digits = iter(self._text)
            return "".join(next(digits, "_") if c == "#" else c for c in self._mode)
        return self._text

    @staticmethod
    def get_value(parent, title: str, mode: str = "ip", initial: str = ""):
        """Show the keypad; returns the entered text, or None if cancelled."""
        dlg = TouchKeypad(parent, title, mode, initial)
        return dlg.value() if dlg.exec() == QDialog.Accepted else None


class TouchConfirm(QDialog):
    """Large-button yes/no dialog."""

    def __init__(self, parent, title: str, message: str, ok_text: str = "OK"):
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint)
        self.setObjectName("TouchDialog")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(10)

        lbl_title = QLabel(title)
        lbl_title.setObjectName("td_Title")
        layout.addWidget(lbl_title)

        lbl_msg = QLabel(message)
        lbl_msg.setObjectName("td_Message")
        lbl_msg.setWordWrap(True)
        layout.addWidget(lbl_msg)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("td_Cancel")
        btn_cancel.setMinimumHeight(52)
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton(ok_text)
        btn_ok.setObjectName("td_Ok")
        btn_ok.setMinimumHeight(52)
        btn_ok.clicked.connect(self.accept)
        actions.addWidget(btn_cancel)
        actions.addWidget(btn_ok)
        layout.addLayout(actions)

        _center_on_parent(self, parent)

    @staticmethod
    def ask(parent, title: str, message: str, ok_text: str = "OK") -> bool:
        return TouchConfirm(parent, title, message, ok_text).exec() == QDialog.Accepted
