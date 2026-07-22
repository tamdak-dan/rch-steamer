import pyads
from PySide6.QtCore import QObject, QThread, Signal, Slot, QTimer


# ---------------------------------------------------------------------------
# Tag map: the single place you edit when the PLC symbol list changes.
#   key   = the name your UI code uses
#   value = (ADS symbol name, pyads type)
# ---------------------------------------------------------------------------
TAG_MAP = {
    "HMI_bRun":     ("MAIN.HMI_bRun",    pyads.PLCTYPE_BOOL),
    #"pt1":         ("MAIN.PT1",         pyads.PLCTYPE_INT),   # upstream pressure
    #"pt2":         ("MAIN.PT2",         pyads.PLCTYPE_INT),   # downstream pressure
    #"flow_rate":   ("MAIN.FlowRate",    pyads.PLCTYPE_INT),
    #"tc1":         ("MAIN.TC1",         pyads.PLCTYPE_INT),
    #"stage":       ("MAIN.Stage",       pyads.PLCTYPE_INT),
    #"alarm_active":("MAIN.AlarmActive", pyads.PLCTYPE_BOOL),
}

# ===========================================================================
# ADS WORKER  —  runs on the BACKGROUND thread
# ===========================================================================
# Everything in this class executes off the main thread. That's the whole
# point: an ADS read over Ethernet takes anywhere from 1ms to (on a timeout)
# several seconds. If that happened on the main thread, your UI would freeze
# solid every time the CX7000 was slow to answer.
#
# It inherits QObject rather than QThread. This is the "worker object" pattern
# and it's the one Qt actually recommends — you create the object, then push
# it onto a thread with moveToThread(). Subclassing QThread and overriding
# run() is the older pattern and makes it very easy to accidentally run code
# on the wrong thread.
# ===========================================================================
class AdsWorker(QObject):

    # -----------------------------------------------------------------------
    # SIGNALS
    # -----------------------------------------------------------------------
    # Signals are how this thread talks to the UI thread safely. You must
    # NEVER call something like label.setText() from a background thread —
    # Qt widgets are not thread-safe and it will crash or corrupt the display
    # in ways that are miserable to debug.
    #
    # When a signal crosses a thread boundary, Qt automatically queues the
    # payload and delivers it on the receiving thread's event loop. So the
    # slot on the other end runs on the main thread, where touching widgets
    # is legal. This is the single most important idea in the whole file.
    # -----------------------------------------------------------------------
    data_updated = Signal(dict)       # emitted every poll with all tag values
    connection_changed = Signal(bool) # True on connect, False on drop
    error_occurred = Signal(str)      # human-readable message for logs/UI

    def __init__(self, ams_net_id: str, ip_address: str,
                 ams_port: int = pyads.PORT_TC3PLC1, poll_ms: int = 250):
        super().__init__()

        # Just storing config. Note what is NOT here: we do not create the
        # pyads connection yet. __init__ runs on the MAIN thread (because
        # that's where you construct the object), and the connection has to
        # be created on the thread that will use it. See start() below.
        self._ams_net_id = ams_net_id
        self._ip_address = ip_address
        self._ams_port = ams_port
        self._poll_ms = poll_ms

        self._plc = None    # pyads.Connection, created in start()
        self._timer = None  # QTimer, created in start()

    # -----------------------------------------------------------------------
    # START  —  the first thing that runs ON the background thread
    # -----------------------------------------------------------------------
    # @Slot() marks this as callable across a thread boundary. AdsClient wires
    # thread.started -> this method, so Qt calls it once the new thread's
    # event loop is up and running.
    #
    # Both the Connection and the QTimer are created here rather than in
    # __init__ specifically so they belong to this thread:
    #   - pyads.Connection holds a socket + handle cache that isn't safe to
    #     share across threads.
    #   - A QTimer fires on the thread it was created on. Create it in
    #     __init__ and it would tick on the main thread, which would mean
    #     _poll() blocks your UI — exactly what we're trying to avoid.
    # -----------------------------------------------------------------------
    @Slot()
    def start(self):
        self._plc = pyads.Connection(self._ams_net_id, self._ams_port, self._ip_address)
        self._connect()

        # QTimer instead of a `while True: sleep()` loop. A sleep loop would
        # block this thread's event loop, meaning write_tag() calls queued
        # from the UI would never get delivered. The timer yields between
        # ticks so queued slots can run.
        self._timer = QTimer()
        self._timer.setInterval(self._poll_ms)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    # -----------------------------------------------------------------------
    # CONNECT  —  open the ADS port, report success or failure
    # -----------------------------------------------------------------------
    # Deliberately does not raise. An exception escaping a slot on a worker
    # thread doesn't propagate anywhere useful — it just prints a traceback
    # and the thread carries on. So instead we swallow it, tell the UI via
    # signal, and let _poll() retry on its next tick. A disconnected PLC
    # should degrade the HMI, not kill it.
    # -----------------------------------------------------------------------
    def _connect(self):
        try:
            self._plc.open()
            self.connection_changed.emit(True)
        except pyads.ADSError as e:
            self.connection_changed.emit(False)
            self.error_occurred.emit(f"ADS connect failed: {e}")

    # -----------------------------------------------------------------------
    # POLL  —  fires every poll_ms, this is the heartbeat of the module
    # -----------------------------------------------------------------------
    @Slot()
    def _poll(self):
        # Guard clause: if we're not connected, spend this tick trying to
        # reconnect instead of reading. This gives you automatic recovery
        # for free — pull the Ethernet cable, plug it back in, and the HMI
        # reconnects on its own within one poll interval.
        if not self._plc or not self._plc.is_open:
            self._connect()
            return

        try:
            # --- The sum-read ---------------------------------------------
            # read_list_by_name bundles every tag into ONE ADS request and
            # gets ONE response. The alternative — looping and calling
            # read_by_name per tag — costs a full network round-trip each.
            # At 6 tags and 250ms that's 24 round-trips/sec vs 4. On a
            # CX7000 (small ARM controller, modest ADS server) that
            # difference is the gap between "fine" and "sluggish".
            request = [(sym, typ) for sym, typ in TAG_MAP.values()]
            raw = self._plc.read_list_by_name(request)

            # raw comes back keyed by PLC symbol name ("MAIN.PT1"). Flip it
            # to your friendly keys ("pt1") so nothing downstream of here
            # ever needs to know what the PLC calls things.
            values = {key: raw[sym] for key, (sym, _) in TAG_MAP.items()}

            # One signal carrying the whole snapshot, rather than one signal
            # per tag. This means the UI updates atomically — you never
            # render a frame showing a new PT1 next to a stale PT2.
            self.data_updated.emit(values)

        except pyads.ADSError as e:
            # A read failure almost always means the link died. Mark it down,
            # close the handle, and let the guard clause above drive the
            # reconnect on the next tick.
            self.connection_changed.emit(False)
            self.error_occurred.emit(f"ADS read failed: {e}")
            try:
                self._plc.close()
            except pyads.ADSError:
                # close() on an already-dead socket can itself throw.
                # Nothing useful to do about it, so swallow it.
                pass

    # -----------------------------------------------------------------------
    # WRITE  —  the one inbound path, UI thread -> PLC
    # -----------------------------------------------------------------------
    # This slot is invoked from the main thread via AdsClient._write_requested.
    # Because it's a queued signal connection, the actual write EXECUTES on
    # this background thread, sequenced in the same event loop as _poll().
    # That's what keeps the connection single-threaded and safe — a read and
    # a write can never overlap.
    #
    # The `object` in Signal(str, object) is a deliberate choice: it lets the
    # value be an int, bool, or float without needing separate signals per type.
    # -----------------------------------------------------------------------
    @Slot(str, object)
    def write_tag(self, key: str, value):
        # Fail loudly on a typo'd key rather than silently doing nothing.
        if key not in TAG_MAP:
            self.error_occurred.emit(f"Unknown tag: {key}")
            return

        symbol, plc_type = TAG_MAP[key]
        try:
            self._plc.write_by_name(symbol, value, plc_type)
        except pyads.ADSError as e:
            self.error_occurred.emit(f"ADS write to {symbol} failed: {e}")

    # -----------------------------------------------------------------------
    # STOP  —  orderly teardown
    # -----------------------------------------------------------------------
    # Stop the timer FIRST, then close the socket. Reverse that order and a
    # tick already queued in the event loop could fire against a closed
    # connection.
    # -----------------------------------------------------------------------
    @Slot()
    def stop(self):
        if self._timer:
            self._timer.stop()
        if self._plc and self._plc.is_open:
            self._plc.close()
        self.connection_changed.emit(False)


# ===========================================================================
# ADS CLIENT  —  the main-thread facade
# ===========================================================================
# This class exists purely so that screen_setup.py never has to think about
# threads. From the outside it looks like a plain object with three signals
# and a couple of methods. All the moveToThread plumbing is hidden in here.
#
# The pattern is worth internalising: the worker knows about ADS but nothing
# about your UI; the UI knows about this facade but nothing about threads.
# It's the same loose-coupling idea as the navigate_to signal on your screens.
# ===========================================================================
class AdsClient(QObject):

    # These mirror the worker's signals one-for-one. Re-emitting rather than
    # exposing self._worker directly means you could swap pyads for Modbus
    # tomorrow and screen_setup.py wouldn't change a line.
    data_updated = Signal(dict)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)

    # Leading underscore = internal. This is the pipe that carries write
    # requests from the main thread into the worker thread.
    _write_requested = Signal(str, object)

    def __init__(self, ams_net_id: str, ip_address: str, poll_ms: int = 250):
        super().__init__()

        # --- The three lines that do the actual threading ------------------
        self._thread = QThread()                          # an empty thread + event loop
        self._worker = AdsWorker(ams_net_id, ip_address, poll_ms=poll_ms)
        self._worker.moveToThread(self._thread)           # worker now "lives" there
        # -------------------------------------------------------------------
        # After moveToThread, any slot on _worker invoked via a signal will
        # run on _thread instead of here. Note that calling a worker method
        # DIRECTLY (self._worker.write_tag(...)) would bypass this entirely
        # and run on the main thread — which is exactly the bug this whole
        # structure exists to prevent. Always go through a signal.

        # Forward worker signals out to whoever is listening.
        self._worker.data_updated.connect(self.data_updated)
        self._worker.connection_changed.connect(self.connection_changed)
        self._worker.error_occurred.connect(self.error_occurred)

        # Main thread -> worker thread. Qt sees the objects are on different
        # threads and picks a queued connection automatically.
        self._write_requested.connect(self._worker.write_tag)

        # Fires once the thread's event loop is running, kicking off start().
        self._thread.started.connect(self._worker.start)

    def start(self):
        """Spin up the thread. Nothing talks to the PLC until this is called."""
        self._thread.start()

    def write(self, key: str, value):
        """Queue a write. Returns immediately — does NOT wait for the PLC."""
        self._write_requested.emit(key, value)

    def shutdown(self):
        """
        Call from closeEvent. Without this you get 'QThread: Destroyed while
        thread is still running' on exit, and sometimes a hard crash.

        quit() asks the event loop to exit; wait() blocks until it actually
        has. The 2000ms cap means a wedged socket delays your shutdown by two
        seconds instead of hanging the app forever.
        """
        self._worker.stop()
        self._thread.quit()
        self._thread.wait(2000)