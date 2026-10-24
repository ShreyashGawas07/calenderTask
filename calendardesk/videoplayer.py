"""Windows' own media player (Media Foundation's MFPlay) drawing a muted, looping video into a window.

Decoding and scaling run in Windows' media pipeline (hardware accelerated where the PC supports it),
not in Python, so a playing video costs a few percent of one core and a paused one nothing. Events
arrive through the window messages Tk already pumps, so no thread is added here.
"""
import ctypes
from ctypes import wintypes

HRESULT = ctypes.c_long
EVENT_PLAY, EVENT_MEDIAITEM_SET, EVENT_ERROR, EVENT_PLAYBACK_ENDED = 0, 6, 10, 11
VT_I8 = 20
MFVideoARMode_None = 0


class _PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort), ("r3", ctypes.c_ushort),
                ("val", ctypes.c_longlong), ("pad", ctypes.c_void_p)]


class _GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]


class _EVENT_HEADER(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("hr", HRESULT), ("player", ctypes.c_void_p), ("state", ctypes.c_int),
                ("props", ctypes.c_void_p)]


class _RECTF(ctypes.Structure):
    _fields_ = [("left", ctypes.c_float), ("top", ctypes.c_float), ("right", ctypes.c_float),
                ("bottom", ctypes.c_float)]


_QI = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
_REF = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
_EVENT = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.POINTER(_EVENT_HEADER))

# IMFPMediaPlayer vtable slots (mfplay.h)
_PLAY, _PAUSE, _SET_POSITION, _SET_MUTE, _NATIVE_SIZE = 3, 4, 7, 24, 25
_SET_SOURCE_RECT, _SET_ASPECT_MODE, _UPDATE_VIDEO, _SHUTDOWN, _RELEASE = 27, 29, 32, 38, 2


def available():
    try:
        ctypes.WinDLL("mfplay")
        return True
    except OSError:
        return False


def cover_rect(src_w, src_h, dst_w, dst_h):
    """The part of the source (as 0..1 fractions) that fills dst exactly, cropping the overflow."""
    if min(src_w, src_h, dst_w, dst_h) <= 0:
        return 0.0, 0.0, 1.0, 1.0
    src, dst = src_w / src_h, dst_w / dst_h
    if src > dst:  # wider than the window: crop the sides
        keep = dst / src
        return (1 - keep) / 2, 0.0, (1 + keep) / 2, 1.0
    keep = src / dst
    return 0.0, (1 - keep) / 2, 1.0, (1 + keep) / 2


class VideoPlayer:
    """Plays `path` muted and looping into the window `hwnd`, filling it (cropping, never stretching)."""

    def __init__(self, hwnd, path, on_error=None):
        self.hwnd, self.on_error = hwnd, on_error
        self.native = None
        self.playing = False
        self._player = ctypes.c_void_p()
        self._closed = False
        ctypes.WinDLL("ole32").CoInitializeEx(None, 2)  # apartment threaded, like Tk's thread
        # A COM object for the callback: a pointer to a vtable of four functions. Kept on self so
        # nothing is garbage-collected while Windows can still call it.
        self._fns = [_QI(self._qi), _REF(lambda this: 1), _REF(lambda this: 1), _EVENT(self._event)]
        self._vtable = (ctypes.c_void_p * 4)(*[ctypes.cast(f, ctypes.c_void_p) for f in self._fns])
        self._callback = ctypes.pointer(ctypes.c_void_p(ctypes.addressof(self._vtable)))
        mfplay = ctypes.WinDLL("mfplay")
        mfplay.MFPCreateMediaPlayer.argtypes = [wintypes.LPCWSTR, wintypes.BOOL, ctypes.c_int, ctypes.c_void_p,
                                                wintypes.HWND, ctypes.POINTER(ctypes.c_void_p)]
        mfplay.MFPCreateMediaPlayer.restype = HRESULT
        hr = mfplay.MFPCreateMediaPlayer(path, False, 0, ctypes.cast(self._callback, ctypes.c_void_p), hwnd,
                                         ctypes.byref(self._player))
        if hr != 0 or not self._player:
            self._player = ctypes.c_void_p()
            raise OSError(f"Windows could not open this video (0x{hr & 0xFFFFFFFF:08X})")
        self._call(_SET_MUTE, HRESULT, wintypes.BOOL)(self._player, True)

    def _call(self, index, restype, *argtypes):
        vtbl = ctypes.cast(ctypes.cast(self._player, ctypes.POINTER(ctypes.c_void_p))[0],
                           ctypes.POINTER(ctypes.c_void_p))
        return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtbl[index])

    @staticmethod
    def _qi(this, iid, out):
        out[0] = this
        return 0

    def _event(self, this, header):
        if self._closed:
            return
        kind = header.contents.type
        if kind == EVENT_MEDIAITEM_SET:
            native = (wintypes.SIZE(), wintypes.SIZE())
            self._call(_NATIVE_SIZE, HRESULT, ctypes.POINTER(wintypes.SIZE), ctypes.POINTER(wintypes.SIZE))(
                self._player, ctypes.byref(native[0]), ctypes.byref(native[1]))
            self.native = (native[0].cx, native[0].cy)
            self.fit()
            self._call(_PLAY, HRESULT)(self._player)  # even when paused: shows the first frame, not black
        elif kind == EVENT_PLAY and not self.playing:
            self._call(_PAUSE, HRESULT)(self._player)
        elif kind == EVENT_PLAYBACK_ENDED:  # loop
            pos = _PROPVARIANT(vt=VT_I8, val=0)
            self._call(_SET_POSITION, HRESULT, ctypes.POINTER(_GUID), ctypes.POINTER(_PROPVARIANT))(
                self._player, ctypes.byref(_GUID()), ctypes.byref(pos))
            if self.playing:
                self._call(_PLAY, HRESULT)(self._player)
        elif kind == EVENT_ERROR and self.on_error:
            self.on_error(header.contents.hr)

    def fit(self):
        """Crop to fill the window; call after the window changes size."""
        if not self._player or not self.native:
            return
        rect = wintypes.RECT()
        ctypes.windll.user32.GetClientRect(self.hwnd, ctypes.byref(rect))
        l, t, r, b = cover_rect(self.native[0], self.native[1], rect.right, rect.bottom)
        self._call(_SET_ASPECT_MODE, HRESULT, ctypes.c_int)(self._player, MFVideoARMode_None)
        self._call(_SET_SOURCE_RECT, HRESULT, ctypes.POINTER(_RECTF))(self._player, ctypes.byref(_RECTF(l, t, r, b)))
        self._call(_UPDATE_VIDEO, HRESULT)(self._player)

    def play(self):
        self.playing = True
        if self._player and self.native:
            self._call(_PLAY, HRESULT)(self._player)

    def pause(self):
        self.playing = False
        if self._player and self.native:
            self._call(_PAUSE, HRESULT)(self._player)

    def close(self):
        if self._player and not self._closed:
            self._closed = True
            self._call(_SHUTDOWN, HRESULT)(self._player)
            self._call(_RELEASE, ctypes.c_ulong)(self._player)
            self._player = ctypes.c_void_p()
