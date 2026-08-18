#!/usr/bin/env bash
# Extract, merge and compile the translation catalogues.
#
#   tools/i18n.sh extract   rebuild locales/dito.pot from the source
#   tools/i18n.sh merge     fold new strings into every existing .po, keeping translations
#   tools/i18n.sh compile   build the .mo files the app actually loads
#   tools/i18n.sh check     fail if any .po has untranslated or fuzzy entries
#   tools/i18n.sh all       extract + merge + compile
#
# Source strings are English and live in the code. Nothing here invents a translation: `merge`
# marks changed strings fuzzy so a human decides.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMINIO=dito
LOCALES="$RAIZ/src/dito/locales"
POT="$LOCALES/$DOMINIO.pot"
IDIOMAS=(pt_BR)

extrair() {
  mkdir -p "$LOCALES"
  # Run from the root with relative paths: absolute ones bake the author's machine into every
  # reference comment, so the catalogue churned whenever it was rebuilt somewhere else.
  # --keyword=_ is the default; ngettext needs the plural form spelled out.
  ( cd "$RAIZ" && find src/dito -name '*.py' -print0 \
    | sort -z \
    | xargs -0 xgettext \
        --language=Python \
        --keyword=_ \
        --keyword=ngettext:1,2 \
        --from-code=UTF-8 \
        --package-name="$DOMINIO" \
        --msgid-bugs-address=lluispaulop@gmail.com \
        --no-wrap \
        --sort-output \
        -o "$POT" )
  echo "  $(grep -c '^msgid ' "$POT") strings em $(realpath --relative-to="$RAIZ" "$POT")"
}

mesclar() {
  [ -f "$POT" ] || { echo "erro: rode 'extract' antes"; exit 1; }
  for idioma in "${IDIOMAS[@]}"; do
    local po="$LOCALES/$idioma/LC_MESSAGES/$DOMINIO.po"
    mkdir -p "$(dirname "$po")"
    if [ -f "$po" ]; then
      msgmerge --quiet --update --backup=none --no-wrap "$po" "$POT"
      echo "  $idioma atualizado"
    else
      msginit --no-translator --locale="$idioma" --input="$POT" --output-file="$po" >/dev/null
      echo "  $idioma criado"
    fi
  done
}

compilar() {
  local total=0
  for idioma in "${IDIOMAS[@]}"; do
    local po="$LOCALES/$idioma/LC_MESSAGES/$DOMINIO.po"
    [ -f "$po" ] || continue
    msgfmt --check-format -o "${po%.po}.mo" "$po"
    echo "  $idioma -> $(realpath --relative-to="$RAIZ" "${po%.po}.mo")"
    total=$((total + 1))
  done
  [ "$total" -gt 0 ] || { echo "erro: nenhum .po para compilar"; exit 1; }
}

conferir() {
  local falhou=0
  for idioma in "${IDIOMAS[@]}"; do
    local po="$LOCALES/$idioma/LC_MESSAGES/$DOMINIO.po"
    [ -f "$po" ] || { echo "  $idioma: sem .po"; falhou=1; continue; }
    local vazias fuzzy
    vazias=$(msgattrib --untranslated --no-wrap "$po" | grep -c '^msgid "' || true)
    fuzzy=$(msgattrib --fuzzy --no-wrap "$po" | grep -c '^msgid "' || true)
    # msgattrib always emits the header entry, so one is the floor, not a miss.
    vazias=$((vazias > 0 ? vazias - 1 : 0))
    fuzzy=$((fuzzy > 0 ? fuzzy - 1 : 0))
    printf '  %-8s %s sem tradução, %s duvidosa(s)\n' "$idioma" "$vazias" "$fuzzy"
    [ "$vazias" -eq 0 ] && [ "$fuzzy" -eq 0 ] || falhou=1
  done
  return "$falhou"
}

case "${1:-all}" in
  extract) extrair ;;
  merge)   mesclar ;;
  compile) compilar ;;
  check)   conferir ;;
  all)     extrair; mesclar; compilar ;;
  *) echo "uso: $0 [extract|merge|compile|check|all]"; exit 1 ;;
esac
