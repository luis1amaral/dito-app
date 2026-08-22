#!/usr/bin/env python3
"""Ditado completo sem falar: injeta um WAV com fala real, espera o cartao e o resolve."""
import argparse
import pathlib
import subprocess
import sys
import time

import numpy as np
from Xlib import X, display
from Xlib.ext import shape

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from medir_travamento import Sonda, acha_pid, janelas_do, separa

# No repo, nao na biblioteca: desde a 1.6.4 o app nao gera mais WAV para repor esta fala.
WAV = str(pathlib.Path(__file__).resolve().parent / 'fixtures/fala.wav')
REMEDIO = None
XID = None


def remedio_opacidade():
    subprocess.run(['xprop', '-id', XID, '-f', '_NET_WM_WINDOW_OPACITY', '32c',
                    '-set', '_NET_WM_WINDOW_OPACITY', '0'], check=False)


def remedio_mover():
    g = MOVER[0]
    subprocess.run(['xdotool', 'windowmove', XID, str(g[0] + 1), str(g[1])], check=False)
    time.sleep(0.12)
    subprocess.run(['xdotool', 'windowmove', XID, str(g[0]), str(g[1])], check=False)


def remedio_encolhe():
    g = MOVER[0]
    subprocess.run(['xdotool', 'windowsize', XID, '1', '1'], check=False)
    time.sleep(0.12)
    subprocess.run(['xdotool', 'windowsize', XID, str(g[2]), str(g[3])], check=False)


MOVER = [(0, 0, 900, 900)]
REMEDIOS = {'nenhum': None, 'opacidade': remedio_opacidade,
            'mover': remedio_mover, 'encolhe': remedio_encolhe}


def rects(w):
    try:
        return w.shape_get_rectangles(shape.SK.Input).rectangles
    except Exception:
        return []


def bbox(w):
    r = rects(w)
    if not r:
        return (0, 0, 0)
    x0 = min(x.x for x in r); y0 = min(x.y for x in r)
    x1 = max(x.x + x.width for x in r); y1 = max(x.y + x.height for x in r)
    return (x1 - x0, y1 - y0, len(r))


def recorta(root, g, r, caixa=None):
    """Recorte da tela na area dos retangulos (ou numa caixa ja conhecida)."""
    if caixa is None:
        x0 = min(x.x for x in r); y0 = min(x.y for x in r)
        x1 = max(x.x + x.width for x in r); y1 = max(x.y + x.height for x in r)
        caixa = (x0, y0, x1 - x0, y1 - y0)
    x0, y0, cw, ch = caixa
    img = root.get_image(g.x + x0, g.y + y0, cw, ch, X.ZPixmap, 0xFFFFFFFF)
    arr = np.frombuffer(img.data, dtype=np.uint8).reshape(ch, cw, 4)[:, :, :3]
    return arr.astype(np.int16), caixa


def captura(root, g):
    img = root.get_image(g.x, g.y, g.width, g.height, X.ZPixmap, 0xFFFFFFFF)
    return np.frombuffer(img.data, dtype=np.uint8).reshape(
        g.height, g.width, 4)[:, :, :3].astype(np.int16)


class MicVirtual:
    """Fonte padrao vira o monitor de um null-sink, para o Dito gravar o que tocarmos nele."""

    def __enter__(self):
        self.orig = subprocess.run(['pactl', 'get-default-source'],
                                   capture_output=True, text=True).stdout.strip()
        # Uma execucao anterior morta deixa o proprio dispositivo de teste como padrao: nunca
        # guardar isso como original, senao o microfone do dono nao volta.
        if 'dito_teste' in self.orig:
            saida = subprocess.run(['pactl', 'list', 'short', 'sources'],
                                   capture_output=True, text=True).stdout
            reais = [l.split('\t')[1] for l in saida.splitlines()
                     if '\t' in l and l.split('\t')[1].startswith('alsa_input')]
            self.orig = reais[0] if reais else ''
        self.mod = subprocess.run(
            ['pactl', 'load-module', 'module-null-sink', 'sink_name=dito_teste'],
            capture_output=True, text=True).stdout.strip()
        subprocess.run(['pactl', 'set-default-source', 'dito_teste.monitor'], check=False)
        return self

    def toca(self, wav):
        subprocess.run(['paplay', '--device=dito_teste', wav], check=False)

    def __exit__(self, *_):
        subprocess.run(['pactl', 'set-default-source', self.orig], check=False)
        if self.mod.isdigit():
            subprocess.run(['pactl', 'unload-module', self.mod], check=False)
        print(f'audio restaurado para {self.orig}')


def uma_volta(i, w, root, g, sonda, mic, wav, tecla, total):
    print(f'\n--- volta {i} ---')
    subprocess.run(['xdotool', 'keydown', 'F9'], check=False)
    mic.toca(wav)
    time.sleep(0.4)
    subprocess.run(['xdotool', 'keyup', 'F9'], check=False)

    t0 = time.perf_counter()
    cartao = None
    while time.perf_counter() - t0 < 40:
        b = bbox(w)
        if b[2] > 1 and b[0] >= 500 and b[1] >= 200:
            cartao = time.perf_counter()
            print(f'  cartao em {cartao - t0:5.2f}s ({b[0]}x{b[1]})')
            break
        time.sleep(0.03)
    if not cartao:
        print('  SEM CARTAO (transcricao vazia?)')
        return None

    time.sleep(0.5)
    subprocess.run(['xdotool', 'key', '--clearmodifiers', tecla], check=False)

    # Assentar = regiao vazia por 2,5 s seguidos; o primeiro zero e so o vao entre cartao e toast.
    ultimo_visivel, zerou, pings = None, None, []
    while time.perf_counter() - cartao < 25:
        r = rects(w)
        if r:
            zerou = None
            if len(r) > 1 and (max(x.x + x.width for x in r) - min(x.x for x in r)) < 500:
                ultimo_visivel = recorta(root, g, r)
        else:
            if zerou is None:
                zerou = time.perf_counter()
            elif time.perf_counter() - zerou > 2.5:
                break
        p = sonda.ping(teto=1.0)
        if p is not None:
            pings.append(p)
        time.sleep(0.02)

    if zerou is None:
        print(f'  *** REGIAO NUNCA ESVAZIOU em 25 s apos {tecla} -> PRESO ***')
        return ('preso', 0)
    if ultimo_visivel is None:
        print(f'  assentou {zerou - cartao:5.2f}s apos {tecla}; sem pilula para comparar')
        return ('ok', 0)

    antiga, caixa = ultimo_visivel
    if REMEDIO:
        REMEDIO()
        time.sleep(0.7)
    agora = recorta(root, g, None, caixa)[0]
    iguais = int((np.abs(antiga - agora).sum(axis=2) <= 24).sum())
    pct = iguais / (caixa[2] * caixa[3]) * 100
    marca = 'FANTASMA' if pct > 90 else 'limpo'
    print(f'  assentou {zerou - cartao:5.2f}s apos {tecla}; pilula {pct:5.1f}% igual -> {marca}; '
          f'ping max={max(pings) if pings else 0:.0f} ms')
    return ('fantasma' if pct > 90 else 'ok', pct)


def main():
    p = argparse.ArgumentParser(description='Reproduz um ditado real sem precisar falar.')
    p.add_argument('--voltas', type=int, default=3)
    p.add_argument('--tecla', default='Tab')
    p.add_argument('--wav', default=WAV)
    p.add_argument('--pausa', type=float, default=2.0)
    p.add_argument('--remedio', default='nenhum', choices=list(REMEDIOS))
    a = p.parse_args()

    pid = acha_pid()
    if not pid:
        sys.exit('dito_app nao esta rodando')
    d = display.Display()
    _, sobre = separa(janelas_do(pid, d))
    if not sobre:
        sys.exit('sobreposicao nao encontrada')
    w = d.create_resource_object('window', sobre.id)
    root = d.screen().root
    g = w.get_geometry()
    total = g.width * g.height
    sonda = Sonda(sobre)
    global REMEDIO, XID
    REMEDIO = REMEDIOS[a.remedio]
    XID = hex(sobre.id)
    MOVER[0] = (g.x, g.y, g.width, g.height)
    print(f'remedio={a.remedio}')
    print(f'pid={pid} sobreposicao={hex(sobre.id)} {g.width}x{g.height}+{g.x}+{g.y}')
    print(f'wav={a.wav}  tecla={a.tecla}  voltas={a.voltas}')

    saidas = []
    with MicVirtual() as mic:
        for i in range(1, a.voltas + 1):
            tecla = ('Return' if i % 2 == 0 else 'Tab') if a.tecla == 'alterna' else a.tecla
            saidas.append(uma_volta(i, w, root, g, sonda, mic, a.wav, tecla, total))
            time.sleep(a.pausa)

    fant = sum(1 for s in saidas if s and s[0] == 'fantasma')
    presos = sum(1 for s in saidas if s and s[0] == 'preso')
    sem = sum(1 for s in saidas if s is None)
    print(f'\n===== {a.voltas} voltas: {fant} com FANTASMA, {presos} presas, {sem} sem cartao =====')


if __name__ == '__main__':
    main()
