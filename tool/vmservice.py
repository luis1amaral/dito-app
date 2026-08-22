#!/usr/bin/env python3
"""Cliente do Dart VM Service para depurar o Dito em build profile (isolates, stack, eval, timeline)."""
import argparse
import asyncio
import json
import re
import sys
import time
from collections import Counter
from itertools import count

import websockets

TIMEOUT_PADRAO = 10.0
STREAMS_TIMELINE = ['Dart', 'Embedder', 'GC']
NOMES_RELEVANTES = ('Frame', 'BUILD', 'RASTERIZER', 'VSYNC', 'PipelineItem', 'GPUFrame')


class VmServiceError(Exception):
    """Erro retornado pelo VM Service em resposta a uma chamada RPC."""


class VmServiceClient:
    """Cliente minimo de JSON-RPC 2.0 sobre WebSocket para o Dart VM Service."""

    def __init__(self, ws, timeout=TIMEOUT_PADRAO):
        self.ws = ws
        self.timeout = timeout
        self._ids = count(1)

    @classmethod
    async def connect(cls, uri, timeout=TIMEOUT_PADRAO):
        """Abre o WebSocket do VM Service, convertendo falha de rede em mensagem clara."""
        try:
            # getVMTimeline devolve megabytes; o limite padrao de 1 MB derruba a conexao.
            ws = await websockets.connect(uri, open_timeout=timeout, max_size=None)
        except (OSError, asyncio.TimeoutError, websockets.InvalidURI, websockets.InvalidHandshake) as e:
            sys.exit(f'nao foi possivel conectar ao VM Service em {uri}: {e}')
        return cls(ws, timeout=timeout)

    async def call(self, method, params=None):
        """Faz uma chamada RPC e devolve 'result', levantando VmServiceError se o VM recusar."""
        req_id = str(next(self._ids))
        payload = {'jsonrpc': '2.0', 'id': req_id, 'method': method, 'params': params or {}}
        try:
            await self.ws.send(json.dumps(payload))
            while True:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=self.timeout)
                msg = json.loads(raw)
                if msg.get('id') != req_id:
                    continue  # streamNotify de outras assinaturas, sem 'id', nao interessa aqui
                if 'error' in msg:
                    err = msg['error']
                    raise VmServiceError(f"{err.get('message', 'erro desconhecido')} (code={err.get('code')})")
                return msg.get('result', {})
        except asyncio.TimeoutError:
            raise VmServiceError(f'timeout esperando resposta de {method}')
        except websockets.ConnectionClosed as e:
            raise VmServiceError(f'conexao com o VM Service caiu durante {method}: {e}')

    async def close(self):
        """Fecha o WebSocket com o VM Service."""
        await self.ws.close()


def extract_uri_from_log(caminho):
    """Extrai a URI do VM Service de um arquivo de log via regex."""
    try:
        with open(caminho, encoding='utf-8', errors='replace') as f:
            texto = f.read()
    except OSError as e:
        sys.exit(f'nao foi possivel ler o log {caminho}: {e}')
    m = re.search(r'Dart VM service is listening on (\S+)', texto)
    if not m:
        m = re.search(r'(https?://[\w.]+:\d+/\S*)', texto)
    if not m:
        sys.exit(f'nenhuma URI do VM Service encontrada em {caminho}')
    return m.group(1).strip()


def to_ws_uri(uri):
    """Converte a URI http do VM Service em ws://.../ws, aceitando que ja venha pronta."""
    ws = uri.replace('http://', 'ws://', 1).replace('https://', 'wss://', 1)
    if ws.rstrip('/').endswith('/ws'):
        return ws
    if not ws.endswith('/'):
        ws += '/'
    return ws + 'ws'


def resolve_uri(args):
    """Determina a URI ws:// do VM Service a partir de --uri ou --log."""
    if args.uri:
        origem = args.uri
    elif args.log:
        origem = extract_uri_from_log(args.log)
    else:
        sys.exit('informe --uri ou --log para achar o VM Service')
    return to_ws_uri(origem)


async def find_isolate(client, selector):
    """Acha o isolateId a partir de id exato, nome (parcial), ou a primeira isolate 'main'."""
    vm = await client.call('getVM')
    isolates = vm.get('isolates', [])
    if not isolates:
        sys.exit('nenhuma isolate disponivel no VM Service')
    if selector:
        for ref in isolates:
            if ref.get('id') == selector:
                return ref['id']
        candidatos = [r for r in isolates if selector.lower() in (r.get('name') or '').lower()]
        if len(candidatos) == 1:
            return candidatos[0]['id']
        if len(candidatos) > 1:
            nomes = ', '.join(r.get('name', '?') for r in candidatos)
            sys.exit(f"nome '{selector}' ambiguo entre: {nomes}")
        sys.exit(f"isolate '{selector}' nao encontrada")
    for ref in isolates:
        if 'main' in (ref.get('name') or '').lower():
            return ref['id']
    return isolates[0]['id']


def resume_kind_pausada(kind):
    """Diz se um pauseEvent.kind representa isolate pausada de verdade."""
    return kind not in ('Resume', 'None', None)


async def cmd_isolates(client, args):
    """Lista as isolates do VM com id, nome e se estao pausadas."""
    vm = await client.call('getVM')
    isolates = vm.get('isolates', [])
    if not isolates:
        print('nenhuma isolate encontrada')
        return
    print(f'{len(isolates)} isolate(s):\n')
    for ref in isolates:
        try:
            info = await client.call('getIsolate', {'isolateId': ref['id']})
        except VmServiceError as e:
            print(f"{ref.get('name', '?'):30s} id={ref['id']:24s} erro ao consultar: {e}")
            continue
        kind = (info.get('pauseEvent') or {}).get('kind')
        marcador = 'PAUSADA' if resume_kind_pausada(kind) else 'rodando'
        print(f"{info.get('name', '?'):30s} id={ref['id']:24s} {marcador:8s} (pauseEvent={kind})")


def token_pos_para_linha_coluna(tabela, token_pos):
    """Traduz um tokenPos em (linha, coluna) usando a tokenPosTable do script."""
    for linha_info in tabela or []:
        linha = linha_info[0]
        pares = linha_info[1:]
        for i in range(0, len(pares), 2):
            if pares[i] == token_pos:
                return linha, pares[i + 1]
    return None, None


async def descreve_local(client, isolate_id, location, cache_scripts):
    """Resolve um SourceLocation em 'arquivo:linha:coluna', com cache de scripts ja lidos."""
    if not location:
        return ''
    script_ref = location.get('script') or {}
    script_id = script_ref.get('id')
    token_pos = location.get('tokenPos')
    uri = script_ref.get('uri', '?')
    if script_id is None or token_pos is None:
        return uri
    if script_id not in cache_scripts:
        try:
            cache_scripts[script_id] = await client.call(
                'getObject', {'isolateId': isolate_id, 'objectId': script_id})
        except VmServiceError:
            cache_scripts[script_id] = None
    script = cache_scripts.get(script_id)
    if not script:
        return uri
    linha, coluna = token_pos_para_linha_coluna(script.get('tokenPosTable'), token_pos)
    return f'{uri}:{linha}:{coluna}' if linha is not None else uri


async def formata_quadro(client, isolate_id, frame, cache_scripts):
    """Formata um quadro de pilha como 'Classe.metodo (arquivo:linha:coluna)'."""
    func = frame.get('function') or {}
    code = frame.get('code') or {}
    nome = func.get('name') or code.get('name') or '<sem nome>'
    dono = (func.get('owner') or {}).get('name')
    completo = f'{dono}.{nome}' if dono else nome
    local = await descreve_local(client, isolate_id, frame.get('location'), cache_scripts)
    kind = frame.get('kind')
    prefixo = f'[{kind}] ' if kind and kind != 'Regular' else ''
    return f'{prefixo}{completo}  ({local})' if local else f'{prefixo}{completo}'


async def cmd_stack(client, args):
    """Mostra a pilha Dart (getStack) de uma isolate, com quadros e awaiterFrames legiveis."""
    isolate_id = await find_isolate(client, args.isolate)
    resultado = await client.call('getStack', {'isolateId': isolate_id})
    cache_scripts = {}

    frames = resultado.get('frames', [])
    if not frames:
        print('pilha vazia (a isolate provavelmente esta rodando, nao pausada)')
    else:
        print(f'== quadros ({len(frames)}) ==')
        for i, frame in enumerate(frames):
            texto = await formata_quadro(client, isolate_id, frame, cache_scripts)
            print(f'#{i:02d}  {texto}')

    awaiter = resultado.get('awaiterFrames')
    if awaiter:
        print(f'\n== awaiterFrames ({len(awaiter)}) ==')
        for i, frame in enumerate(awaiter):
            texto = await formata_quadro(client, isolate_id, frame, cache_scripts)
            print(f'#{i:02d}  {texto}')


def escolhe_biblioteca(isolate_info):
    """Escolhe a biblioteca para avaliar: prefere package:dito_app/, senao a raiz da isolate."""
    libs = isolate_info.get('libraries', [])
    for lib in libs:
        if (lib.get('uri') or '').startswith('package:dito_app/'):
            return lib['id']
    root = isolate_info.get('rootLib')
    if root:
        return root.get('id')
    return libs[0]['id'] if libs else None


def formata_resultado_eval(resultado):
    """Formata o retorno de evaluate/evaluateInFrame de forma legivel para o operador."""
    tipo = resultado.get('type')
    if tipo in ('Error', '@Error'):
        return f"erro em tempo de execucao: {resultado.get('message', resultado)}"
    if tipo == 'Sentinel':
        return f"indisponivel: {resultado.get('valueAsString', resultado.get('kind'))}"
    if 'valueAsString' in resultado:
        sufixo = '...' if resultado.get('valueAsStringIsTruncated') else ''
        return f"{resultado.get('valueAsString')}{sufixo}"
    if 'class' in resultado:
        return f"<{resultado['class'].get('name', '?')}> id={resultado.get('id', '?')}"
    return json.dumps(resultado, ensure_ascii=False)


async def cmd_eval(client, args):
    """Avalia uma expressao Dart via evaluateInFrame (quadro 0) ou evaluate na biblioteca do app."""
    isolate_id = await find_isolate(client, args.isolate)

    resultado, erro_frame = None, None
    try:
        resultado = await client.call(
            'evaluateInFrame', {'isolateId': isolate_id, 'frameIndex': 0, 'expression': args.expressao})
    except VmServiceError as e:
        erro_frame = e

    if resultado is None:
        info = await client.call('getIsolate', {'isolateId': isolate_id})
        lib_id = escolhe_biblioteca(info)
        if not lib_id:
            sys.exit('nenhuma biblioteca encontrada na isolate para avaliar a expressao')
        try:
            resultado = await client.call(
                'evaluate', {'isolateId': isolate_id, 'targetId': lib_id, 'expression': args.expressao})
        except VmServiceError as e:
            detalhe = f' | evaluateInFrame tambem falhou: {erro_frame}' if erro_frame else ''
            print(f'erro ao avaliar "{args.expressao}": {e}{detalhe}')
            sys.exit(1)

    print(formata_resultado_eval(resultado))


async def liga_timeline_e_espera(client, segundos):
    """Liga os streams de timeline relevantes e espera N segundos antes de ler."""
    await client.call('setVMTimelineFlags', {'recordedStreams': STREAMS_TIMELINE})
    print(f'timeline ligada (streams={",".join(STREAMS_TIMELINE)}), aguardando {segundos:.1f}s...')
    await asyncio.sleep(segundos)
    return await client.call('getVMTimeline')


async def cmd_frames(client, args):
    """Liga a timeline, espera N segundos, e conta eventos por tipo (frame agendado x rasterizado)."""
    timeline = await liga_timeline_e_espera(client, args.segundos)
    eventos = timeline.get('traceEvents', [])
    print(f'\n{len(eventos)} eventos capturados na timeline\n')
    if not eventos:
        print('ZERO eventos: o motor Flutter nao esta nem agendando nada nesse intervalo')
        return

    contagem = Counter(e.get('name', '?') for e in eventos)
    print('== contagem por nome relevante (substring, agrega variantes) ==')
    algum = False
    for chave in NOMES_RELEVANTES:
        n = sum(v for nome, v in contagem.items() if chave.lower() in nome.lower())
        if n:
            algum = True
            print(f'  {chave:15s} {n}')
    if not algum:
        print('  nenhum nome da lista bateu — use o TOP 15 abaixo para achar o nome certo nesta versao')

    print('\n== top 15 nomes de evento por frequencia ==')
    for nome, n in contagem.most_common(15):
        print(f'  {n:6d}  {nome}')


async def cmd_timeline(client, args):
    """Liga a timeline, espera N segundos, e grava o JSON bruto (getVMTimeline) em arquivo."""
    timeline = await liga_timeline_e_espera(client, args.segundos)
    caminho = args.saida or f'timeline_{int(time.time())}.json'
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(timeline, f, ensure_ascii=False)
    print(f'{len(timeline.get("traceEvents", []))} eventos gravados em {caminho}')


def build_parser():
    """Monta o parser de linha de comando com os subcomandos do VM Service."""
    p = argparse.ArgumentParser(
        description='Cliente do Dart VM Service para depurar o Dito em build profile.')

    origem = argparse.ArgumentParser(add_help=False)
    origem.add_argument('--uri', help='URI do VM Service (http ou ws), ex: http://127.0.0.1:PORT/TOKEN=/')
    origem.add_argument('--log', help='arquivo de log de onde extrair a URI do VM Service')
    origem.add_argument('--timeout', type=float, default=TIMEOUT_PADRAO,
                         help='timeout em segundos para cada chamada RPC (padrao: %(default)s)')

    isolate_arg = argparse.ArgumentParser(add_help=False)
    isolate_arg.add_argument('--isolate', help='id ou nome (parcial) da isolate; padrao: a primeira "main"')

    sub = p.add_subparsers(dest='comando', required=True)

    sp = sub.add_parser('isolates', parents=[origem], help='lista as isolates do VM')
    sp.set_defaults(func=cmd_isolates)

    sp = sub.add_parser('stack', parents=[origem, isolate_arg], help='mostra a pilha Dart de uma isolate')
    sp.set_defaults(func=cmd_stack)

    sp = sub.add_parser('eval', parents=[origem, isolate_arg], help='avalia uma expressao Dart na isolate')
    sp.add_argument('expressao', help='expressao Dart a avaliar, ex: WidgetsBinding.instance.hasScheduledFrame')
    sp.set_defaults(func=cmd_eval)

    sp = sub.add_parser('frames', parents=[origem], help='conta eventos de timeline (Frame/BUILD/RASTERIZER/...)')
    sp.add_argument('segundos', type=float, help='duracao da captura em segundos')
    sp.set_defaults(func=cmd_frames)

    sp = sub.add_parser('timeline', parents=[origem], help='grava a timeline bruta (getVMTimeline) em JSON')
    sp.add_argument('segundos', type=float, help='duracao da captura em segundos')
    sp.add_argument('--saida', help='arquivo de saida (padrao: timeline_<epoch>.json)')
    sp.set_defaults(func=cmd_timeline)

    return p


async def executa(args):
    """Resolve a URI, conecta no VM Service e despacha para o subcomando escolhido."""
    uri = resolve_uri(args)
    client = await VmServiceClient.connect(uri, timeout=args.timeout)
    try:
        await args.func(client, args)
    except VmServiceError as e:
        sys.exit(f'erro do VM Service: {e}')
    finally:
        await client.close()


def main():
    """Ponto de entrada da CLI do cliente do Dart VM Service."""
    args = build_parser().parse_args()
    try:
        asyncio.run(executa(args))
    except KeyboardInterrupt:
        sys.exit(1)


if __name__ == '__main__':
    main()
