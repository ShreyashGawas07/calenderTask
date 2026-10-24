"""Small Win32 helpers via ctypes: DPI, desktop pinning, global hotkey, single instance, startup."""
import ctypes
import os
import sys
import threading
import winreg
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.GetAncestor.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
user32.SetWindowLongPtrW.restype = ctypes.c_void_p
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_uint]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
kernel32.CreateMutexW.restype = wintypes.HANDLE
WINEVENTPROC = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, wintypes.LONG,
                                  wintypes.LONG, wintypes.DWORD, wintypes.DWORD)
user32.SetWinEventHook.restype = wintypes.HANDLE
user32.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE, WINEVENTPROC,
                                   wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
user32.UnhookWinEvent.restype = wintypes.BOOL
user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.SystemParametersInfoW.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
user32.GetMessageW.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, ctypes.c_uint, ctypes.c_uint]
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

GWLP_HWNDPARENT = -8
GA_ROOT = 2
HWND_TOP, HWND_BOTTOM, HWND_TOPMOST, HWND_NOTOPMOST = 0, 1, -1, -2
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x1, 0x2, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
EVENT_SYSTEM_FOREGROUND, WINEVENT_OUTOFCONTEXT = 0x0003, 0x0000
ERROR_ALREADY_EXISTS = 183
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "CalendarDesk"


def set_dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        user32.SetProcessDPIAware()


_mutex = None


def single_instance(name="Local\\CalendarDesk.SingleInstance"):
    """True if this is the only running copy."""
    global _mutex
    _mutex = kernel32.CreateMutexW(None, False, name)
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS


def work_area():
    """(left, top, right, bottom) of the primary screen minus the taskbar."""
    rect = wintypes.RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
    return rect.left, rect.top, rect.right, rect.bottom


def hwnd_of(tk_window):
    return user32.GetAncestor(tk_window.winfo_id(), GA_ROOT)


def pin_to_desktop(hwnd):
    """Make the desktop (Progman) own the window so it stays on the wallpaper through Show desktop."""
    progman = user32.FindWindowW("Progman", None)
    if progman:
        user32.SetWindowLongPtrW(hwnd, GWLP_HWNDPARENT, progman)
    send_to_bottom(hwnd)


def send_to_bottom(hwnd):
    user32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


def raise_window(hwnd):
    """Put the window above normal windows without taking focus."""
    flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
    user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)


def bring_to_front(hwnd):
    """Raise and focus. Windows refuses focus changes from background apps, so briefly
    share input state with the current foreground thread, which permits it."""
    raise_window(hwnd)
    fg_tid = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
    my_tid = kernel32.GetCurrentThreadId()
    attached = fg_tid and fg_tid != my_tid and user32.AttachThreadInput(my_tid, fg_tid, True)
    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    if attached:
        user32.AttachThreadInput(my_tid, fg_tid, False)


def foreground_is_ours():
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
    return pid.value == os.getpid()


def desktop_is_foreground():
    """True when the desktop itself (the wallpaper) is the active window."""
    buf = ctypes.create_unicode_buffer(32)
    user32.GetClassNameW(user32.GetForegroundWindow(), buf, 32)
    return buf.value in ("Progman", "WorkerW")


class ForegroundHook:
    """Calls `on_change()` (soon after, from Tk's event loop) whenever a window comes to the front, so
    nothing has to poll for it. Set up from the Tk thread: the out-of-context events then arrive through
    Tk's own message loop, so this adds no thread. `handle` is None if it couldn't be set up.

    The event arrives nested inside Tk's event processing, where calling tkinter would wreck its saved
    Python thread state and crash the interpreter. So the hook only asks Tcl, through its C API, to run
    `after 0 <on_change>`; tkinter then makes that call the normal way."""
    TCL_EVAL_GLOBAL = 0x20000

    def __init__(self, widget, on_change):
        self.handle = None
        tcl = self._loaded_tcl(widget)
        if tcl is None:
            return
        interp = widget.tk.interpaddr()
        self._command = widget.register(on_change)
        script = f"after 0 {self._command}".encode()
        self._widget = widget

        def fire(*args):
            if self.handle and not tcl.Tcl_InterpDeleted(interp):
                state = tcl.Tcl_SaveInterpState(interp, 0)  # it may arrive in the middle of a Tk command
                tcl.Tcl_EvalEx(interp, script, -1, self.TCL_EVAL_GLOBAL)
                tcl.Tcl_RestoreInterpState(interp, state)
        self._proc = WINEVENTPROC(fire)  # kept referenced while hooked
        self.handle = user32.SetWinEventHook(EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, None,
                                             self._proc, 0, 0, WINEVENT_OUTOFCONTEXT) or None
        if not self.handle:
            widget.deletecommand(self._command)

    @staticmethod
    def _loaded_tcl(widget):
        """The Tcl library _tkinter is already using (never load another copy), or None."""
        ver = widget.tk.call("info", "tclversion").replace(".", "")
        for name in (f"tcl{ver}t.dll", f"tcl{ver}.dll", f"tcl9tcl{ver}.dll"):
            module = kernel32.GetModuleHandleW(name)
            if module:
                break
        else:
            return None
        tcl = ctypes.CDLL(name, handle=module)
        tcl.Tcl_EvalEx.restype = ctypes.c_int
        tcl.Tcl_EvalEx.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
        tcl.Tcl_SaveInterpState.restype = ctypes.c_void_p
        tcl.Tcl_SaveInterpState.argtypes = [ctypes.c_void_p, ctypes.c_int]
        tcl.Tcl_RestoreInterpState.restype = ctypes.c_int
        tcl.Tcl_RestoreInterpState.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        tcl.Tcl_InterpDeleted.restype = ctypes.c_int
        tcl.Tcl_InterpDeleted.argtypes = [ctypes.c_void_p]
        return tcl

    def stop(self):
        if self.handle:
            user32.UnhookWinEvent(self.handle)
            self.handle = None
            self._widget.deletecommand(self._command)


class HotkeyThread(threading.Thread):
    """Registers Ctrl+Alt+<key> and calls `on_press()` (from this thread) when it is pressed."""

    def __init__(self, key, on_press):
        super().__init__(daemon=True)
        self.key = key.upper()[:1] or "C"
        self.on_press = on_press
        self.registered = threading.Event()
        self.ok = False

    def run(self):
        self.tid = kernel32.GetCurrentThreadId()
        self.ok = bool(user32.RegisterHotKey(None, 1, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord(self.key)))
        self.registered.set()
        if not self.ok:
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                self.on_press()
        user32.UnregisterHotKey(None, 1)

    def stop(self):
        if self.ok:
            user32.PostThreadMessageW(self.tid, WM_QUIT, 0, 0)


def launch_command():
    """Command line that starts this app without a console window, as a single process
    (the main pythonw.exe; a venv's pythonw.exe is a stub that spawns a second process)."""
    exe = os.path.join(sys.base_prefix, "pythonw.exe")
    if not os.path.exists(exe):
        exe = sys.executable
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "CalendarDesk.pyw")
    return f'"{exe}" "{script}"'


def get_startup():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_VALUE)
            return True
    except OSError:
        return False


def set_startup(enabled):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, RUN_VALUE, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_VALUE)
            except FileNotFoundError:
                pass
