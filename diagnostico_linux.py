"""Diagnóstico local sem abrir a GUI, conectar contas ou alterar configurações."""
import importlib.util
import os
import shutil
import sys

from ayla_paths import BASE_DIR, ENV_PATH


def main():
    print(f'Python: {sys.version.split()[0]}')
    print(f'Instalação: {BASE_DIR}')
    print(f'Sessão: {os.environ.get("XDG_SESSION_TYPE", "não informada")}')
    print(f'Desktop: {os.environ.get("XDG_CURRENT_DESKTOP", "não informado")}')
    print(f'.env: {"presente" if ENV_PATH.is_file() else "ausente"} (conteúdo não exibido)')
    print('\nBibliotecas Python:')
    for name in ('discord', 'PySide6', 'PyQt5', 'PIL', 'psutil', 'numpy', 'cv2',
                 'pygame', 'sounddevice', 'soundfile', 'openai',
                 'groq', 'moviepy', 'dotenv', 'Xlib'):
        found = importlib.util.find_spec(name) is not None
        print(f'  {name}: {"OK" if found else "ausente"}')
    print('\nFerramentas do sistema (algumas são alternativas/opcionais):')
    for name in ('ffmpeg', 'ffprobe', 'xdg-open', 'xdg-user-dir', 'wpctl', 'pactl',
                 'playerctl', 'nmcli', 'wl-paste', 'xclip', 'wmctrl', 'spectacle',
                 'grim', 'gnome-screenshot', 'plasma-apply-wallpaperimage', 'fc-match',
                 'clamscan', 'qbittorrent', 'agy'):
        print(f'  {name}: {shutil.which(name) or "ausente"}')
    print('\nInstalação e limitações: LINUX.md')


if __name__ == '__main__':
    main()
