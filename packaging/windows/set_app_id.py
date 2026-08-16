"""Grava o System.AppUserModel.ID num atalho .lnk.

Sem isso a notificação do Dito sai com o nome do interpretador — "Python". O
`SetCurrentProcessExplicitAppUserModelID` do processo não basta: o shell só resolve o nome e o
ícone do toast quando existe um atalho no Menu Iniciar carregando o MESMO id nesta propriedade.
E o launcher gerado pelo pip não tem recurso de versão nenhum, então não há de onde tirar o nome.

    python set_app_id.py <caminho.lnk> <app-id>
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

_CLSID_ShellLink = "{00021401-0000-0000-C000-000000000046}"
_IID_IPersistFile = "{0000010B-0000-0000-C000-000000000046}"
_IID_IPropertyStore = "{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}"
_FMTID_AppUserModel = "{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}"
_PID_APP_ID = 5

_CLSCTX_INPROC_SERVER = 1
_COINIT_APARTMENTTHREADED = 0x2
_STGM_READWRITE = 0x00000002

# IUnknown occupies 0-2 in every vtable below.
_VT_QUERY_INTERFACE = 0
_VT_RELEASE = 2
_VT_PERSIST_LOAD = 5
_VT_PERSIST_SAVE = 6
_VT_STORE_SET_VALUE = 6
_VT_STORE_COMMIT = 7

_ole32 = ctypes.WinDLL("ole32", use_last_error=True)



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


class _PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", _GUID), ("pid", wintypes.DWORD)]


class _PROPVARIANT(ctypes.Structure):
    _fields_ = [
        ("vt", wintypes.WORD),
        ("r1", wintypes.WORD),
        ("r2", wintypes.WORD),
        ("r3", wintypes.WORD),
        ("data", ctypes.c_void_p),
        ("pad", ctypes.c_void_p),
    ]


_VT_LPWSTR = 31


def _propvariant_from_string(text: str, out: _PROPVARIANT) -> bool:
    """`InitPropVariantFromString` é inline no header, não exportada — daí montar na mão.

    A string tem que ser do alocador do COM: quem libera é o `PropVariantClear`.
    """
    _ole32.CoTaskMemAlloc.restype = ctypes.c_void_p
    dados = ctypes.create_unicode_buffer(text)
    tamanho = ctypes.sizeof(dados)
    bloco = _ole32.CoTaskMemAlloc(tamanho)
    if not bloco:
        return False
    ctypes.memmove(bloco, dados, tamanho)
    out.vt = _VT_LPWSTR
    out.data = bloco
    return True


def _vcall(pointer, slot: int, restype, *argtypes):
    vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtable[slot])


def _release(pointer) -> None:
    if pointer:
        _vcall(pointer, _VT_RELEASE, ctypes.c_ulong)(pointer)


def set_app_id(lnk: str, app_id: str) -> bool:
    """Abre o atalho, escreve a propriedade e grava de volta."""
    _ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)

    persist = ctypes.c_void_p()
    store = ctypes.c_void_p()
    value = _PROPVARIANT()
    try:
        if _ole32.CoCreateInstance(
            ctypes.byref(_GUID(_CLSID_ShellLink)), None, _CLSCTX_INPROC_SERVER,
            ctypes.byref(_GUID(_IID_IPersistFile)), ctypes.byref(persist),
        ):
            return False

        load = _vcall(persist, _VT_PERSIST_LOAD, ctypes.HRESULT, wintypes.LPCWSTR, wintypes.DWORD)
        if load(persist, lnk, _STGM_READWRITE):
            return False

        query = _vcall(
            persist, _VT_QUERY_INTERFACE, ctypes.HRESULT,
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
        )
        if query(persist, ctypes.byref(_GUID(_IID_IPropertyStore)), ctypes.byref(store)):
            return False

        if not _propvariant_from_string(app_id, value):
            return False

        key = _PROPERTYKEY(_GUID(_FMTID_AppUserModel), _PID_APP_ID)
        set_value = _vcall(
            store, _VT_STORE_SET_VALUE, ctypes.HRESULT,
            ctypes.POINTER(_PROPERTYKEY), ctypes.POINTER(_PROPVARIANT),
        )
        if set_value(store, ctypes.byref(key), ctypes.byref(value)):
            return False

        if _vcall(store, _VT_STORE_COMMIT, ctypes.HRESULT)(store):
            return False

        # None keeps the file it was loaded from; TRUE says we are done writing it. O retorno
        # dele não decide nada: o Commit às vezes já gravou, e aí o Save reclama de um arquivo
        # que não está mais sujo. Quem decide é a leitura de volta, no final.
        save = _vcall(persist, _VT_PERSIST_SAVE, ctypes.HRESULT, wintypes.LPCWSTR, wintypes.BOOL)
        try:
            save(persist, None, True)
        except OSError:
            pass
        return True
    except OSError:
        return False
    finally:
        _ole32.PropVariantClear(ctypes.byref(value))
        _release(store)
        _release(persist)


def read_app_id(lnk: str) -> str | None:
    """Lê de volta o que foi gravado — a prova de que o atalho carrega a identidade."""
    _ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
    persist = ctypes.c_void_p()
    store = ctypes.c_void_p()
    value = _PROPVARIANT()
    try:
        if _ole32.CoCreateInstance(
            ctypes.byref(_GUID(_CLSID_ShellLink)), None, _CLSCTX_INPROC_SERVER,
            ctypes.byref(_GUID(_IID_IPersistFile)), ctypes.byref(persist),
        ):
            return None
        load = _vcall(persist, _VT_PERSIST_LOAD, ctypes.HRESULT, wintypes.LPCWSTR, wintypes.DWORD)
        if load(persist, lnk, 0):
            return None
        query = _vcall(
            persist, _VT_QUERY_INTERFACE, ctypes.HRESULT,
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
        )
        if query(persist, ctypes.byref(_GUID(_IID_IPropertyStore)), ctypes.byref(store)):
            return None
        key = _PROPERTYKEY(_GUID(_FMTID_AppUserModel), _PID_APP_ID)
        get_value = _vcall(
            store, 5, ctypes.HRESULT,
            ctypes.POINTER(_PROPERTYKEY), ctypes.POINTER(_PROPVARIANT),
        )
        if get_value(store, ctypes.byref(key), ctypes.byref(value)):
            return None
        return ctypes.cast(value.data, ctypes.c_wchar_p).value if value.vt == 31 else None
    except OSError:
        return None
    finally:
        _ole32.PropVariantClear(ctypes.byref(value))
        _release(store)
        _release(persist)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    caminho, identidade = sys.argv[1], sys.argv[2]
    set_app_id(caminho, identidade)
    # A prova é ler de volta do disco: é isso que o shell vai ler para nomear a notificação.
    gravado = read_app_id(caminho)
    ok = gravado == identidade
    print(f"{'ok' if ok else 'FALHOU'}: {caminho} -> {gravado}")
    raise SystemExit(0 if ok else 1)
