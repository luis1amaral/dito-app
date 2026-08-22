#!/usr/bin/env python3
"""Fica de tocaia: acusa quando a regiao de clique zera mas os pixels da pilula continuam na tela."""
import pathlib
import subprocess
import sys
import time

import numpy as np
from PIL import Image
from Xlib import X, display
from Xlib.ext import shape

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from medir_travamento import acha_pid, janelas_do, separa

SAIDA = pathlib.Path('/tmp/dito_fantasma')
LIMIAR = 24
SEGURA_S = 2.5


def main():
    pid = acha_pid()
    if not pid:
        sys.exit('dito_app nao esta rodando')
    d = display.Display()
    _, sobre = separa(janelas_do(pid, d))
    w = d.create_resource_object('window', sobre.id)
    root = d.screen().root
    g = w.get_geometry()
    SAIDA.mkdir(exist_ok=True)
    print(f'tocaia em {hex(sobre.id)} {g.width}x{g.height}+{g.x}+{g.y}; Ctrl+C para sair')

    def rects():
        try:
            return w.shape_get_rectangles(shape.SK.Input).rectangles
        except Exception:
            return []

    def foto(r):
        x0 = min(x.x for x in r); y0 = min(x.y for x in r)
        x1 = max(x.x + x.width for x in r); y1 = max(x.y + x.height for x in r)
        img = root.get_image(g.x + x0, g.y + y0, x1 - x0, y1 - y0, X.ZPixmap, 0xFFFFFFFF)
        arr = np.frombuffer(img.data, dtype=np.uint8).reshape(y1 - y0, x1 - x0, 4)[:, :, :3]
        return arr.astype(np.int16), (x0, y0, x1 - x0, y1 - y0)

    ultimo_visivel = None
    zerou_em = None
    acusado = False
    n = 0
    while True:
        r = rects()
        if r:
            # Guarda so a pilula (pequena); um cartao aberto nao interessa para o toast preso.
            if len(r) > 1 and (max(x.x + x.width for x in r) - min(x.x for x in r)) < 500:
                ultimo_visivel = foto(r)
            zerou_em, acusado = None, False
        elif ultimo_visivel is not None:
            if zerou_em is None:
                zerou_em = time.perf_counter()
            elif not acusado and time.perf_counter() - zerou_em > SEGURA_S:
                acusado = True
                antiga, (x0, y0, cw, ch) = ultimo_visivel
                img = root.get_image(g.x + x0, g.y + y0, cw, ch, X.ZPixmap, 0xFFFFFFFF)
                agora = np.frombuffer(img.data, dtype=np.uint8).reshape(
                    ch, cw, 4)[:, :, :3].astype(np.int16)
                iguais = int((np.abs(antiga - agora).sum(axis=2) <= LIMIAR).sum())
                total = cw * ch
                marca = time.strftime('%H:%M:%S')
                pct = iguais / total * 100
                try:
                    nb = len(w.shape_get_rectangles(shape.SK.Bounding).rectangles)
                except Exception:
                    nb = -1
                op = subprocess.run(['xprop', '-id', hex(sobre.id), '_NET_WM_WINDOW_OPACITY'],
                                    capture_output=True, text=True).stdout.strip()
                if pct > 90:
                    n += 1
                    print(f'          Bounding={nb} rects | {op}')
                    Image.fromarray(antiga.astype(np.uint8)[:, :, ::-1]).save(
                        SAIDA / f'{n}_quando_visivel.png')
                    Image.fromarray(agora.astype(np.uint8)[:, :, ::-1]).save(
                        SAIDA / f'{n}_depois_de_esconder.png')
                    print(f'[{marca}] *** FANTASMA #{n}: regiao vazia ha {SEGURA_S}s e '
                          f'{pct:.0f}% dos pixels da pilula continuam iguais -> {SAIDA}')
                else:
                    print(f'[{marca}] ok: area limpou ({pct:.0f}% igual ao que estava)')
        time.sleep(0.15)


if __name__ == '__main__':
    main()
