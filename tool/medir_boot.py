#!/usr/bin/env python3
"""Cronometra o boot do Dito: do exec ate a sobreposicao atender o primeiro evento."""
import pathlib
import subprocess
import sys
import time

from Xlib import X, display

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from medir_travamento import Sonda, janelas_do, separa

BIN = 'build/linux/x64/release/bundle/dito_app'


def espera_janelas(pid, teto=40.0):
    d = display.Display()
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < teto:
        principal, sobre = separa(janelas_do(pid, d))
        if principal and sobre:
            return principal, sobre, time.perf_counter() - t0
        time.sleep(0.02)
    return None, None, None


def main():
    binario = sys.argv[1] if len(sys.argv) > 1 else BIN
    segundos = float(sys.argv[2]) if len(sys.argv) > 2 else 25.0
    print(f'lancando {binario}')
    t0 = time.perf_counter()
    proc = subprocess.Popen([binario], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    principal, sobre, t_janelas = espera_janelas(proc.pid)
    if not sobre:
        proc.terminate()
        sys.exit('as janelas nao apareceram em 40 s')
    print(f'janelas existem em {t_janelas:.2f}s apos o exec')

    sonda = Sonda(sobre)
    primeiro = None
    t1 = time.perf_counter()
    while primeiro is None and time.perf_counter() - t1 < 30:
        primeiro = sonda.ping(teto=1.0)
    print(f'sobreposicao respondeu o 1o ping em {time.perf_counter() - t0:.2f}s apos o exec '
          f'(round-trip {primeiro:.1f} ms)')

    vals, marcas = [], []
    t2 = time.perf_counter()
    while time.perf_counter() - t2 < segundos:
        t = time.perf_counter()
        p = sonda.ping()
        vals.append(p)
        marcas.append(t - t0)
        time.sleep(0.02)
    ok = sorted(v for v in vals if v is not None)
    print(f'\nprimeiros {segundos:.0f}s de vida: mediana={ok[len(ok)//2]:.1f} '
          f'p95={ok[int(len(ok)*.95)]:.1f} max={ok[-1]:.1f} ms')
    ruins = [(m, v) for m, v in zip(marcas, vals) if v is not None and v > 100]
    print(f'travas > 100 ms no boot: {len(ruins)}')
    for m, v in ruins[:20]:
        print(f'    t={m:6.2f}s apos exec  {v:8.1f} ms')
    print(f'\npid={proc.pid} continua rodando')


if __name__ == '__main__':
    main()
