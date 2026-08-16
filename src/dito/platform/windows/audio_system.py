"""Mute and volume of the default microphone, straight from WASAPI (the Windows twin of pactl).

Raw COM on purpose: pycaw would add two dependencies for six vtable calls. See the README here.
"""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

from ...audio import devices
from ..source_health import SourceHealth

__all__ = [
    "SourceHealth", "available", "health", "is_muted", "volume_pct",
    "unmute", "set_volume", "default_source_name",
]

_CLSID_MMDeviceEnumerator = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"
_IID_IMMDeviceEnumerator = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"
_IID_IAudioEndpointVolume = "{5CDF2C82-841E-4546-9722-0CF74078229A}"

_E_CAPTURE = 1          # EDataFlow.eCapture
_E_CONSOLE = 0          # ERole.eConsole
_CLSCTX_ALL = 23
_COINIT_APARTMENTTHREADED = 0x2

# IUnknown takes slots 0-2; these are the ones this module calls.
_VT_RELEASE = 2
_VT_GET_DEFAULT_ENDPOINT = 4        # IMMDeviceEnumerator
_VT_ACTIVATE = 3                    # IMMDevice
_VT_SET_MASTER_SCALAR = 7           # IAudioEndpointVolume
_VT_GET_MASTER_SCALAR = 9
_VT_SET_MUTE = 14
_VT_GET_MUTE = 15

_ole32 = ctypes.WinDLL("ole32", use_last_error=True)
_started = threading.local()


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    def __init__(self, text: str) -> None:
        super().__init__()
        _ole32.CLSIDFromString(text, ctypes.byref(self))


def _vcall(pointer, slot: int, restype, *argtypes):
    vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return proto(vtable[slot])


def _release(pointer) -> None:
    if pointer:
        _vcall(pointer, _VT_RELEASE, ctypes.c_ulong)(pointer)


def _com_ready() -> bool:
    """Once per thread; Qt may have gone first, and an already-initialised apartment is fine."""
    if getattr(_started, "done", False):
        return True
    _ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
    _started.done = True
    return True


class _Endpoint:
    """The default capture endpoint's volume interface, released on the way out."""

    def __enter__(self):
        self._enumerator = ctypes.c_void_p()
        self._device = ctypes.c_void_p()
        self._volume = ctypes.c_void_p()
        _com_ready()

        hr = _ole32.CoCreateInstance(
            ctypes.byref(_GUID(_CLSID_MMDeviceEnumerator)), None, _CLSCTX_ALL,
            ctypes.byref(_GUID(_IID_IMMDeviceEnumerator)), ctypes.byref(self._enumerator),
        )
        if hr or not self._enumerator:
            return None

        get_default = _vcall(
            self._enumerator, _VT_GET_DEFAULT_ENDPOINT, ctypes.HRESULT,
            ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p),
        )
        try:
            get_default(self._enumerator, _E_CAPTURE, _E_CONSOLE, ctypes.byref(self._device))
        except OSError:
            return None                 # no microphone at all is not an error, it is an answer
        if not self._device:
            return None

        activate = _vcall(
            self._device, _VT_ACTIVATE, ctypes.HRESULT,
            ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
        )
        try:
            activate(
                self._device, ctypes.byref(_GUID(_IID_IAudioEndpointVolume)),
                _CLSCTX_ALL, None, ctypes.byref(self._volume),
            )
        except OSError:
            return None
        return self._volume if self._volume else None

    def __exit__(self, *_exc) -> bool:
        for pointer in (self._volume, self._device, self._enumerator):
            _release(pointer)
        return False


def available() -> bool:
    """True when the endpoint can actually be opened — the honest twin of `which pactl`."""
    with _Endpoint() as volume:
        return volume is not None


def is_muted(source: str | None = None) -> bool | None:
    """True/False, or None when it could not be determined."""
    with _Endpoint() as volume:
        if volume is None:
            return None
        muted = wintypes.BOOL()
        try:
            _vcall(volume, _VT_GET_MUTE, ctypes.HRESULT, ctypes.POINTER(wintypes.BOOL))(
                volume, ctypes.byref(muted)
            )
        except OSError:
            return None
        return bool(muted.value)


def volume_pct(source: str | None = None) -> int | None:
    with _Endpoint() as volume:
        if volume is None:
            return None
        level = ctypes.c_float()
        try:
            _vcall(volume, _VT_GET_MASTER_SCALAR, ctypes.HRESULT, ctypes.POINTER(ctypes.c_float))(
                volume, ctypes.byref(level)
            )
        except OSError:
            return None
        return int(round(level.value * 100))


def unmute(source: str | None = None) -> bool:
    with _Endpoint() as volume:
        if volume is None:
            return False
        try:
            _vcall(volume, _VT_SET_MUTE, ctypes.HRESULT, wintypes.BOOL, ctypes.c_void_p)(
                volume, False, None
            )
        except OSError:
            return False
        return True


def set_volume(pct: int, source: str | None = None) -> bool:
    with _Endpoint() as volume:
        if volume is None:
            return False
        level = ctypes.c_float(max(0.0, min(100.0, float(pct))) / 100.0)
        try:
            _vcall(
                volume, _VT_SET_MASTER_SCALAR, ctypes.HRESULT, ctypes.c_float, ctypes.c_void_p
            )(volume, level, None)
        except OSError:
            return False
        return True


def default_source_name() -> str | None:
    """sounddevice already resolves this, and asking IPropertyStore again would say the same."""
    try:
        return next((d.name for d in devices.list_inputs() if d.default), None)
    except Exception:
        return None


def health(source: str | None = None) -> SourceHealth:
    return SourceHealth(
        muted=is_muted(),
        volume=volume_pct(),
        name=default_source_name(),
    )
