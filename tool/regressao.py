#!/usr/bin/env python3
"""Portao de regressao do Dito no Linux: um comando, um veredito por criterio."""
import argparse
import json
import pathlib
import re
import subprocess
import sys
import time

import numpy as np
from Xlib import X, display
from Xlib.ext import shape

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'tool'))
from medir_abertura import classifica, janelas          # noqa: E402
from medir_travamento import Sonda                       # noqa: E402
from repro_ditado import MicVirtual, rects, recorta      # noqa: E402

BIN = RAIZ / 'build/linux/x64/release/bundle/dito_app'
LOGS = pathlib.Path.home() / '.local/share/dito/logs'
# No repo, nao na biblioteca: desde a 1.6.4 o app nao gera mais WAV para repor esta fala.
WAV = RAIZ / 'tool/fixtures/fala.wav'

LIMITES = {
    'analyze_problemas': 0,
    'testes_falhos': 0,
    'testes_minimo': 211,
    'boot_janelas_s': 1.5,
    'boot_primeiro_ping_s': 2.5,
    'ping_parado_mediana_ms': 3.0,
    'fantasmas': 0,
    'cartoes_perdidos': 0,
    'crash_novos': 0,
    'clique_roubado': 0,
    'aberturas_congeladas': 0,
    'brilho_conteudo': 120,
}


class Portao:
    def __init__(self):
        self.itens = []

    def add(self, nome, ok, detalhe):
        self.itens.append((nome, bool(ok), detalhe))
        print(f'  [{"PASSA" if ok else "FALHA"}] {nome}: {detalhe}')

    def veredito(self):
        maus = [n for n, ok, _ in self.itens if not ok]
        print(f'\n===== {len(self.itens) - len(maus)}/{len(self.itens)} criterios passaram =====')
        if maus:
            print('FALHOU em: ' + ', '.join(maus))
        return 0 if not maus else 1


def roda(cmd, cwd=RAIZ, timeout=900):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def mata_app():
    for p in subprocess.run(['pgrep', '-x', 'dito_app'],
                            capture_output=True, text=True).stdout.split():
        subprocess.run(['kill', p], check=False)
    time.sleep(2)


def estatico(p):
    r = roda(['flutter', 'analyze'])
    problemas = 0 if 'No issues found' in r.stdout else len(
        [l for l in r.stdout.splitlines() if re.match(r'\s+(error|warning|info)', l)])
    p.add('analyze', problemas <= LIMITES['analyze_problemas'], f'{problemas} problemas')

    r = roda(['flutter', 'test'])
    m = re.findall(r'\+(\d+)(?:\s+-(\d+))?', r.stdout)
    verdes = int(m[-1][0]) if m else 0
    falhos = int(m[-1][1]) if m and m[-1][1] else 0
    p.add('testes', falhos == LIMITES['testes_falhos'] and verdes >= LIMITES['testes_minimo'],
          f'{verdes} verdes, {falhos} falhos (minimo {LIMITES["testes_minimo"]})')


def sobe_app(d):
    t0 = time.perf_counter()
    proc = subprocess.Popen([str(BIN)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    princ = sobre = None
    while not sobre and time.perf_counter() - t0 < 30:
        princ, sobre = classifica(d, janelas(d, proc.pid))
        time.sleep(0.03)
    return proc, princ, sobre, time.perf_counter() - t0


def app_real(p):
    d = display.Display()
    root = d.screen().root
    crash = LOGS / 'crash.log'
    antes_crash = crash.read_text(errors='replace').count('erro nao tratado') if crash.exists() else 0

    mata_app()
    proc, princ, sobre, t_janelas = sobe_app(d)
    if not sobre:
        p.add('boot', False, 'sobreposicao nunca apareceu')
        return
    ws = sobre[0]
    p.add('boot: janelas existem', t_janelas <= LIMITES['boot_janelas_s'], f'{t_janelas:.2f}s')

    sonda = Sonda(ws)
    t0 = time.perf_counter()
    primeiro = None
    while primeiro is None and time.perf_counter() - t0 < 20:
        primeiro = sonda.ping(teto=1.0)
    p.add('boot: 1o ping', (t_janelas + time.perf_counter() - t0) <= LIMITES['boot_primeiro_ping_s'],
          f'{t_janelas + time.perf_counter() - t0:.2f}s apos exec')

    # Sobreposicao nao pode roubar clique sobre a janela principal (S0).
    roubou = 0
    # Com o app subindo so na bandeja, o frame da principal pode nem existir ainda.
    try:
        g = princ[1].get_geometry() if princ else None
    except Exception:
        g = None
    if princ and g:
        cx, cy = g.x + g.width // 2, g.y + g.height // 2
        orig = root.query_pointer()
        for _ in range(20):
            root.warp_pointer(cx, cy); d.sync(); time.sleep(0.02)
            q = root.query_pointer()
            if q.child and q.child.id in (ws.id, sobre[1].id):
                roubou += 1
            time.sleep(0.05)
        root.warp_pointer(orig.root_x, orig.root_y); d.sync()
        p.add('sobreposicao nao rouba clique', roubou <= LIMITES['clique_roubado'],
              f'{roubou}/20 amostras roubadas')
    else:
        p.add('sobreposicao nao rouba clique', True,
              'janela principal escondida na bandeja; nada a roubar')

    # ANTES de qualquer F9: a tecla destrava a janela e mascararia o defeito (armadilha 5.3).
    p.add(*abre_com_conteudo(d, root, princ, pid=proc.pid))

    vals = []
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 8:
        v = sonda.ping()
        if v is not None:
            vals.append(v)
        time.sleep(0.02)
    med = sorted(vals)[len(vals) // 2] if vals else 999
    p.add('fluidez parado', med <= LIMITES['ping_parado_mediana_ms'], f'mediana {med:.1f} ms')

    # Ciclo real de ditado: cartao, fantasma, foco.
    fantasmas = perdidos = 0
    focos = []
    if not WAV.exists():
        p.add('ciclo de ditado', False, f'WAV de teste ausente: {WAV}')
    else:
        with MicVirtual() as mic:
            for i in range(6):
                tecla = 'Return' if i % 2 else 'Tab'
                r = uma_volta(d, root, ws, sonda, mic, tecla)
                if r is None:
                    perdidos += 1
                else:
                    fant, foco = r
                    fantasmas += 1 if fant else 0
                    focos.append(foco)
                time.sleep(1.5)
        p.add('cartao aparece', perdidos <= LIMITES['cartoes_perdidos'],
              f'{perdidos}/6 sem cartao')
        p.add('sem pixel fantasma', fantasmas <= LIMITES['fantasmas'],
              f'{fantasmas}/{6 - perdidos} com fantasma')
        p.add('foco no cartao (armadilha 4.6)', all(focos) and focos,
              f'{sum(focos)}/{len(focos)} cartoes com input focus True')

    depois_crash = crash.read_text(errors='replace').count('erro nao tratado') if crash.exists() else 0
    p.add('sem excecao nova', depois_crash - antes_crash <= LIMITES['crash_novos'],
          f'{depois_crash - antes_crash} novas')
    proc.terminate()


def esconde(d, cliente):
    """Fecha pela via do WM: o app intercepta e manda para a bandeja em vez de sair."""
    import Xlib.protocol.event as xev
    protocolos = d.intern_atom('WM_PROTOCOLS')
    fechar = d.intern_atom('WM_DELETE_WINDOW')
    cliente.send_event(xev.ClientMessage(window=cliente, client_type=protocolos,
                                         data=(32, [fechar, X.CurrentTime, 0, 0, 0])),
                       event_mask=X.NoEventMask)
    d.flush()


def abre_com_conteudo(d, root, princ, voltas=5, pid=None):
    """Abrir pela bandeja tem de mostrar o conteudo, nao a tela de boot congelada."""
    congeladas = []
    for i in range(voltas):
        subprocess.run(['gdbus', 'call', '--session', '--dest', 'com.defalt.dito_app',
                        '--object-path', '/org/ayatana/NotificationItem/dito/Menu',
                        '--method', 'com.canonical.dbusmenu.Event', '--',
                        '15', 'clicked', "<''>", '0'], capture_output=True)
        time.sleep(2.5)
        # A principal so existe depois de a bandeja abri-la: procurar agora, nao antes.
        if pid is not None:
            princ, _ = classifica(d, janelas(d, pid))
        if not princ:
            congeladas.append(f'volta {i + 1}: janela nao apareceu')
            continue
        try:
            gc = princ[0].get_geometry()
            ab = princ[0].translate_coords(root, 0, 0)
            img = root.get_image(-ab.x, -ab.y, gc.width, gc.height, X.ZPixmap, 0xFFFFFFFF)
            arr = np.frombuffer(img.data, dtype=np.uint8).reshape(gc.height, gc.width, 4)[:, :, :3]
        except Exception as e:
            congeladas.append(f'volta {i + 1}: {e}')
            continue
        if arr.mean() >= LIMITES['brilho_conteudo']:
            congeladas.append(f'volta {i + 1}: brilho {arr.mean():.0f}')
        esconde(d, princ[0])
        time.sleep(1.5)
    return ('abre com conteudo, nao a tela de boot',
            len(congeladas) <= LIMITES['aberturas_congeladas'],
            f'{len(congeladas)}/{voltas} congeladas' + (f' ({congeladas[0]})' if congeladas else ''))


def uma_volta(d, root, ws, sonda, mic, tecla):
    subprocess.run(['xdotool', 'keydown', 'F9'], check=False)
    mic.toca(str(WAV))
    time.sleep(0.4)
    subprocess.run(['xdotool', 'keyup', 'F9'], check=False)

    g = ws.get_geometry()
    t0 = time.perf_counter()
    achou = False
    while time.perf_counter() - t0 < 40:
        r = rects(ws)
        if r and len(r) > 1:
            larg = max(x.x + x.width for x in r) - min(x.x for x in r)
            alt = max(x.y + x.height for x in r) - min(x.y for x in r)
            if larg >= 500 and alt >= 200:
                achou = True
                break
        time.sleep(0.03)
    if not achou:
        return None

    time.sleep(0.4)
    hints = subprocess.run(['xprop', '-id', hex(ws.id), 'WM_HINTS'],
                           capture_output=True, text=True).stdout
    foco = 'input focus: True' in hints or 'input or input focus: True' in hints
    subprocess.run(['xdotool', 'key', '--clearmodifiers', tecla], check=False)

    ultimo, zerou = None, None
    t1 = time.perf_counter()
    while time.perf_counter() - t1 < 25:
        r = rects(ws)
        if r:
            zerou = None
            if len(r) > 1 and (max(x.x + x.width for x in r) - min(x.x for x in r)) < 500:
                ultimo = recorta(root, g, r)
        else:
            if zerou is None:
                zerou = time.perf_counter()
            elif time.perf_counter() - zerou > 2.5:
                break
        time.sleep(0.03)
    if ultimo is None or zerou is None:
        return (False, foco)
    antiga, caixa = ultimo
    agora = recorta(root, g, None, caixa)[0]
    iguais = int((np.abs(antiga - agora).sum(axis=2) <= 24).sum())
    return (iguais / (caixa[2] * caixa[3]) > 0.9, foco)


def main():
    ap = argparse.ArgumentParser(description='Portao de regressao do Dito (Linux).')
    ap.add_argument('--so-estatico', action='store_true')
    ap.add_argument('--so-app', action='store_true')
    a = ap.parse_args()
    p = Portao()
    print(f'=== portao de regressao — {time.strftime("%H:%M:%S")} ===')
    if not a.so_app:
        estatico(p)
    if not a.so_estatico:
        if not BIN.exists():
            p.add('build', False, f'{BIN} nao existe; rode flutter build linux --release')
        else:
            app_real(p)
    codigo = p.veredito()
    mata_app()
    sys.exit(codigo)


if __name__ == '__main__':
    main()
