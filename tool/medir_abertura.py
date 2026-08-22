#!/usr/bin/env python3
"""Prova ou derruba o S0: o que acontece na abertura, e quem recebe o clique sobre a janela."""
import pathlib
import subprocess
import sys
import time

from Xlib import X, display
from Xlib.ext import shape

sys.path.insert(0, str(pathlib.Path(__file__).parent))

BIN = 'build/linux/x64/release/bundle/dito_app'


def janelas(d, pid):
    """Anda tambem dentro dos frames: o WM reparenteia, e o cliente deixa de ser filho da raiz."""
    root = d.screen().root
    atom = d.intern_atom('_NET_WM_PID')
    achadas = []
    for f in root.query_tree().children:
        try:
            # Janelas somem entre enumerar e perguntar: BadWindow aqui e normal, nao erro.
            alvos = [f] + list(f.query_tree().children)
        except Exception:
            continue
        for w in alvos:
            try:
                p = w.get_full_property(atom, X.AnyPropertyType)
                if p and p.value[0] == pid:
                    achadas.append((w, f))
            except Exception:
                pass
    return achadas


def classifica(d, achadas):
    estado = d.intern_atom('_NET_WM_STATE')
    acima = d.intern_atom('_NET_WM_STATE_ABOVE')
    sobre = princ = None
    for w, frame in achadas:
        try:
            p = w.get_full_property(estado, X.AnyPropertyType)
            no_topo = bool(p and acima in list(p.value))
        except Exception:
            no_topo = False
        g = w.get_geometry()
        if no_topo:
            sobre = (w, frame)
        elif g.width > 100 and g.height > 100:
            princ = (w, frame)
    return princ, sobre


def formas(w):
    saida = {}
    for nome, k in (('bound', shape.SK.Bounding), ('input', shape.SK.Input)):
        try:
            r = w.shape_get_rectangles(k).rectangles
        except Exception:
            saida[nome] = 'erro'
            continue
        if not r:
            saida[nome] = '0r VAZIA'
        else:
            x0 = min(x.x for x in r); y0 = min(x.y for x in r)
            x1 = max(x.x + x.width for x in r); y1 = max(x.y + x.height for x in r)
            saida[nome] = f'{len(r)}r {x1-x0}x{y1-y0}+{x0}+{y0}'
    return saida


def main():
    binario = sys.argv[1] if len(sys.argv) > 1 else BIN
    segundos = float(sys.argv[2]) if len(sys.argv) > 2 else 25.0
    d = display.Display()
    root = d.screen().root

    print(f'lancando {binario}')
    t0 = time.perf_counter()
    proc = subprocess.Popen([binario], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    princ = sobre = None
    while not (princ and sobre) and time.perf_counter() - t0 < 30:
        princ, sobre = classifica(d, janelas(d, proc.pid))
        time.sleep(0.05)
    if not sobre:
        proc.terminate(); sys.exit('sobreposicao nao apareceu')
    ws, fs = sobre
    gp = princ[0].get_geometry() if princ else None
    print(f'sobreposicao cliente={hex(ws.id)} frame={hex(fs.id)} '
          f'{ws.get_geometry().width}x{ws.get_geometry().height}'
          f'+{fs.get_geometry().x}+{fs.get_geometry().y}')
    if princ:
        print(f'principal    cliente={hex(princ[0].id)} frame={hex(princ[1].id)} '
              f'{gp.width}x{gp.height}+{princ[1].get_geometry().x}+{princ[1].get_geometry().y}')
    else:
        print('principal    NAO ENCONTRADA')
    ids = {ws.id: 'SOBREPOSICAO', fs.id: 'SOBREPOSICAO(frame)'}
    if princ:
        ids[princ[0].id] = 'principal'
        ids[princ[1].id] = 'principal(frame)'

    # Ponto testado: o centro da janela principal, que e onde o dono clica.
    if princ:
        g = princ[1].get_geometry()
        cx, cy = g.x + g.width // 2, g.y + g.height // 2
    else:
        cx, cy = d.screen().width_in_pixels // 4, d.screen().height_in_pixels // 2
    print(f'ponto testado: ({cx},{cy})\n')

    original = root.query_pointer()
    ultimo, comeu, total = None, 0, 0
    while time.perf_counter() - t0 < segundos:
        f = formas(ws)
        root.warp_pointer(cx, cy)
        d.sync()
        time.sleep(0.02)
        q = root.query_pointer()
        alvo = q.child.id if q.child else 0
        quem = ids.get(alvo, hex(alvo) if alvo else 'raiz')
        total += 1
        if alvo in (ws.id, fs.id):
            comeu += 1
        linha = (f['bound'], f['input'], quem)
        if linha != ultimo:
            print(f"{time.perf_counter()-t0:6.2f}  bound={f['bound']:<22} "
                  f"input={f['input']:<22} clique -> {quem}")
            ultimo = linha
        time.sleep(0.1)
    root.warp_pointer(original.root_x, original.root_y)
    d.sync()

    print(f'\nVEREDITO: {comeu}/{total} amostras com o clique indo para a SOBREPOSICAO '
          f'({comeu/total*100:.0f}%)')
    print(f'pid={proc.pid} segue rodando')


if __name__ == '__main__':
    main()
