"""Caminhos da instalação, independentes do usuário e do diretório de execução."""
from pathlib import Path, PureWindowsPath
import os
import re
import subprocess

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / '.env'


def project_path(*parts):
    return BASE_DIR.joinpath(*parts)


def user_dir(kind):
    """Respeita pastas XDG traduzidas ou personalizadas pelo usuário."""
    names = {'DESKTOP': 'Desktop', 'DOCUMENTS': 'Documents', 'DOWNLOAD': 'Downloads', 'VIDEOS': 'Videos', 'PICTURES': 'Pictures', 'MUSIC': 'Music'}
    kind = kind.upper()
    if os.name != 'nt':
        try:
            result = subprocess.run(['xdg-user-dir', kind], capture_output=True,
                                    text=True, timeout=3, check=True)
            path = Path(result.stdout.strip())
            if result.stdout.strip() and path.is_absolute():
                return path
        except (OSError, subprocess.SubprocessError):
            pass
    return Path.home() / names[kind]


def resolve_path(value, base=None):
    """Resolve caminhos relativos; migra referências antigas à pasta AI/IA.

    Caminhos Windows externos ao projeto são rejeitados no Linux, pois não há
    como deduzir a montagem correspondente sem uma configuração do usuário.
    """
    text = os.path.expandvars(os.path.expanduser(os.fspath(value)))
    if os.name != 'nt' and re.match(r'^[a-zA-Z]:[\\/]', text):
        parts = PureWindowsPath(text).parts
        for i in range(len(parts) - 1):
            if parts[i].lower() in {'documents', 'documentos'} and parts[i + 1].lower() in {'ai', 'ia'}:
                return BASE_DIR.joinpath(*parts[i + 2:]).resolve()
        raise ValueError(f'Caminho do Windows sem equivalente configurado no Linux: {text}')
    if os.name != 'nt' and text.startswith('\\\\'):
        raise ValueError('Monte o compartilhamento de rede e informe seu caminho Linux.')
    path = Path(text)
    return (path if path.is_absolute() else Path(base or BASE_DIR) / path).resolve()
