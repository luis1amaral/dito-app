#!/usr/bin/env python3
"""N lancamentos: a janela principal nasce viva? Sonda = redimensionar e ver se o Flutter repinta."""
import pathlib
import subprocess
import sys
import time

import numpy as np
from Xlib import X, display

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from medir_abertura import classifica, janelas

BIN = 'build/linux/x64/release/bundle/dito_app'


def foto(root, g):
    img = root.get_image(g.x, g.y, g.width, g.height, X.ZPixmap, 0xFFFFFFFF)
    return np.frombuffer(img.data, dtype=np.uint8).reshape(
        g.height, g.width, 4)[:, :, :3].astype(np.int16)


def uma_volta(i, binario, d, root):
    err = f'/tmp/dito_stderr_{i}.log'
    t0 = time.perf_counter()
    with open(err, 'w') as f:
        proc = subprocess.Popen([binario], stdout=f, stderr=subprocess.STDOUT)

    princ = None
    while not princ and time.perf_counter() - t0 < 30:
        princ, _ = classifica(d, janelas(d, proc.pid))
        time.sleep(0.03)
    if not princ:
        proc.terminate()
        return {'volta': i, 'erro': 'sem janela principal'}
    cliente, frame = princ
    time.sleep(4.0)  # deixa o windowManager centralizar e o Dart desenhar

    g = frame.get_geometry()
    antes = foto(root, g)
    # Redimensionar forca o Flutter a relayout+repaint: janela morta nao muda um pixel.
    subprocess.run(['xdotool', 'windowsize', hex(cliente.id),
                    str(g.width - 40), str(g.height - 40)], check=False)
    time.sleep(1.2)
    g2 = frame.get_geometry()
    depois = foto(root, g2)
    lado = (min(antes.shape[0], depois.shape[0]), min(antes.shape[1], depois.shape[1]))
    mudou = int((np.abs(antes[:lado[0], :lado[1]] - depois[:lado[0], :lado[1]]).sum(axis=2) > 24).sum())
    cores = len(np.unique(depois.reshape(-1, 3), axis=0))

    saida = open(err).read()
    shaders = saida.count('Failed to setup compositor shaders')
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    time.sleep(1.5)
    redimensionou = (g2.width, g2.height) != (g.width, g.height)
    return {'volta': i, 'antes': f'{g.width}x{g.height}+{g.x}+{g.y}',
            'depois': f'{g2.width}x{g2.height}+{g2.x}+{g2.y}',
            'redimensionou': redimensionou, 'mudou': mudou,
            'cores': cores, 'shaders': shaders,
            'viva': ('VIVA' if mudou > 2000 else 'MORTA') if redimensionou else 'SONDA FALHOU'}


def main():
    binario = sys.argv[1] if len(sys.argv) > 1 else BIN
    voltas = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    d = display.Display()
    root = d.screen().root
    print(f'{voltas} lancamentos de {binario}\n')
    res = []
    for i in range(1, voltas + 1):
        r = uma_volta(i, binario, d, root)
        res.append(r)
        print(f'  volta {i}: {r}')
    mortas = sum(1 for r in res if r.get('viva') == 'MORTA')
    erros = sum(r.get('shaders', 0) for r in res)
    print(f'\nVEREDITO: {mortas}/{voltas} janelas principais nasceram MORTAS; '
          f'{erros} erros de compositor no total')


if __name__ == '__main__':
    main()
