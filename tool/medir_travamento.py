#!/usr/bin/env python3
"""Mede o travamento da interface do Dito no Linux/X11, de fora do app."""
import argparse
import csv
import os
import subprocess
import sys
import threading
import time

from Xlib import X, Xatom, display
from Xlib.ext import shape
import Xlib.protocol.event as xev

# ppoll/poll sao o repouso do laco GTK; qualquer outra syscall na thread principal e trabalho.
SYSCALL_REPOUSO = {7, 271, 232}
NOME_SYSCALL = {0: 'read', 1: 'write', 7: 'poll', 16: 'ioctl', 17: 'pread', 18: 'pwrite',
                23: 'select', 46: 'sendmsg', 47: 'recvmsg', 61: 'wait4', 202: 'futex',
                230: 'clock_nanosleep', 232: 'epoll_wait', 271: 'ppoll', 281: 'epoll_pwait'}


def acha_pid():
    saida = subprocess.run(['pgrep', '-f', 'dito_app'], capture_output=True, text=True).stdout
    for linha in saida.split():
        if os.path.exists(f'/proc/{linha}/exe'):
            try:
                if 'dito_app' in os.readlink(f'/proc/{linha}/exe'):
                    return int(linha)
            except OSError:
                pass
    return None


def janelas_do(pid, d):
    """Acha as janelas de topo do processo; xdotool search --pid nao funciona nesta pilha."""
    root = d.screen().root
    atom = d.intern_atom('_NET_WM_PID')
    achadas = []
    for w in root.query_tree().children:
        try:
            p = w.get_full_property(atom, X.AnyPropertyType)
            if p and p.value[0] == pid:
                achadas.append((w, w.get_geometry()))
        except Exception:
            pass
    return achadas


def separa(achadas, d=None):
    """A sobreposicao e a unica com _NET_WM_STATE_ABOVE; tamanho nao serve (a principal varia)."""
    d = d or display.Display()
    estado = d.intern_atom('_NET_WM_STATE')
    acima = d.intern_atom('_NET_WM_STATE_ABOVE')
    sobre = principal = None
    for w, g in achadas:
        try:
            p = w.get_full_property(estado, X.AnyPropertyType)
            no_topo = bool(p and acima in list(p.value))
        except Exception:
            no_topo = False
        if no_topo:
            sobre = w
        elif g.width > 1 and g.height > 1:
            principal = w
    return principal, sobre


class Sonda:
    """Round-trip de _NET_WM_PING: mede em ms se o laco GTK do app ainda atende."""

    def __init__(self, win):
        self.d = display.Display()
        self.win = self.d.create_resource_object('window', win.id)
        A = self.d.intern_atom
        self.protocols, self.ping_atom = A('WM_PROTOCOLS'), A('_NET_WM_PING')
        self.d.screen().root.change_attributes(event_mask=X.SubstructureNotifyMask)
        self.d.sync()

    def ping(self, teto=5.0):
        t0 = time.perf_counter()
        marca = int(t0 * 1000000) & 0xFFFFFFFF
        self.win.send_event(xev.ClientMessage(
            window=self.win, client_type=self.protocols,
            data=(32, [self.ping_atom, marca, self.win.id, 0, 0])), event_mask=0)
        self.d.flush()
        while time.perf_counter() - t0 < teto:
            while self.d.pending_events():
                e = self.d.next_event()
                if (e.type == X.ClientMessage and e.client_type == self.protocols
                        and e.data[1][0] == self.ping_atom and e.data[1][1] == marca):
                    return (time.perf_counter() - t0) * 1000
            time.sleep(0.001)
        return None


class Amostrador(threading.Thread):
    """Regiao de clique, foco do X e syscall da thread de plataforma, num relogio so."""

    def __init__(self, pid, principal, sobre, hz=20):
        super().__init__(daemon=True)
        self.pid, self.hz = pid, hz
        self.d = display.Display()
        self.sobre = self.d.create_resource_object('window', sobre.id) if sobre else None
        self.principal = self.d.create_resource_object('window', principal.id) if principal else None
        self.ativa_atom = self.d.intern_atom('_NET_ACTIVE_WINDOW')
        self.root = self.d.screen().root
        self.linhas = []
        self.parar = threading.Event()

    def _syscall(self):
        try:
            with open(f'/proc/{self.pid}/task/{self.pid}/syscall') as f:
                bruto = f.read().split()
            # "running" e o caso mais interessante: thread queimando CPU, nao dormindo em syscall.
            return int(bruto[0]) if bruto and bruto[0] != 'running' else -1
        except OSError:
            return -2

    def _rects(self, win, kind):
        try:
            return len(win.shape_get_rectangles(kind).rectangles)
        except Exception:
            return -1

    def _ativa(self):
        try:
            p = self.root.get_full_property(self.ativa_atom, Xatom.WINDOW)
            return p.value[0] if p else 0
        except Exception:
            return 0

    def run(self):
        passo = 1.0 / self.hz
        while not self.parar.is_set():
            t = time.perf_counter()
            self.linhas.append({
                't': t,
                'input_rects': self._rects(self.sobre, shape.SK.Input) if self.sobre else -1,
                'bound_rects': self._rects(self.sobre, shape.SK.Bounding) if self.sobre else -1,
                'ativa': self._ativa(),
                'syscall': self._syscall(),
            })
            time.sleep(max(0, passo - (time.perf_counter() - t)))


def intervalos(linhas, chave, condicao):
    """Junta amostras vizinhas que satisfazem a condicao num intervalo com duracao."""
    saida, ini = [], None
    for l in linhas:
        if condicao(l[chave]):
            if ini is None:
                ini = l['t']
            fim = l['t']
        elif ini is not None:
            saida.append((ini, fim - ini))
            ini = None
    if ini is not None:
        saida.append((ini, linhas[-1]['t'] - ini))
    return saida


def resumo(pings, linhas, t0, rotulo):
    print(f'\n===== {rotulo} =====')
    ok = [p for _, p in pings if p is not None]
    perdidos = sum(1 for _, p in pings if p is None)
    if ok:
        ok_ord = sorted(ok)
        print(f'laco GTK  : {len(ok)} pings, min={ok_ord[0]:.1f} '
              f'mediana={ok_ord[len(ok)//2]:.1f} p95={ok_ord[int(len(ok)*0.95)]:.1f} '
              f'max={ok_ord[-1]:.1f} ms  |  sem resposta: {perdidos}')
    travas = [(t, p) for t, p in pings if p is not None and p > 100]
    print(f'travas > 100 ms: {len(travas)}')
    for t, p in travas[:25]:
        print(f'    t={t - t0:7.2f}s  {p:8.1f} ms')

    if linhas:
        presa = [(t, dur) for t, dur in intervalos(linhas, 'input_rects', lambda v: v > 0)]
        print(f'\nregiao de clique nao vazia: {len(presa)} intervalos')
        for t, dur in presa[:25]:
            print(f'    t={t - t0:7.2f}s  por {dur:6.2f}s')
        def ocupada(v):
            return v == -1 or (v >= 0 and v not in SYSCALL_REPOUSO)

        fora = intervalos(linhas, 'syscall', ocupada)
        longos = [(t, d) for t, d in fora if d >= 0.10]
        print(f'\nthread de plataforma ocupada: {len(fora)} intervalos, '
              f'{len(longos)} deles >= 100 ms')
        for t, dur in longos[:15]:
            print(f'    t={t - t0:7.2f}s  por {dur * 1000:6.0f} ms')
        vistos = {}
        for l in linhas:
            if ocupada(l['syscall']):
                vistos[l['syscall']] = vistos.get(l['syscall'], 0) + 1
        if vistos:
            print('    amostras ocupadas: ' + ', '.join(
                f'{"CPU(running)" if s == -1 else NOME_SYSCALL.get(s, s)}={n}'
                for s, n in sorted(vistos.items(), key=lambda kv: -kv[1])[:8]))


def grava_csv(caminho, pings, linhas, t0):
    with open(caminho, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['tipo', 't_s', 'valor', 'extra1', 'extra2'])
        for t, p in pings:
            w.writerow(['ping', f'{t - t0:.4f}', '' if p is None else f'{p:.2f}', '', ''])
        for l in linhas:
            w.writerow(['amostra', f'{l["t"] - t0:.4f}', l['input_rects'],
                        l['bound_rects'], l['syscall']])
    print(f'\nCSV: {caminho}')


def tecla(k):
    subprocess.run(['xdotool', 'key', '--clearmodifiers', k], check=False)


def segura_tecla(k, segundos):
    """F9 e push-to-talk: um tap nao exercita o mesmo caminho que segurar."""
    subprocess.run(['xdotool', 'keydown', '--clearmodifiers', k], check=False)
    time.sleep(segundos)
    subprocess.run(['xdotool', 'keyup', '--clearmodifiers', k], check=False)


def executa(args):
    pid = args.pid or acha_pid()
    if not pid:
        sys.exit('dito_app nao esta rodando')
    d = display.Display()
    achadas = janelas_do(pid, d)
    if not achadas:
        sys.exit(f'nenhuma janela com _NET_WM_PID={pid}')
    principal, sobre = separa(achadas)
    print(f'pid={pid}  principal={hex(principal.id) if principal else "-"}  '
          f'sobreposicao={hex(sobre.id) if sobre else "-"}')

    alvo = sobre if (args.alvo == 'sobreposicao' and sobre) else (principal or sobre)
    sonda = Sonda(alvo)
    amostrador = Amostrador(pid, principal, sobre, hz=args.hz)
    amostrador.start()

    pings, t0 = [], time.perf_counter()
    fim = t0 + args.segundos
    roteiro = threading.Thread(target=args.roteiro, args=(t0,), daemon=True) if args.roteiro else None
    if roteiro:
        roteiro.start()
    while time.perf_counter() < fim:
        t = time.perf_counter()
        pings.append((t, sonda.ping()))
        time.sleep(max(0, args.intervalo - (time.perf_counter() - t)))
    amostrador.parar.set()
    amostrador.join(timeout=1)

    resumo(pings, amostrador.linhas, t0, args.rotulo)
    if args.csv:
        grava_csv(args.csv, pings, amostrador.linhas, t0)


def main():
    p = argparse.ArgumentParser(description='Mede travamento da interface do Dito (Linux/X11).')
    p.add_argument('modo', choices=['observar', 'f9', 'cartao'])
    p.add_argument('--pid', type=int)
    p.add_argument('--segundos', type=float, default=30)
    p.add_argument('--voltas', type=int, default=10)
    p.add_argument('--tecla', default='Tab')
    p.add_argument('--pausa', type=float, default=8.0)
    p.add_argument('--alvo', choices=['sobreposicao', 'principal'], default='sobreposicao')
    p.add_argument('--hz', type=int, default=20)
    p.add_argument('--intervalo', type=float, default=0.02)
    p.add_argument('--csv')
    a = p.parse_args()

    if a.modo == 'f9':
        segura = 1.5
        a.segundos = max(a.segundos, a.voltas * (segura + a.pausa) + 4)

        def roteiro(_t0):
            time.sleep(2)
            for i in range(a.voltas):
                segura_tecla('F9', segura)
                time.sleep(a.pausa)
        a.roteiro, a.rotulo = roteiro, f'{a.voltas} ciclos de F9'
    elif a.modo == 'cartao':
        a.segundos = max(a.segundos, a.voltas * a.pausa + 6)

        def roteiro(_t0):
            time.sleep(3)
            for i in range(a.voltas):
                tecla(a.tecla)
                time.sleep(a.pausa)
        a.roteiro, a.rotulo = roteiro, f'{a.voltas} x tecla {a.tecla} no cartao'
    else:
        a.roteiro, a.rotulo = None, f'observacao de {a.segundos:.0f}s'

    executa(a)


if __name__ == '__main__':
    main()
