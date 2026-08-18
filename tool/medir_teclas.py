"""Prova que o app NAO nasce achando que uma tecla esta pressionada.

    python tool/medir_teclas.py

O Windows reporta o F10 como pressionado em GetAsyncKeyState sem ninguem encostar nele. Semear
o estado do hook a partir disso fazia o app subir achando que a reuniao ja estava em curso: o F9
era recusado e o F10 nunca gerava borda de subida. Este medidor compara as duas leituras.
"""
import ctypes
import os
import re
import subprocess
import sys
import time

u32 = ctypes.windll.user32
_alvos = [a for a in sys.argv[1:] if not a.startswith('--')]
EXE = _alvos[0] if _alvos else r'build\windows\x64\runner\Debug\dito_app.exe'
LOG = os.path.expandvars(r'%LOCALAPPDATA%\dito\logs\hotkeys.log')
VK = {'f9': 0x78, 'f10': 0x79}


def rodando():
    saida = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq dito_app.exe', '/NH'],
                           capture_output=True, text=True).stdout
    return 'dito_app.exe' in saida


subprocess.run(['taskkill', '/F', '/IM', 'dito_app.exe'], capture_output=True)
subprocess.run(['taskkill', '/F', '/IM', 'dito-engine.exe'], capture_output=True)
while rodando():
    time.sleep(0.25)

if '--sem-build' not in sys.argv:
    if subprocess.run(['flutter', 'build', 'windows', '--debug'], shell=True).returncode != 0:
        raise SystemExit('flutter build falhou')

print('o que o Windows diz, sem ninguem tocando no teclado:')
mentiu = False
for nome, vk in VK.items():
    baixo = (u32.GetAsyncKeyState(vk) & 0x8000) != 0
    print(f'  GetAsyncKeyState({nome}) = {"PRESSIONADA" if baixo else "solta"}')
    mentiu = mentiu or baixo

marca = os.path.getsize(LOG) if os.path.exists(LOG) else 0
subprocess.Popen([EXE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

estado = None
inicio = time.time()
while time.time() - inicio < 60 and estado is None:
    time.sleep(0.4)
    if not os.path.exists(LOG):
        continue
    with open(LOG, encoding='utf-8', errors='replace') as f:
        f.seek(marca)
        for linha in f:
            achado = re.search(r'estado do hook: \{(.+)\}', linha)
            if achado:
                estado = achado.group(1)

subprocess.run(['taskkill', '/F', '/IM', 'dito_app.exe'], capture_output=True)
subprocess.run(['taskkill', '/F', '/IM', 'dito-engine.exe'], capture_output=True)

if estado is None:
    raise SystemExit('o app nao reportou o estado do hook')

print(f'\no que o hook do app diz ao ligar as teclas:\n  {estado}')
campos = dict(par.split(': ', 1) for par in estado.split(', ') if ': ' in par)
falhas = []
if campos.get('_installed') != 'true':
    falhas.append('o hook nao instalou')
for acao in ('dictation', 'meeting'):
    if campos.get(acao) != 'false':
        falhas.append(f'{acao} nasceu como pressionada')

print()
if mentiu:
    print('(o Windows mentiu sobre alguma tecla nesta rodada - e exatamente o caso que importa)')
if falhas:
    print('REPROVOU: ' + '; '.join(falhas))
    sys.exit(1)
print('PASSA: nenhuma acao nasce pressionada, e o hook esta instalado')
