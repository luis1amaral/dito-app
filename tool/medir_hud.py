"""Fotografa TODOS os estados do HUD com os pixels que a propria janela compos, e mede cada um.

Captura de tela nao serve aqui: a janela do HUD tem alfa por pixel via DWM, e nem BitBlt nem
PrintWindow a enxergam - as duas devolvem preto. Entao o app se fotografa por dentro.

    python tool/medir_hud.py            # compila e mede
    python tool/medir_hud.py --sem-build

Sai 1 se qualquer estado estiver fora de esquadro. As fotos ficam em build/hud/.
"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

from PIL import Image

u32 = ctypes.windll.user32
GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_VISIBLE, WS_EX_TOOLWINDOW, SW_MINIMIZE = 0x10000000, 0x00000080, 6
CB = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

_alvos = [a for a in sys.argv[1:] if not a.startswith('--')]
EXE = _alvos[0] if _alvos else r'build\windows\x64\runner\Debug\dito_app.exe'
FOTOS = os.path.abspath(os.path.join('build', 'hud'))
LOG = os.path.expandvars(r'%LOCALAPPDATA%\dito\logs\app.log')


def pids_do_app():
    saida = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq dito_app.exe', '/NH', '/FO', 'CSV'],
                           capture_output=True, text=True).stdout
    achados = set()
    for linha in saida.splitlines():
        campos = linha.split('","')
        if len(campos) > 1 and campos[1].strip('"').isdigit():
            achados.add(int(campos[1].strip('"')))
    return achados


def janelas(pids):
    achadas = []

    def visita(hwnd, _):
        pid = wintypes.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            r = wintypes.RECT()
            u32.GetWindowRect(hwnd, ctypes.byref(r))
            achadas.append({
                'hwnd': hwnd,
                'ferramenta': bool(u32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW),
                'rect': (r.left, r.top, r.right, r.bottom),
            })
        return True

    u32.EnumWindows(CB(visita), 0)
    return achadas


def janelas_do_app():
    return janelas(pids_do_app())


def minimiza_a_principal(pids):
    def visita(hwnd, _):
        pid = wintypes.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            ex = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            st = u32.GetWindowLongW(hwnd, GWL_STYLE)
            if not (ex & WS_EX_TOOLWINDOW) and (st & WS_VISIBLE):
                u32.ShowWindow(hwnd, SW_MINIMIZE)
        return True

    u32.EnumWindows(CB(visita), 0)


def mede(caminho):
    img = Image.open(caminho).convert('RGBA')
    w, h = img.size
    alfa = img.split()[3].load()
    linhas = [y for y in range(h) if sum(alfa[x, y] > 60 for x in range(w)) > w * 0.10]
    colunas = [x for x in range(w) if sum(alfa[x, y] > 60 for y in range(h)) > h * 0.10]
    if not linhas or not colunas:
        return img, None

    caixa = (colunas[0], linhas[0], colunas[-1] + 1, linhas[-1] + 1)
    problemas = []
    largura, altura = caixa[2] - caixa[0], caixa[3] - caixa[1]
    if abs((w - largura) / 2 - caixa[0]) >= 10:
        problemas.append('fora do centro')
    if h - caixa[3] >= 40:
        problemas.append(f'{h - caixa[3]}px sobrando embaixo')
    limites = (300, 700, 40, 160) if 'cartao' not in caminho else (380, 700, 150, 600)
    if not limites[0] < largura < limites[1]:
        problemas.append(f'largura {largura}')
    if not limites[2] < altura < limites[3]:
        problemas.append(f'altura {altura}')
    return img, (caixa, problemas)


def com_xadrez(img):
    w, h = img.size
    fundo = Image.new('RGB', (w, h), (240, 240, 240))
    for y in range(0, h, 16):
        for x in range(0, w, 16):
            if (x // 16 + y // 16) % 2:
                fundo.paste((208, 208, 208), (x, y, min(x + 16, w), min(y + 16, h)))
    fundo.paste(img, (0, 0), img)
    return fundo


subprocess.run(['taskkill', '/F', '/IM', 'dito_app.exe'], capture_output=True)
subprocess.run(['taskkill', '/F', '/IM', 'dito-engine.exe'], capture_output=True)
while pids_do_app():
    time.sleep(0.25)

# compilar SO com o app morto: exe travado faz o build falhar e a medicao roda no binario velho
if '--sem-build' not in sys.argv:
    if subprocess.run(['flutter', 'build', 'windows', '--debug'], shell=True).returncode != 0:
        raise SystemExit('flutter build falhou')

os.makedirs(FOTOS, exist_ok=True)
for velho in os.listdir(FOTOS):
    os.remove(os.path.join(FOTOS, velho))
marca = os.path.getsize(LOG) if os.path.exists(LOG) else 0

subprocess.Popen([EXE], env=dict(os.environ, DITO_HUD_HOLD='1', DITO_HUD_SHOT=FOTOS),
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

inicio, pronto, sondas = time.time(), False, []
while time.time() - inicio < 120 and not pronto:
    time.sleep(0.3)
    minimiza_a_principal(pids_do_app())
    if not os.path.exists(LOG):
        continue
    with open(LOG, encoding='utf-8', errors='replace') as f:
        f.seek(marca)
        sondas = []
        for linha in f:
            if 'hud_hold: fim' in linha:
                pronto = True
            if 'probe=' in linha and 'hud_hold: ' in linha:
                sondas.append(linha.split('hud_hold: ', 1)[1].strip())

if not pronto:
    raise SystemExit('o HUD nao completou a passagem pelos estados')

# a regiao da janela e o que impede o canvas transparente de comer clique alheio
final = [l for l in sondas if l.startswith('fim ')]
if final:
    import re as _re
    m = _re.search(r'rect=(\d+),(\d+),(\d+),(\d+)', final[0])
    p_ = _re.search(r'pilula=Size\(([\d.]+), ([\d.]+)\).*pos=Offset\(([\d.]+), ([\d.]+)\)', final[0])
    if m and p_:
        L, T = int(m.group(1)), int(m.group(2))
        pw, ph, px_, py_ = (float(g) for g in p_.groups())
        u32.WindowFromPoint.restype = wintypes.HWND
        u32.WindowFromPoint.argtypes = [wintypes.POINT]
        def dono(x, y):
            h = u32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
            return u32.GetAncestor(h, 2)  # GA_ROOT
        alvo = [j for j in janelas_do_app() if j['ferramenta'] and j['rect'][2] - j['rect'][0] == 900]
        hud_hwnd = alvo[0]['hwnd'] if alvo else None
        dentro = dono(L + px_ + pw / 2, T + py_ + ph / 2)
        fora = dono(L + 20, T + 20)
        print()
        print(f'clique no meio da pilula -> {"o HUD" if dentro == hud_hwnd else "outra janela"}'
              f' {"OK" if dentro == hud_hwnd else "FALHA"}')
        print(f'clique no canto vazio ----> {"o HUD" if fora == hud_hwnd else "outra janela"}'
              f' {"FALHA" if fora == hud_hwnd else "OK"}')
        if dentro != hud_hwnd or fora == hud_hwnd:
            print('REPROVOU: a regiao da janela nao esta recortada no conteudo')
            sys.exit(1)
for linha in sondas:
    print(linha)
print()

falhas = 0
for nome in sorted(n for n in os.listdir(FOTOS) if not n.startswith('visto-')):
    img, medida = mede(os.path.join(FOTOS, nome))
    if medida is None:
        print(f'{nome:<20} NAO ACHEI a pilula')
        falhas += 1
        continue
    caixa, problemas = medida
    largura, altura = caixa[2] - caixa[0], caixa[3] - caixa[1]
    veredito = 'OK' if not problemas else 'FALHA: ' + ', '.join(problemas)
    falhas += 1 if problemas else 0
    print(f'{nome:<20} {largura}x{altura} em x={caixa[0]} y={caixa[1]}  {veredito}')
    com_xadrez(img).save(os.path.join(FOTOS, 'visto-' + nome))

print()
print(f'{"REPROVOU" if falhas else "PASSA"}: {falhas} estado(s) fora de esquadro')
sys.exit(1 if falhas else 0)
