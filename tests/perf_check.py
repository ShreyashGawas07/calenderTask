"""Idle performance check (a script, not part of unittest discovery).

    .venv\\Scripts\\python tests\\perf_check.py on|off [tasks]

Starts the app on a temporary data folder with today's glow on or off, lets it idle on the
wallpaper and measures CPU (in cycles) over 20 s, thread count, working set and child processes.
Exits 1 if CPU >= 0.1 % of one core, more than 3 threads, any child process, or > 70 MB.
"""
import ctypes
import os
import sys
import tempfile
import threading
import time
from ctypes import wintypes
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calendardesk import model  # noqa: E402
from calendardesk.app import App  # noqa: E402
from calendardesk.store import Store  # noqa: E402

WARMUP_S, MEASURE_S = 3, 20


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260)]


def _cycles():
    k32 = ctypes.WinDLL("kernel32")
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.QueryProcessCycleTime.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_ulonglong)]
    n = ctypes.c_ulonglong()
    k32.QueryProcessCycleTime(k32.GetCurrentProcess(), ctypes.byref(n))
    return n.value


def cycles_per_second():
    """CPU cycles one busy core runs per second (time.process_time ticks in 15.6 ms steps on Windows,
    far too coarse for an app that is idle, so the check counts cycles instead)."""
    c0, t0 = _cycles(), time.perf_counter()
    while time.perf_counter() - t0 < 0.3:
        pass
    return (_cycles() - c0) / (time.perf_counter() - t0)


def working_set_mb():
    k32 = ctypes.WinDLL("kernel32")
    psapi = ctypes.WinDLL("psapi")
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD]
    c = PROCESS_MEMORY_COUNTERS()
    c.cb = ctypes.sizeof(c)
    psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return c.WorkingSetSize / 2**20


def child_processes():
    k32 = ctypes.WinDLL("kernel32")
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    e = PROCESSENTRY32W()
    e.dwSize = ctypes.sizeof(e)
    kids = []
    ok = k32.Process32FirstW(snap, ctypes.byref(e))
    while ok:
        if e.th32ParentProcessID == os.getpid():
            kids.append(e.szExeFile)
        ok = k32.Process32NextW(snap, ctypes.byref(e))
    k32.CloseHandle(snap)
    return kids


def main():
    glow = (sys.argv[1] if len(sys.argv) > 1 else "on") == "on"
    n_tasks = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    store = Store(tempfile.mkdtemp(prefix="cd-perf-"))
    store.settings["today_glow"] = glow
    today = date.today()
    for i in range(n_tasks):
        store.data["tasks"].append(model.new_task(f"task {i}", today.replace(day=1 + i % 28)))
    app = App(store, tray=True)
    result = {}

    def crashed(*exc):  # never hang on an error inside a timer callback
        import traceback
        traceback.print_exception(*exc)
        app.quit()
        sys.exit(2)
    app.root.report_callback_exception = crashed

    def start():
        result["hz"] = cycles_per_second()
        result["t0"] = (_cycles(), time.monotonic())
        app.root.after(MEASURE_S * 1000, stop)

    def stop():
        cpu0, wall0 = result["t0"]
        result["cpu"] = 100 * (_cycles() - cpu0) / result["hz"] / (time.monotonic() - wall0)
        result["threads"] = threading.active_count()
        result["mem"] = working_set_mb()
        result["kids"] = child_processes()
        app.quit()

    app.root.after(WARMUP_S * 1000, start)
    app.run()
    ok = result["cpu"] < 0.1 and result["threads"] <= 3 and not result["kids"] and result["mem"] < 70
    print(f"glow {'on' if glow else 'off'}: CPU {result['cpu']:.3f}% of one core, threads {result['threads']}, "
          f"memory {result['mem']:.1f} MB, child processes {result['kids'] or 0} -> {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
