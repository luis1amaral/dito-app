#!/usr/bin/env python3
"""A janela principal nasce viva? Guarda o stderr, pinga o laco GTK e ve se ela realmente pinta."""
import pathlib
import subprocess
import sys
import time

import numpy as np
from Xlib import X, display

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from medir_abertura import classifica, janelas
from medir_travamento import Sonda

BIN = 'build/linux/x64/release/bundle/dito_app'
ERR = '/tmp/dito_stderr.log'


def foto(root, g):
    img = root.get_image(g.x, g.y, g.width, g.height, X.ZPixmap, 0xFFFFFFFF)
    return np.frombuffer(img.data, dtype=np.uint8).reshape(
        g.height, g.width, 4)[:, :, :3].astype(np.int16)


def main():
    binario = sys.argv[1] if len(sys.argv) > 1 else BIN
    d = display.Display()
    root = d.screen().root
    print(f'lancando {binario} (stderr em {ERR})')
    t0 = time.perf_counter()
    with open(ERR, 'w') as err:
        proc = subprocess.Popen([binario], stdout=err, stderr=subprocess.STDOUT)

    princ = None
    while not princ and time.perf_counter() - t0 < 30:
        princ, _ = classifica(d, janelas(d, proc.pid))
        time.sleep(0.03)
    if not princ:
        proc.terminate(); sys.exit('janela principal nunca apareceu')
    cliente, frame = princ
    g = frame.get_geometry()
    print(f'principal {hex(cliente.id)} {g.width}x{g.height}+{g.x}+{g.y} '
          f'em {time.perf_counter()-t0:.2f}s apos exec')

    sonda = Sonda(cliente)
    fotos = []
    for alvo in (1.5, 3.0, 5.0, 8.0, 12.0, 18.0):
        while time.perf_counter() - t0 < alvo:
            time.sleep(0.05)
        p = sonda.ping(teto=2.0)
        f = foto(root, g)
        cores = len(np.unique(f.reshape(-1, 3), axis=0))
        mudou = '-' if not fotos else int((np.abs(f - fotos[-1][1]).sum(axis=2) > 24).sum())
        fotos.append((alvo, f))
        print(f'  t={alvo:5.1f}s  ping={"sem resposta" if p is None else f"{p:6.1f} ms":>13}  '
              f'cores distintas={cores:6d}  px que mudaram desde a anterior={mudou}')

    print('\n--- stderr do app ---')
    print(open(ERR).read()[-2500:] or '(vazio)')
    print(f'pid={proc.pid} segue rodando')


if __name__ == '__main__':
    main()
