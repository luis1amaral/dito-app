import sys

TAMANHOS = ("tiny", "base", "small", "medium", "large-v3")


def _ensure_std_streams() -> None:
    """Deixa stdin/stdout/stderr utilizaveis E em UTF-8 - as duas coisas que o motor precisa.

    (1) Windowed (console=False): sem console e sem redirect, stdout/err viram None e o primeiro
    print() derruba o processo. So substituimos quando estao None (os subcomandos runhidden do
    instalador escrevem num arquivo de log em vez de sumir).

    (2) UTF-8 no IPC: no Windows um pipe herda a code page ANSI (cp1252), entao os acentos que o
    Flutter le como UTF-8 viravam «�» (nos nomes de dispositivo e no texto transcrito).
    reconfigure forca UTF-8 nas duas pontas e roda SEMPRE, inclusive quando o Flutter fez spawn
    com pipes validos - por isso nao ha mais o return preguicoso de antes."""
    import os

    if sys.stdout is None or sys.stderr is None:
        target = None
        try:
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
            logs = os.path.join(base, "dito", "logs")
            os.makedirs(logs, exist_ok=True)
            target = open(  # noqa: SIM115 - vive o processo inteiro de proposito
                os.path.join(logs, "engine-frozen.log"),
                "a",
                buffering=1,
                encoding="utf-8",
                errors="replace",
            )
        except Exception:
            try:
                target = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
            except Exception:
                target = None
        if target is not None:
            if sys.stdout is None:
                sys.stdout = target
            if sys.stderr is None:
                sys.stderr = target

    # UTF-8 nas duas pontas do IPC: mata os «�» dos acentos no texto real do motor.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:
            pass


_ensure_std_streams()


def _baixar(nomes) -> int:
    from faster_whisper.utils import download_model

    for nome in nomes:
        try:
            print(f"Baixando modelo de voz Whisper ({nome})...")
            download_model(nome)
            print(f"Modelo ({nome}) baixado e pronto para uso.")
        except Exception as erro:  # noqa: BLE001
            # Never fail the installer: the app downloads on first use if this did not work.
            print(f"Nao consegui baixar o modelo ({nome}): {erro}")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] == "engine":
        from dito.engine_server import run_server
        return run_server()
    elif args[0] == "gpu":
        from dito import gpu_setup
        install = "--install" in args
        window = "--window" in args
        force = "--force" in args
        remove = "--remove" in args
        return gpu_setup.run(install=install, window=window, force=force, remove=remove)
    elif args[0] in ("download-model", "model"):
        pedidos = []
        for i, a in enumerate(args):
            if a in ("--model", "-m") and i + 1 < len(args):
                pedidos.append(args[i + 1])
            elif a not in ("download-model", "model") and not a.startswith("-"):
                pedidos.append(a)
        if not pedidos or "all" in pedidos or "todos" in pedidos:
            pedidos = list(TAMANHOS)
        return _baixar(pedidos)
    else:
        from dito.engine_server import run_server
        return run_server()


if __name__ == "__main__":
    sys.exit(main())
