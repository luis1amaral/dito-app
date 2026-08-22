#!/usr/bin/env python3
"""Despeja o estado inteiro do Dito no instante em que o dono diz que travou."""
import pathlib
import subprocess
import sys
import time

import numpy as np
from PIL import Image
from Xlib import X, display
from Xlib.ext import shape

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from medir_abertura import classifica, janelas
from medir_travamento import Sonda

SAIDA = pathlib.Path('/tmp/dito_flagra')


def formas(w):
    fora = {}
    for nome, k in (('bound', shape.SK.Bounding), ('input', shape.SK.Input)):
        try:
            r = w.shape_get_rectangles(k).rectangles
        except Exception:
            fora[nome] = 'erro'
            continue
        if not r:
            fora[nome] = '0r VAZIA'
        else:
            x0 = min(x.x for x in r); y0 = min(x.y for x in r)
            x1 = max(x.x + x.width for x in r); y1 = max(x.y + x.height for x in r)
            fora[nome] = f'{len(r)}r {x1-x0}x{y1-y0}+{x0}+{y0}'
    return fora


def main():
    SAIDA.mkdir(exist_ok=True)
    pid = subprocess.run(['pgrep', '-x', 'dito_app'], capture_output=True, text=True).stdout.split()
    if not pid:
        sys.exit('dito_app nao esta rodando')
    pid = int(pid[0])
    d = display.Display()
    root = d.screen().root
    princ, sobre = classifica(d, janelas(d, pid))
    print(f'=== FLAGRA {time.strftime("%H:%M:%S")}  pid={pid} ===')

    for nome, par in (('principal', princ), ('sobreposicao', sobre)):
        if not par:
            print(f'{nome}: NAO ENCONTRADA')
            continue
        w, frame = par
        g = frame.get_geometry()
        a = w.get_attributes()
        f = formas(w)
        try:
            p = Sonda(w).ping(teto=3.0)
            resp = 'SEM RESPOSTA (>3s)' if p is None else f'{p:.1f} ms'
        except Exception as e:
            resp = f'erro: {e}'
        print(f'{nome}: {hex(w.id)} {g.width}x{g.height}+{g.x}+{g.y} '
              f'{"viewable" if a.map_state == X.IsViewable else "UNMAPPED"} '
              f'| ping={resp} | bound={f["bound"]} input={f["input"]}')
        img = root.get_image(g.x, g.y, g.width, g.height, X.ZPixmap, 0xFFFFFFFF)
        arr = np.frombuffer(img.data, dtype=np.uint8).reshape(g.height, g.width, 4)[:, :, :3]
        Image.fromarray(arr[:, :, ::-1]).save(SAIDA / f'{nome}.png')

    ativa = subprocess.run(['xdotool', 'getactivewindow'], capture_output=True, text=True).stdout.strip()
    print(f'janela ativa: {hex(int(ativa)) if ativa else "-"}')
    q = root.query_pointer()
    print(f'ponteiro em ({q.root_x},{q.root_y}) -> {hex(q.child.id) if q.child else "raiz"}')
    with open(f'/proc/{pid}/task/{pid}/syscall') as fh:
        print(f'thread de plataforma: syscall={fh.read().split()[0]}')
    for nome in ('app', 'controller', 'hud_window', 'crash'):
        p = pathlib.Path.home() / '.local/share/dito/logs' / f'{nome}.log'
        if p.exists():
            linhas = p.read_text(errors='replace').splitlines()[-4:]
            print(f'--- {nome}.log ---')
            for l in linhas:
                print('   ', l[:150])
    print(f'\nimagens em {SAIDA}')


if __name__ == '__main__':
    main()
