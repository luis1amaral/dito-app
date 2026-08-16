#!/usr/bin/env bash
# Builds the Dito .deb -- a THIN package, on purpose.
#
# apt.defaltm.com is hosted on Cloudflare Pages, which refuses to serve any file above 25 MiB
# (docs/armadilhas.md 6.1). A self-contained .deb carrying faster-whisper + ctranslate2 + the Qt
# stack would be several hundred MB and could never be published there. So the package ships the
# source only, declares in Depends everything Debian already packages (Qt, numpy, av,
# onnxruntime, pynput, ...), and leaves the handful of PyPI-only wheels to a per-user venv built
# on FIRST RUN. `pip install` as root from postinst is banned: it writes outside dpkg's control,
# and a postinst that fails wedges apt with no interface to explain why.
#
#   ./packaging/deb/make-deb.sh        -> dist/dito_<versao>_all.deb
#
# Idempotent: wipes packaging/deb/build/ and the previous .deb of the same version before
# building. Reads the version from pyproject.toml, so there is no second place to bump.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
cd "$ROOT"

PKG=dito
APPID=com.defalt.dito
STAGE=$HERE/build
ASSETS=src/dito/ui/assets
# Cloudflare Pages' documented per-file ceiling. Crossing it does not fail at build time on the
# repo side -- it fails at `wrangler pages deploy`, after the .deb is already tagged and the
# version already bumped. Better to hear it here.
MAX_BYTES=$((25 * 1024 * 1024))

command -v python3 >/dev/null || { echo "erro: python3 não encontrado" >&2; exit 1; }
python3 -c 'import tomllib' 2>/dev/null \
  || { echo "erro: python3 sem tomllib (precisa de 3.11+) — não consigo ler o pyproject.toml" >&2; exit 1; }
command -v dpkg-deb >/dev/null || { echo "erro: dpkg-deb não encontrado (apt install dpkg-dev)" >&2; exit 1; }

# --- metadados lidos do próprio projeto ---------------------------------------------------
VER=$(python3 -c '
import tomllib
with open("pyproject.toml", "rb") as f:
    print(tomllib.load(f)["project"]["version"])
')
[ -n "$VER" ] || { echo "erro: não li a versão do pyproject.toml" >&2; exit 1; }

# The lock is everything in [project.dependencies] that the .deb's Depends does NOT already
# provide. Those apt packages are visible inside the venv (it is created with
# --system-site-packages) and pip recognises them as installed, because each ships dist-info or
# egg-info metadata -- PySide6's lives in libpyside6-py3-6.8, pulled in by python3-pyside6.*.
# Listing them again would only invite pip to shadow the system copy with a PyPI wheel, which is
# the exact drift pyproject.toml's open floors exist to avoid.
# Anything NOT in this set falls through to the lock, which is the safe default: a new dependency
# gets installed rather than silently missing.
REQS=$(python3 -c '
import re, tomllib

FROM_APT = {"numpy", "pyside6", "pynput", "pyperclip", "python-xlib", "tomli-w"}
with open("pyproject.toml", "rb") as f:
    deps = tomllib.load(f)["project"]["dependencies"]
for spec in deps:
    name = re.split(r"[<>=!~;\[\s]", spec, maxsplit=1)[0].strip().lower()
    if name not in FROM_APT:
        print(spec)
')
[ -n "$REQS" ] || { echo "erro: requirements.lock sairia vazio — confira as dependências do pyproject.toml" >&2; exit 1; }

echo "empacotando $PKG $VER (all)"

# --- árvore instalada ----------------------------------------------------------------------
rm -rf "$STAGE"
install -d "$STAGE/DEBIAN" \
           "$STAGE/usr/lib/$PKG" \
           "$STAGE/usr/bin" \
           "$STAGE/usr/share/applications" \
           "$STAGE/usr/share/doc/$PKG" \
           "$STAGE/etc/xdg/autostart"

# The package keeps its own directory name inside /usr/lib/dito, so PYTHONPATH=/usr/lib/dito is
# all the launcher needs for `import dito` to resolve. Byte-code is left out: it would be stale
# the moment the interpreter changes minor version, and dpkg would not know to remove it.
cp -a src/$PKG "$STAGE/usr/lib/$PKG/"
find "$STAGE/usr/lib/$PKG" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$STAGE/usr/lib/$PKG" -name '*.py[co]' -delete
find "$STAGE/usr/lib/$PKG" -type f -exec chmod 644 {} +
find "$STAGE/usr/lib/$PKG" -type d -exec chmod 755 {} +

{
  echo "# Gerado por packaging/deb/make-deb.sh a partir do pyproject.toml — não editar à mão."
  echo "# Só o que o apt do Debian não tem. O resto chega pelos Depends do pacote e fica visível"
  echo "# dentro da venv porque ela é criada com --system-site-packages."
  printf '%s\n' "$REQS"
} > "$STAGE/usr/lib/$PKG/requirements.lock"
chmod 644 "$STAGE/usr/lib/$PKG/requirements.lock"

# --- lançador -------------------------------------------------------------------------------
# A wrapper, not a symlink: the code in /usr/lib/dito is owned by dpkg and the wheels live in a
# venv under $HOME, so something has to bridge the two interpreters at runtime. A symlink into
# either one would pick the wrong site-packages.
cat > "$STAGE/usr/bin/$PKG" <<'LAUNCHER'
#!/bin/sh
# Dito launcher. The .deb carries only source: apt.defaltm.com runs on Cloudflare Pages, which
# refuses files above 25 MiB, so the PyPI-only wheels cannot ride inside the package. They live
# in a per-user venv, built on first run -- never by the postinst, never as root.
set -eu

CODE=/usr/lib/dito

# `:-` and not `-`: on this machine the XDG_* variables are DEFINED AND EMPTY (Cinnamon exports
# them that way). With `-` the empty value survives, and "$empty/dito/venv" is the RELATIVE path
# dito/venv, created inside whatever directory the launcher happened to start in. Same trap
# documented in src/dito/paths.py and armadilhas 5.4.
DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}
VENV=$DATA_HOME/dito/venv
VENV_PY=$VENV/bin/python

export PYTHONPATH=${PYTHONPATH:+$PYTHONPATH:}$CODE

if [ ! -x "$VENV_PY" ]; then
  if [ "${DITO_BOOTSTRAP:-auto}" = "never" ]; then
    # Set by the autostart entry. Downloading hundreds of MB at login, with no window to show it,
    # is the one thing the silent daemon must never do.
    echo "dito: ambiente ainda não preparado — abra o Dito pelo menu uma vez." >&2
    exit 0
  fi

  # The graphical bootstrap runs on the SYSTEM interpreter, which is possible only because Qt
  # comes from apt (python3-pyside6.*): there is a window to show progress before the venv that
  # would otherwise provide it even exists.
  if python3 -c 'import importlib.util as u, sys; sys.exit(0 if u.find_spec("dito.bootstrap") else 1)' 2>/dev/null; then
    python3 -m dito.bootstrap || exit $?
  else
    # Fallback for a package built before the bootstrap UI landed: same two commands, in the
    # terminal. Keeps the .deb usable on its own instead of failing with an import error.
    echo "dito: preparando o ambiente em $VENV (só na primeira vez)…" >&2
    python3 -m venv --system-site-packages "$VENV"
    "$VENV_PY" -m pip install --disable-pip-version-check -r "$CODE/requirements.lock" >&2
  fi

  if [ ! -x "$VENV_PY" ]; then
    echo "dito: o ambiente não foi criado em $VENV — veja o erro acima." >&2
    exit 1
  fi
fi

exec "$VENV_PY" -m dito "$@"
LAUNCHER
chmod 755 "$STAGE/usr/bin/$PKG"

# --- .desktop --------------------------------------------------------------------------------
install -m 644 "$HERE/$APPID.desktop" "$STAGE/usr/share/applications/$APPID.desktop"
install -m 644 "$HERE/$APPID-autostart.desktop" "$STAGE/etc/xdg/autostart/$APPID-autostart.desktop"

# The menu entry is worthless if the subcommand it calls does not exist. A warning and not a
# failure: the window is being written in parallel, and the daemon half of the package works
# without it.
for sub in ui listen; do
  grep -q "add_parser(\"$sub\"" src/$PKG/cli.py \
    || echo "aviso: 'dito $sub' não existe em src/$PKG/cli.py — o .desktop que o chama não vai abrir nada"
done

if command -v desktop-file-validate >/dev/null 2>&1; then
  desktop-file-validate "$STAGE/usr/share/applications/$APPID.desktop"
  desktop-file-validate "$STAGE/etc/xdg/autostart/$APPID-autostart.desktop"
fi

# --- ícones ------------------------------------------------------------------------------------
# The artwork's real size must NOT be used as the directory name when it exceeds 512. hicolor's
# index.theme declares sizes only up to 512x512 and GTK skips any directory it does not declare,
# so a 1024x1024 PNG lands on disk and never renders. That already burned two projects in this
# house; it is why the clamp is 512 and not the artwork's own number. GTK scales down when drawing.
HICOLOR_MAX=512
icons=0
if [ -d "$ASSETS" ]; then
  # Matched by NAME, not "every PNG under assets/": the rest of that directory is UI artwork, and
  # promoting a random glyph to application icon would be a confident wrong answer.
  while IFS= read -r png; do
    px=$(file -b "$png" | grep -oE '[0-9]+ x [0-9]+' | head -1 | awk '{print $1}')
    if [ -z "$px" ]; then
      echo "aviso: não li o tamanho de $png — ignorado"
      continue
    fi
    if [ "$px" -gt "$HICOLOR_MAX" ]; then
      px=$HICOLOR_MAX
    fi
    install -d "$STAGE/usr/share/icons/hicolor/${px}x${px}/apps"
    install -m 644 "$png" "$STAGE/usr/share/icons/hicolor/${px}x${px}/apps/$APPID.png"
    echo "  ícone -> hicolor/${px}x${px}/apps/$APPID.png"
    icons=$((icons + 1))
  done < <(find "$ASSETS" -type f \( -name "$APPID*.png" -o -name 'icon*.png' -o -name "$PKG*.png" \) | sort)

  svg=$(find "$ASSETS" -type f \( -name "$APPID*.svg" -o -name 'icon*.svg' \) | sort | head -1)
  if [ -n "$svg" ]; then
    install -d "$STAGE/usr/share/icons/hicolor/scalable/apps"
    install -m 644 "$svg" "$STAGE/usr/share/icons/hicolor/scalable/apps/$APPID.svg"
    echo "  ícone -> hicolor/scalable/apps/$APPID.svg"
    icons=$((icons + 1))
  fi
fi
if [ "$icons" -eq 0 ]; then
  echo "aviso: nenhum ícone em $ASSETS/ (procurei ${APPID}*.png, icon*.png, ${PKG}*.png e o .svg)"
  echo "       o pacote sai sem ícone; rode de novo quando os PNGs existirem"
fi

# --- metadados do pacote --------------------------------------------------------------------
cat > "$STAGE/usr/share/doc/$PKG/copyright" <<EOF
Upstream-Name: $PKG
Files: *
Copyright: $(date +%Y) Luis Amaral
License: proprietary
 Uso pessoal. Todos os direitos reservados.
EOF
chmod 644 "$STAGE/usr/share/doc/$PKG/copyright"

# Anything under /etc is only protected from being overwritten on upgrade if dpkg is told it is a
# conffile. Without this, a user who edits the autostart entry loses the edit on the next upgrade.
echo "/etc/xdg/autostart/$APPID-autostart.desktop" > "$STAGE/DEBIAN/conffiles"
chmod 644 "$STAGE/DEBIAN/conffiles"

# Installed-Size is in KiB and counts only the installed tree, never DEBIAN/.
SIZE_KB=$(du -sk --exclude=DEBIAN "$STAGE" | cut -f1)
sed -e "s/@VERSION@/$VER/" -e "s/@INSTALLED_SIZE@/$SIZE_KB/" "$HERE/control.in" > "$STAGE/DEBIAN/control"
chmod 644 "$STAGE/DEBIAN/control"
if grep -q '@[A-Z_]\+@' "$STAGE/DEBIAN/control"; then
  echo "erro: sobrou placeholder não substituído no control:" >&2
  grep -n '@[A-Z_]\+@' "$STAGE/DEBIAN/control" >&2
  exit 1
fi

for script in postinst prerm postrm; do
  install -m 755 "$HERE/$script" "$STAGE/DEBIAN/$script"
  sh -n "$STAGE/DEBIAN/$script" || { echo "erro: $script não é sh válido" >&2; exit 1; }
done
sh -n "$STAGE/usr/bin/$PKG" || { echo "erro: o lançador não é sh válido" >&2; exit 1; }

# --- build --------------------------------------------------------------------------------------
mkdir -p dist
OUT="dist/${PKG}_${VER}_all.deb"
rm -f "$OUT"
# --root-owner-group replaces fakeroot: it stamps root:root on every entry without needing the
# files to actually be owned by root while building.
dpkg-deb --root-owner-group --build "$STAGE" "$OUT" >/dev/null

BYTES=$(stat -c %s "$OUT")
if [ "$BYTES" -gt "$MAX_BYTES" ]; then
  # Deleted, not just reported: apt-repo.sh sweeps ~/Desktop/Projetos/**/dist/*.deb, so leaving an
  # oversized package here would hand it to the next `apt-repo.sh publish` and only blow up at the
  # Pages upload, long after this script said something was wrong.
  rm -f "$OUT"
  echo >&2
  echo "erro: o pacote saiu com $(numfmt --to=iec --suffix=B "$BYTES") — o limite é 25 MiB." >&2
  echo "      apaguei $OUT para o apt-repo.sh não tentar publicá-lo." >&2
  echo "      apt.defaltm.com roda em Cloudflare Pages, que RECUSA servir arquivo acima disso." >&2
  echo "      Um .deb maior instala localmente e nunca chega a quem for baixar pelo apt." >&2
  echo "      Saída: manter o pacote fino (só o código) ou publicar o pesado num bucket R2," >&2
  echo "      que não tem esse teto." >&2
  exit 1
fi

echo
echo "pronto: $OUT ($(numfmt --to=iec --suffix=B "$BYTES"), instalado ~${SIZE_KB} kB)"
echo "  conferir:    dpkg-deb -I $OUT && dpkg-deb -c $OUT"
echo "  instalar:    sudo apt install ./$OUT"
echo "  publicar:    ~/dev/claude/tools/apt-repo.sh publish"
