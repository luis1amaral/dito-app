#!/usr/bin/env python3
"""Vigia a sobreposicao: separa "o app nao escondeu" de "o compositor nao repintou"."""
import pathlib
import subprocess
import sys
import time

import numpy as np
from Xlib import X, display
from Xlib.ext import shape

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from medir_travamento import acha_pid, janelas_do, separa

LIMIAR_PX = 24


def captura(root, g):
    img = root.get_image(g.x, g.y, g.width, g.height, X.ZPixmap, 0xFFFFFFFF)
    return np.frombuffer(img.data, dtype=np.uint8).reshape(g.height, g.width, 4)[:, :, :3]


def main():
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
    print(f'vigiando {hex(sobre.id)} {g.width}x{g.height}+{g.x}+{g.y}')
    print('grave algo e de Tab para descartar; Ctrl+C para sair\n')

    anterior = None
    while True:
        try:
            n = len(w.shape_get_rectangles(shape.SK.Input).rectangles)
        except Exception:
            time.sleep(0.05)
            continue
        if anterior is not None and (n > 0) != (anterior > 0):
            marca = time.strftime('%H:%M:%S')
            print(f'[{marca}] regiao de clique: {anterior} -> {n} rects')
            if n == 0:
                time.sleep(0.4)
                antes = captura(root, g).astype(np.int16)
                subprocess.run(['xrefresh'], check=False)
                time.sleep(0.4)
                depois = captura(root, g).astype(np.int16)
                dif = int((np.abs(antes - depois).sum(axis=2) > LIMIAR_PX).sum())
                total = g.width * g.height
                # Se um xrefresh muda a tela, o que estava la eram pixels que ninguem repintou.
                veredito = ('PIXELS VELHOS: app escondeu, compositor nao repintou'
                            if dif > total * 0.005 else 'tela limpa: nada sobrou')
                print(f'          {dif} px mudaram com xrefresh '
                      f'({dif / total * 100:.2f}%) -> {veredito}')
        anterior = n
        time.sleep(0.05)


if __name__ == '__main__':
    main()
