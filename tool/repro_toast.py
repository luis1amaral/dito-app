#!/usr/bin/env python3
"""Reproduz o toast 'descartado' preso: injeta cartao via DITO_HUD_HOLD, da Tab e vigia a saida."""
import os
import pathlib
import subprocess
import sys
import time

import numpy as np
from Xlib import X, display
from Xlib.ext import shape

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from medir_travamento import janelas_do, separa

BIN = 'build/linux/x64/release/bundle/dito_app'


def bbox(w):
    try:
        r = w.shape_get_rectangles(shape.SK.Input).rectangles
    except Exception:
        return None
    if not r:
        return (0, 0, 0, 0, 0)
    x0 = min(x.x for x in r); y0 = min(x.y for x in r)
    x1 = max(x.x + x.width for x in r); y1 = max(x.y + x.height for x in r)
    return (x1 - x0, y1 - y0, x0, y0, len(r))


def captura(root, g):
    img = root.get_image(g.x, g.y, g.width, g.height, X.ZPixmap, 0xFFFFFFFF)
    return np.frombuffer(img.data, dtype=np.uint8).reshape(g.height, g.width, 4)[:, :, :3]


def main():
    binario = sys.argv[1] if len(sys.argv) > 1 else BIN
    env = dict(os.environ, DITO_HUD_HOLD='1', DITO_HUD_CARD_MS='20000')
    print(f'lancando {binario} com DITO_HUD_HOLD=1')
    proc = subprocess.Popen([binario], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    d = display.Display()
    sobre = None
    t0 = time.perf_counter()
    while not sobre and time.perf_counter() - t0 < 40:
        _, sobre = separa(janelas_do(proc.pid, d))
        time.sleep(0.05)
    if not sobre:
        proc.terminate(); sys.exit('sobreposicao nao apareceu')
    w = d.create_resource_object('window', sobre.id)
    root = d.screen().root
    g = w.get_geometry()
    print(f'sobreposicao {hex(sobre.id)} {g.width}x{g.height}+{g.x}+{g.y}')

    # Referencia no primeiro segundo: o arnes so comeca a desenhar em t=2s.
    limite = time.perf_counter() + 1.2
    while bbox(w)[4] != 0 and time.perf_counter() < limite:
        time.sleep(0.05)
    ref = captura(root, g).astype(np.int16)
    time.sleep(0.4)
    ref2 = captura(root, g).astype(np.int16)
    ruido = int((np.abs(ref - ref2).sum(axis=2) > 24).sum())
    print(f'referencia capturada com {bbox(w)[4]} rects; ruido de fundo: {ruido} px')

    print('esperando o cartao (altura > 200 px)...')
    cartao_em = None
    while time.perf_counter() - t0 < 90:
        b = bbox(w)
        # 1 retangulo e o fallback "sem medida ainda" (janela inteira); o cartao tem a largura dele.
        if b and b[4] > 1 and b[0] >= 500 and b[1] >= 200:
            time.sleep(0.6)
            ativa = subprocess.run(['xdotool', 'getactivewindow'],
                                   capture_output=True, text=True).stdout.strip()
            cartao_em = time.perf_counter()
            print(f'[{cartao_em - t0:6.2f}s] CARTAO no ar: {b[0]}x{b[1]} ({b[4]} rects); '
                  f'janela ativa={hex(int(ativa)) if ativa else "?"} '
                  f'(sobreposicao={hex(sobre.id)}) -> Tab')
            subprocess.run(['xdotool', 'key', '--clearmodifiers', 'Tab'], check=False)
            break
        time.sleep(0.03)
    if not cartao_em:
        proc.terminate(); sys.exit('o cartao nunca apareceu')

    print('vigiando a saida do toast por 15 s...')
    vazio_em = None
    ultimo = None
    while time.perf_counter() - cartao_em < 15:
        b = bbox(w)
        if b and b[:2] != (ultimo[:2] if ultimo else None):
            print(f'  [{time.perf_counter() - cartao_em:6.2f}s] regiao {b[0]}x{b[1]} ({b[4]} rects)')
            ultimo = b
            if b[4] == 0 and vazio_em is None:
                vazio_em = time.perf_counter()
        time.sleep(0.05)

    if vazio_em:
        print(f'\nRESULTADO: regiao esvaziou {vazio_em - cartao_em:.2f}s apos o Tab')
        xid = hex(sobre.id)
        total = g.width * g.height
        remedios = [
            ('sem remedio (estado apos esconder)', lambda: None),
            ('opacidade 0 (_NET_WM_WINDOW_OPACITY)',
             lambda: subprocess.run(['xprop', '-id', xid, '-f', '_NET_WM_WINDOW_OPACITY', '32c',
                                     '-set', '_NET_WM_WINDOW_OPACITY', '0'], check=False)),
            ('mover 1 px e voltar', lambda: (
                subprocess.run(['xdotool', 'windowmove', xid, str(g.x + 1), str(g.y)], check=False),
                time.sleep(0.15),
                subprocess.run(['xdotool', 'windowmove', xid, str(g.x), str(g.y)], check=False))),
        ]
        escolhido = os.environ.get('REMEDIO', 'nenhum')
        acao = dict((n.split(' ')[0], a) for n, a in remedios).get(escolhido.split(' ')[0])
        nome = next((n for n, _ in remedios if n.startswith(escolhido.split(' ')[0])), 'nenhum')
        print(f'\nremedio em teste: {nome}')
        if acao:
            acao()
        time.sleep(0.8)
        depois = captura(root, g).astype(np.int16)
        # xrefresh e o "como fica sem fantasma": comparar contra ele, 0,8 s depois, evita drift.
        subprocess.run(['xrefresh'], check=False)
        time.sleep(0.8)
        limpo = captura(root, g).astype(np.int16)
        mask = np.abs(depois - limpo).sum(axis=2) > 24
        n = int(mask.sum())
        caixa = '-'
        if n:
            ys, xs = np.nonzero(mask)
            caixa = f'({xs.min()},{ys.min()})-({xs.max()},{ys.max()})'
        print(f'FANTASMA restante: {n} px ({n / total * 100:.2f}%) bbox={caixa}  '
              + ('-> LIMPOU' if n < total * 0.001 else '-> AINDA SUJO'))
        subprocess.run(['xprop', '-id', xid, '-remove', '_NET_WM_WINDOW_OPACITY'], check=False)
    else:
        print(f'\nRESULTADO: a regiao NUNCA esvaziou em 15 s -> toast preso reproduzido')
        print(f'  ultimo estado: {ultimo}')
    print(f'\npid={proc.pid} segue rodando')


if __name__ == '__main__':
    main()
