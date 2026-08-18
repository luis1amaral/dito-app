"""Lista as janelas de topo do dito_app.exe com estilo, visibilidade e retangulo."""
import ctypes, subprocess, sys
from ctypes import wintypes

u32 = ctypes.windll.user32
GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_VISIBLE, WS_MINIMIZE = 0x10000000, 0x20000000
EX = {0x00000008: 'TOPMOST', 0x00000080: 'TOOLWINDOW', 0x08000000: 'NOACTIVATE',
      0x00080000: 'LAYERED', 0x00000020: 'TRANSPARENT'}

pids = set()
for line in subprocess.run(['tasklist', '/FI', 'IMAGENAME eq dito_app.exe', '/NH', '/FO', 'CSV'],
                           capture_output=True, text=True).stdout.splitlines():
    parts = [p.strip('"') for p in line.split('","')]
    if len(parts) > 1 and parts[1].isdigit(): pids.add(int(parts[1]))
if not pids: sys.exit('dito_app.exe nao esta rodando')

CB = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def visita(hwnd, _):
    pid = wintypes.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value not in pids: return True
    titulo = ctypes.create_unicode_buffer(256); u32.GetWindowTextW(hwnd, titulo, 256)
    classe = ctypes.create_unicode_buffer(256); u32.GetClassNameW(hwnd, classe, 256)
    st = u32.GetWindowLongW(hwnd, GWL_STYLE) & 0xFFFFFFFF
    ex = u32.GetWindowLongW(hwnd, GWL_EXSTYLE) & 0xFFFFFFFF
    r = wintypes.RECT(); u32.GetWindowRect(hwnd, ctypes.byref(r))
    flags = ' '.join(n for b, n in EX.items() if ex & b) or '-'
    print(f'hwnd={hwnd:#x} "{titulo.value}" [{classe.value}]')
    print(f'   visivel={bool(st & WS_VISIBLE)} minimizada={bool(st & WS_MINIMIZE)} '
          f'IsWindowVisible={bool(u32.IsWindowVisible(hwnd))}')
    print(f'   rect={r.left},{r.top} ate {r.right},{r.bottom} ({r.right-r.left}x{r.bottom-r.top})')
    print(f'   ex={flags}  dono={u32.GetWindow(hwnd, 4):#x}')
    return True
u32.EnumWindows(CB(visita), 0)
