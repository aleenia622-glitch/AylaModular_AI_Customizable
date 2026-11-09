"""Ponto de entrada de recarga, executado do disco pelo comando e pela ferramenta."""
from pathlib import Path
import runpy


def reload_active_manager(manager):
    from dotenv import load_dotenv

    root = Path(__file__).resolve().parent
    # Não use importlib.reload: ele recriaria o ContextVar usado pelos workers.
    namespace = runpy.run_path(str(root / 'ayla_modules.py'))
    updated_class = namespace['ModuleManager']
    method_globals = updated_class.registry.__globals__
    method_globals['ACTIVE_REGISTRY'] = manager.registry.__func__.__globals__['ACTIVE_REGISTRY']
    with manager.lock:
        load_dotenv(dotenv_path=Path(manager.base).resolve().parent / '.env', override=True)
        previous_class = manager.__class__
        manager.__class__ = updated_class
        try:
            manager.reload()
            if manager.errors:
                details = '; '.join(f'{name}: {error}' for name, error in manager.errors.items())
                raise RuntimeError(f'Recarga com módulos indisponíveis: {details}')
        except Exception:
            manager.__class__ = previous_class
            raise
    return len(manager.registry().tools)
