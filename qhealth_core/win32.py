"""Win32 (ctypes) backend for Windows: raw input, the foreground window, processes and autostart.

Raw Input is used instead of low-level hooks on purpose: hooks sit in the system input chain, so a
busy Python interpreter would add input lag for every app. Raw Input is delivered as ordinary
messages to a hidden window and can never slow down the user's typing.
"""
import ctypes
import os
import sys
from ctypes import wintypes
from typing import Callable, Dict, List, Optional, Set, Tuple

if sys.platform != "win32":
    raise ImportError("qhealth_core.win32 is only available on Windows")

from .keymap import scancode_to_evdev

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
version = ctypes.WinDLL("version", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

WM_QUIT, WM_CLOSE, WM_INPUT = 0x0012, 0x0010, 0x00FF
HWND_MESSAGE = wintypes.HWND(-3)
RIDEV_INPUTSINK = 0x00000100
RID_INPUT = 0x10000003
RIM_TYPEMOUSE, RIM_TYPEKEYBOARD = 0, 1
RI_KEY_BREAK, RI_KEY_E0, RI_KEY_E1 = 0x01, 0x02, 0x04
MOUSE_BUTTONS = ((0x0001, "left"), (0x0004, "right"), (0x0010, "middle"), (0x0040, "side1"), (0x0100, "side2"))
RI_MOUSE_WHEEL, RI_MOUSE_HWHEEL = 0x0400, 0x0800
PROCESS_TERMINATE, PROCESS_QUERY_LIMITED_INFORMATION, SYNCHRONIZE = 0x0001, 0x1000, 0x00100000
WAIT_TIMEOUT = 0x00000102
TH32CS_SNAPPROCESS = 0x00000002
GW_OWNER = 4
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wintypes.DWORD), ("dwSize", wintypes.DWORD),
                ("hDevice", wintypes.HANDLE), ("wParam", wintypes.WPARAM)]


class _MOUSEBUTTONS(ctypes.Structure):
    _fields_ = [("usButtonFlags", wintypes.USHORT), ("usButtonData", wintypes.USHORT)]


class _MOUSEUNION(ctypes.Union):
    _fields_ = [("ulButtons", wintypes.ULONG), ("buttons", _MOUSEBUTTONS)]


class RAWMOUSE(ctypes.Structure):
    _fields_ = [("usFlags", wintypes.USHORT), ("u", _MOUSEUNION), ("ulRawButtons", wintypes.ULONG),
                ("lLastX", wintypes.LONG), ("lLastY", wintypes.LONG), ("ulExtraInformation", wintypes.ULONG)]


class RAWKEYBOARD(ctypes.Structure):
    _fields_ = [("MakeCode", wintypes.USHORT), ("Flags", wintypes.USHORT), ("Reserved", wintypes.USHORT),
                ("VKey", wintypes.USHORT), ("Message", wintypes.UINT), ("ExtraInformation", wintypes.ULONG)]


class _RAWDATA(ctypes.Union):
    _fields_ = [("mouse", RAWMOUSE), ("keyboard", RAWKEYBOARD)]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("data", _RAWDATA)]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ULONG_PTR), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]


def _sig(fn, argtypes, restype):
    fn.argtypes, fn.restype = argtypes, restype


_sig(user32.DefWindowProcW, [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], LRESULT)
_sig(user32.RegisterClassExW, [ctypes.POINTER(WNDCLASSEXW)], wintypes.ATOM)
_sig(user32.CreateWindowExW, [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                              wintypes.HINSTANCE, wintypes.LPVOID], wintypes.HWND)
_sig(user32.DestroyWindow, [wintypes.HWND], wintypes.BOOL)
_sig(user32.RegisterRawInputDevices, [ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT], wintypes.BOOL)
_sig(user32.GetRawInputData, [wintypes.HANDLE, wintypes.UINT, wintypes.LPVOID, ctypes.POINTER(wintypes.UINT),
                              wintypes.UINT], wintypes.UINT)
_sig(user32.GetMessageW, [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT], wintypes.BOOL)
_sig(user32.TranslateMessage, [ctypes.POINTER(wintypes.MSG)], wintypes.BOOL)
_sig(user32.DispatchMessageW, [ctypes.POINTER(wintypes.MSG)], LRESULT)
_sig(user32.PostThreadMessageW, [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], wintypes.BOOL)
_sig(user32.PostMessageW, [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], wintypes.BOOL)
_sig(user32.GetForegroundWindow, [], wintypes.HWND)
_sig(user32.GetWindowThreadProcessId, [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD)
_sig(user32.GetWindowTextLengthW, [wintypes.HWND], ctypes.c_int)
_sig(user32.GetWindowTextW, [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int)
_sig(user32.GetClassNameW, [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int)
_sig(user32.EnumWindows, [WNDENUMPROC, wintypes.LPARAM], wintypes.BOOL)
_sig(user32.EnumChildWindows, [wintypes.HWND, WNDENUMPROC, wintypes.LPARAM], wintypes.BOOL)
_sig(user32.IsWindowVisible, [wintypes.HWND], wintypes.BOOL)
_sig(user32.GetWindow, [wintypes.HWND, wintypes.UINT], wintypes.HWND)
_sig(user32.GetWindowLongPtrW, [wintypes.HWND, ctypes.c_int], ctypes.c_ssize_t)
_sig(kernel32.GetModuleHandleW, [wintypes.LPCWSTR], wintypes.HMODULE)
_sig(kernel32.GetCurrentThreadId, [], wintypes.DWORD)
_sig(kernel32.OpenProcess, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE)
_sig(kernel32.CloseHandle, [wintypes.HANDLE], wintypes.BOOL)
_sig(kernel32.TerminateProcess, [wintypes.HANDLE, wintypes.UINT], wintypes.BOOL)
_sig(kernel32.WaitForSingleObject, [wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD)
_sig(kernel32.QueryFullProcessImageNameW, [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                           ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL)
_sig(kernel32.CreateToolhelp32Snapshot, [wintypes.DWORD, wintypes.DWORD], wintypes.HANDLE)
_sig(kernel32.Process32FirstW, [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)], wintypes.BOOL)
_sig(kernel32.Process32NextW, [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)], wintypes.BOOL)
_sig(kernel32.ProcessIdToSessionId, [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL)
_sig(version.GetFileVersionInfoSizeW, [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD)
_sig(version.GetFileVersionInfoW, [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID], wintypes.BOOL)
_sig(version.VerQueryValueW, [wintypes.LPCVOID, wintypes.LPCWSTR, ctypes.POINTER(wintypes.LPVOID),
                              ctypes.POINTER(wintypes.UINT)], wintypes.BOOL)
_sig(shell32.SetCurrentProcessExplicitAppUserModelID, [wintypes.LPCWSTR], ctypes.c_long)

INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value


# ----------------------------------------------------------------------------------------- input
class RawInputListener:
    """Receives physical keyboard / mouse input system-wide on a hidden message-only window.

    on_key(evdev_code_or_None, is_repeat), on_click(button_name), on_scroll() run on the listener thread.
    Injected input (SendInput, remote tools) has no device handle and is ignored, like evdev's hardware-only view.
    """

    def __init__(self, on_key: Callable[[Optional[int], bool], None], on_click: Callable[[str], None],
                 on_scroll: Callable[[], None]):
        self.on_key, self.on_click, self.on_scroll = on_key, on_click, on_scroll
        self.thread_id = 0
        self._down: Set[Tuple[int, bool]] = set()
        self._wndproc = WNDPROC(self._proc)  # keep a reference: Windows calls it for the window's lifetime

    def _proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_INPUT:
            try:
                self._handle(lparam)
            except Exception:
                pass
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _handle(self, lparam):
        raw = RAWINPUT()
        size = wintypes.UINT(ctypes.sizeof(raw))
        if user32.GetRawInputData(lparam, RID_INPUT, ctypes.byref(raw), ctypes.byref(size),
                                  ctypes.sizeof(RAWINPUTHEADER)) == 0xFFFFFFFF:
            return
        if not raw.header.hDevice:
            return
        if raw.header.dwType == RIM_TYPEKEYBOARD:
            kb = raw.data.keyboard
            if kb.Flags & RI_KEY_E1:
                return
            key = (kb.MakeCode, bool(kb.Flags & RI_KEY_E0))
            if kb.Flags & RI_KEY_BREAK:
                self._down.discard(key)
                return
            repeat = key in self._down
            self._down.add(key)
            self.on_key(scancode_to_evdev(*key), repeat)
        elif raw.header.dwType == RIM_TYPEMOUSE:
            flags = raw.data.mouse.u.buttons.usButtonFlags
            for bit, name in MOUSE_BUTTONS:
                if flags & bit:
                    self.on_click(name)
            if flags & (RI_MOUSE_WHEEL | RI_MOUSE_HWHEEL):
                self.on_scroll()

    def run(self):
        """Blocks running the message loop; returns after stop() or if registration fails."""
        self.thread_id = kernel32.GetCurrentThreadId()
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW(cbSize=ctypes.sizeof(WNDCLASSEXW), lpfnWndProc=self._wndproc, hInstance=hinst,
                         lpszClassName="QHealthRawInput")
        user32.RegisterClassExW(ctypes.byref(wc))  # fails harmlessly if already registered
        hwnd = user32.CreateWindowExW(0, "QHealthRawInput", "QHealth input", 0, 0, 0, 0, 0,
                                      HWND_MESSAGE, None, hinst, None)
        if not hwnd:
            return
        devices = (RAWINPUTDEVICE * 2)(RAWINPUTDEVICE(0x01, 0x06, RIDEV_INPUTSINK, hwnd),   # keyboard
                                       RAWINPUTDEVICE(0x01, 0x02, RIDEV_INPUTSINK, hwnd))   # mouse
        if user32.RegisterRawInputDevices(devices, 2, ctypes.sizeof(RAWINPUTDEVICE)):
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        user32.DestroyWindow(hwnd)

    def stop(self):
        if self.thread_id:
            user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)


# -------------------------------------------------------------------------------------- windows
def _window_pid(hwnd) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _window_text(hwnd) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _class_name(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def foreground_window() -> Optional[Tuple[int, str, str]]:
    """(pid, title, window class) of the focused window, or None (locked screen, nothing focused)."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = _window_pid(hwnd)
    # UWP apps are hosted by ApplicationFrameHost; the real app owns a child window
    if process_name(pid) == "applicationframehost":
        found = []

        def child(h, _):
            p = _window_pid(h)
            if p != pid:
                found.append(p)
                return False
            return True

        user32.EnumChildWindows(hwnd, WNDENUMPROC(child), 0)
        if found:
            pid = found[0]
    return pid, _window_text(hwnd), _class_name(hwnd)


def _app_windows() -> List[Tuple[int, int]]:
    """(hwnd, pid) of visible, titled, unowned top-level windows: the windows a user thinks of as apps."""
    out = []

    def each(hwnd, _):
        if (user32.IsWindowVisible(hwnd) and not user32.GetWindow(hwnd, GW_OWNER)
                and not user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW
                and user32.GetWindowTextLengthW(hwnd) > 0):
            out.append((hwnd, _window_pid(hwnd)))
        return True

    user32.EnumWindows(WNDENUMPROC(each), 0)
    return out


def gui_processes() -> List[Tuple[int, str]]:
    """(pid, exe name) of processes in this session that currently show an app window."""
    session = _session(os.getpid())
    seen: Dict[int, str] = {}
    for _, pid in _app_windows():
        if pid not in seen and _session(pid) == session:
            seen[pid] = process_name(pid)
    return [(pid, name) for pid, name in seen.items() if name]


def close_windows(pids: Set[int]) -> None:
    """Politely ask apps to close (WM_CLOSE), like SIGTERM."""
    for hwnd, pid in _app_windows():
        if pid in pids:
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


# ------------------------------------------------------------------------------------ processes
def process_path(pid: int) -> str:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        return buf.value if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)) else ""
    finally:
        kernel32.CloseHandle(handle)


def exe_stem(path_or_name: str) -> str:
    """'C:\\...\\Code.exe' -> 'code': the app id QHealth uses on Windows."""
    base = os.path.basename(path_or_name).lower()
    return base[:-4] if base.endswith(".exe") else base


def process_name(pid: int) -> str:
    return exe_stem(process_path(pid))


def _session(pid: int) -> int:
    sid = wintypes.DWORD(0xFFFFFFFF)
    kernel32.ProcessIdToSessionId(pid, ctypes.byref(sid))
    return sid.value


def processes() -> List[Tuple[int, int, str]]:
    """(pid, parent pid, exe name) for every process in the current session."""
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID_HANDLE_VALUE:
        return []
    session = _session(os.getpid())
    out = []
    try:
        entry = PROCESSENTRY32W(dwSize=ctypes.sizeof(PROCESSENTRY32W))
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            pid = entry.th32ProcessID
            if _session(pid) == session:
                out.append((pid, entry.th32ParentProcessID, exe_stem(entry.szExeFile)))
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    return out


def process_alive(pid: int) -> bool:
    handle = kernel32.OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        return kernel32.WaitForSingleObject(handle, 0) == WAIT_TIMEOUT
    finally:
        kernel32.CloseHandle(handle)


def terminate(pid: int) -> bool:
    handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if not handle:
        return False
    try:
        return bool(kernel32.TerminateProcess(handle, 1))
    finally:
        kernel32.CloseHandle(handle)


def file_description(path: str) -> str:
    """The exe's own name for itself ('Visual Studio Code', 'Google Chrome'), from its version resource."""
    size = version.GetFileVersionInfoSizeW(path, None)
    if not size:
        return ""
    data = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(path, 0, size, data):
        return ""
    ptr, length = wintypes.LPVOID(), wintypes.UINT()
    tables = []
    if version.VerQueryValueW(data, "\\VarFileInfo\\Translation", ctypes.byref(ptr), ctypes.byref(length)) and length.value >= 4:
        lang, codepage = ctypes.cast(ptr, ctypes.POINTER(wintypes.WORD * 2)).contents
        tables.append(f"{lang:04x}{codepage:04x}")
    tables += ["040904b0", "040904e4", "04090000"]
    for field in ("FileDescription", "ProductName"):
        for table in tables:
            if (version.VerQueryValueW(data, f"\\StringFileInfo\\{table}\\{field}", ctypes.byref(ptr), ctypes.byref(length))
                    and length.value > 1):
                text = ctypes.wstring_at(ptr, length.value).rstrip("\0").strip()
                if text:
                    return text
    return ""


# ------------------------------------------------------------------------------------ app shell
APP_USER_MODEL_ID = "Qssaf.QHealth"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "QHealth"  # same value the installer's "Start with Windows" option writes


def set_app_user_model_id() -> None:
    """Group the taskbar button under QHealth's own icon instead of python.exe's."""
    shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)


def autostart_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pythonw if os.path.exists(pythonw) else sys.executable
    return f'"{exe}" -m qhealth_core.cli --minimized'


def autostart_enabled() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, RUN_VALUE)
            return True
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass
