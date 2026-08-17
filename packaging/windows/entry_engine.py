import sys

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
        from faster_whisper.utils import download_model
        model_name = "small"
        for i, a in enumerate(args):
            if a in ("--model", "-m") and i + 1 < len(args):
                model_name = args[i + 1]
            elif a not in ("download-model", "model") and not a.startswith("-"):
                model_name = a
        print(f"Baixando modelo de voz Whisper ({model_name})...")
        download_model(model_name)
        print(f"Modelo ({model_name}) baixado e pronto para uso.")
        return 0
    else:
        from dito.engine_server import run_server
        return run_server()

if __name__ == "__main__":
    sys.exit(main())
