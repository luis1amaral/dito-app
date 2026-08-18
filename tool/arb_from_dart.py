"""Converte o catalogo de strings escrito a mao em ARB, o formato padrao do Flutter.

    python tool/arb_from_dart.py

Le lib/l10n/app_strings_{pt,en}.dart e escreve lib/l10n/app_{pt,en}.arb, preservando os
NOMES dos membros - e o que permite trocar a implementacao sem tocar nos pontos de uso.
"""
import json
import re
import sys

CONTRATO = 'lib/l10n/app_strings.dart'
FONTES = {'en': 'lib/l10n/app_strings_en.dart', 'pt': 'lib/l10n/app_strings_pt.dart'}
SAIDAS = {'en': 'lib/l10n/app_en.arb', 'pt': 'lib/l10n/app_pt.arb'}

MEMBRO = re.compile(
    r"^\s*String\s+(?:get\s+)?(\w+)\s*(\(([^)]*)\))?\s*=>\s*'(.*)';\s*$")
PARAM = re.compile(r'(\w+)\s+(\w+)')


def parametros(assinatura):
    if not assinatura:
        return {}
    return {nome: tipo for tipo, nome in PARAM.findall(assinatura)}


def para_icu(valor, nomes):
    """Interpolacao do Dart vira placeholder do ICU, e chave literal vira chave escapada."""
    texto = valor.replace("\\'", "'")
    for nome in sorted(nomes, key=len, reverse=True):
        texto = texto.replace('${' + nome + '}', f'\x00{nome}\x01')
        texto = re.sub(r'\$' + nome + r'\b', f'\x00{nome}\x01', texto)
    sobrou = re.search(r'\$\w+', texto)
    if sobrou:
        raise SystemExit(f'interpolacao nao declarada {sobrou.group()} em "{texto}"')
    # so agora: qualquer chave que reste e literal, e o ICU a leria como placeholder
    if '{' in texto or '}' in texto:
        raise SystemExit(f'chave literal em "{texto}" - o ICU precisa de escape manual')
    return texto.replace('\x00', '{').replace('\x01', '}')


def catalogo(caminho):
    entradas = {}
    for linha in open(caminho, encoding='utf-8'):
        achado = MEMBRO.match(linha)
        if not achado:
            continue
        nome, _, assinatura, valor = achado.groups()
        nomes = parametros(assinatura)
        entradas[nome] = (para_icu(valor, nomes), nomes)
    return entradas


contrato = catalogo(FONTES['en'])
if not contrato:
    sys.exit('nao consegui ler nenhuma string')

for idioma, fonte in FONTES.items():
    entradas = catalogo(fonte)
    faltando = set(contrato) - set(entradas)
    if faltando:
        sys.exit(f'{idioma} nao tem: {sorted(faltando)}')

    arb = {'@@locale': idioma}
    for nome, (valor, nomes) in entradas.items():
        arb[nome] = valor
        meta = {}
        if nomes:
            meta['placeholders'] = {p: {'type': t} for p, t in nomes.items()}
        arb[f'@{nome}'] = meta
    with open(SAIDAS[idioma], 'w', encoding='utf-8') as saida:
        json.dump(arb, saida, ensure_ascii=False, indent=2)
        saida.write('\n')
    print(f'{SAIDAS[idioma]}: {len(entradas)} strings')
