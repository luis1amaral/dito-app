#!/usr/bin/env bash
# Instala o Dito nesta máquina, do jeito que o pacote instala — e limpa o que era provisório.
#
#   tools/instalar.sh            build + instala + troca o autostart + religa
#   tools/instalar.sh --sem-sudo só o que não precisa de senha (build e verificação)
#
# Precisa de senha no passo do apt. O resto roda como usuário.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

passo() { printf '\n\033[1m» %s\033[0m\n' "$1"; }
ok()    { printf '  \033[32m✓\033[0m %s\n' "$1"; }
aviso() { printf '  \033[33m!\033[0m %s\n' "$1"; }

passo "Conferindo que a árvore está sã antes de empacotar"
.venv/bin/ruff check . >/dev/null && ok "lint limpo"
.venv/bin/python -m pytest -q -m "not x11" >/dev/null && ok "testes verdes"

passo "Gerando o pacote"
bash packaging/deb/make-deb.sh >/dev/null
DEB=$(ls -t dist/dito_*.deb | head -1)
VER_DEB=$(dpkg-deb -f "$DEB" Version)
ok "$(basename "$DEB") — $(du -h "$DEB" | cut -f1)"

if [ "${1:-}" = "--sem-sudo" ]; then
  aviso "parando aqui: o resto precisa de senha"
  echo
  echo "  para terminar:  sudo apt install -y $RAIZ/$DEB"
  exit 0
fi

passo "Parando o Dito que está rodando"
# See docs/armadilhas.md 5.8: /proc/PID/exe resolves the venv's python symlink to the real binary.
parados=""
for p in /proc/[0-9]*; do
  pid=${p#/proc/}
  [ "$pid" = "$$" ] && continue
  exe=$(readlink "$p/exe" 2>/dev/null) || continue
  case "$exe" in */python*) ;; *) continue;; esac
  case "$(tr '\0' ' ' < "$p/cmdline" 2>/dev/null)" in
    *"dito listen"*|*"dito ui"*)
      if kill "$pid" 2>/dev/null; then parados="$parados $pid"; ok "parei o pid $pid"; fi
      ;;
  esac
done
sleep 2

# Um que ignora o TERM segura o socket, e a instalação segue como se estivesse tudo certo.
for pid in $parados; do
  [ -d "/proc/$pid" ] || continue
  kill -9 "$pid" 2>/dev/null && aviso "o pid $pid ignorou o TERM; mandei KILL"
  sleep 1
done
if [ -S "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/dito/dito.sock" ] \
   && command -v ss >/dev/null && ss -xlp 2>/dev/null | grep -q 'dito/dito.sock'; then
  aviso "alguém ainda segura o socket de controle — a instalação segue, mas confira 'dito status'"
fi

passo "Instalando"
# Rodar de novo sem bump é normal aqui, e o apt trata "mesma versão" como downgrade e recusa.
sudo apt install -y --allow-downgrades --reinstall "$RAIZ/$DEB"
INSTALADA=$(dpkg-query -W -f='${Version}' dito 2>/dev/null || echo '?')
ok "instalado: $(dito --version 2>/dev/null || echo '?')"
# O apt resolve o caminho para o nome do pacote e pode preferir a versão do repositório.
[ "$INSTALADA" = "$VER_DEB" ] || aviso "instalou $INSTALADA, e o pacote gerado é $VER_DEB"

passo "Tirando o provisório que eu tinha deixado"
# O .deb traz o autostart em /etc/xdg e o .desktop em /usr/share; os de usuário apontavam para a
# venv do projeto e passariam a competir com o pacote.
for f in "$HOME/.config/autostart/com.defalt.dito.desktop" \
         "$HOME/.local/share/applications/com.defalt.dito.desktop"; do
  [ -e "$f" ] && rm -f "$f" && ok "removi $(basename "$f") de usuário"
done
[ -e "$HOME/.config/autostart/ditado-voz.desktop" ] && \
  rm -f "$HOME/.config/autostart/ditado-voz.desktop" && ok "removi o autostart do ditado antigo"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

passo "Primeira execução (monta a venv de usuário, se faltar)"
if dito --version >/dev/null 2>&1; then
  DITO_BOOTSTRAP=ask python3 -m dito.bootstrap --headless || aviso "o bootstrap reclamou; abra o app para ver a tela"
fi

passo "Subindo"
setsid dito listen >/dev/null 2>&1 < /dev/null &
sleep 12
if dito status; then
  ok "no ar"
else
  aviso "não respondeu — rode 'dito listen' num terminal para ver o erro"
fi

echo
ok "pronto. Procure «Dito» no menu, ou segure F9 e fale."
