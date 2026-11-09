"""Integrações de sistema com detecção explícita de recursos Linux/Windows."""
from pathlib import Path
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import unquote, urlparse

from ayla_paths import BASE_DIR, resolve_path

IS_WINDOWS = os.name == 'nt'


def is_wayland():
    return not IS_WINDOWS and (os.environ.get('XDG_SESSION_TYPE') == 'wayland' or bool(os.environ.get('WAYLAND_DISPLAY')))


def run_command(args, timeout=30):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f'{args[0]}: código {result.returncode}')
    return result.stdout.strip()


def shell_command(command):
    if IS_WINDOWS:
        return ['powershell', '-NoProfile', '-NonInteractive', '-Command', command]
    return [shutil.which('bash') or '/bin/sh', '-c', command]


def open_path(value, reveal=False):
    path = resolve_path(value)
    if not path.exists():
        raise FileNotFoundError(path)
    if IS_WINDOWS:
        if reveal:
            subprocess.Popen(['explorer', '/select,', str(path)])
        else:
            os.startfile(str(path))
    else:
        target = path.parent if reveal and path.is_file() else path
        run_command(['xdg-open', str(target)], timeout=15)


def launch_terminal(args, cwd=BASE_DIR):
    args = [str(a) for a in args]
    if IS_WINDOWS:
        return subprocess.Popen(args, cwd=cwd, creationflags=subprocess.CREATE_NEW_CONSOLE)
    candidates = [('x-terminal-emulator', '-e'), ('konsole', '-e'),
                  ('gnome-terminal', '--'), ('xfce4-terminal', '-x'), ('kitty', '--'), ('xterm', '-e')]
    for executable, flag in candidates:
        if shutil.which(executable):
            return subprocess.Popen([executable, flag, *args], cwd=cwd)
    raise RuntimeError('Nenhum terminal disponível: instale konsole, gnome-terminal ou xterm.')


def set_wallpaper(value):
    path = resolve_path(value)
    if not path.is_file():
        raise FileNotFoundError(path)
    if IS_WINDOWS:
        import ctypes
        if not ctypes.windll.user32.SystemParametersInfoW(20, 0, str(path), 3):
            raise RuntimeError('Não foi possível aplicar o papel de parede.')
        return
    desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
    if 'kde' in desktop and shutil.which('plasma-apply-wallpaperimage'):
        run_command(['plasma-apply-wallpaperimage', str(path)])
    elif any(name in desktop for name in ('gnome', 'unity', 'budgie')):
        run_command(['gsettings', 'set', 'org.gnome.desktop.background', 'picture-uri', path.as_uri()])
        keys = run_command(['gsettings', 'list-keys', 'org.gnome.desktop.background'])
        if 'picture-uri-dark' in keys.splitlines():
            run_command(['gsettings', 'set', 'org.gnome.desktop.background', 'picture-uri-dark', path.as_uri()])
    elif 'cinnamon' in desktop:
        run_command(['gsettings', 'set', 'org.cinnamon.desktop.background', 'picture-uri', path.as_uri()])
    elif 'mate' in desktop:
        run_command(['gsettings', 'set', 'org.mate.background', 'picture-filename', str(path)])
    elif 'xfce' in desktop:
        props = run_command(['xfconf-query', '-c', 'xfce4-desktop', '-l']).splitlines()
        props = [p for p in props if p.endswith('/last-image')]
        if not props:
            raise RuntimeError('XFCE não expôs uma configuração de papel de parede.')
        for prop in props:
            run_command(['xfconf-query', '-c', 'xfce4-desktop', '-p', prop, '-s', str(path)])
    elif not is_wayland() and shutil.which('feh'):
        run_command(['feh', '--bg-fill', str(path)])
    else:
        raise RuntimeError('Papel de parede: ambiente não suportado; use as configurações do desktop.')


def set_volume(action, value=50):
    if action not in {'mute', 'unmute', 'definir'}:
        raise ValueError('Use mute, unmute ou definir.')
    value = max(0, min(100, int(value)))
    if shutil.which('wpctl'):
        if action == 'definir':
            run_command(['wpctl', 'set-volume', '@DEFAULT_AUDIO_SINK@', f'{value}%'])
        run_command(['wpctl', 'set-mute', '@DEFAULT_AUDIO_SINK@', '1' if action == 'mute' else '0'])
    elif shutil.which('pactl'):
        if action == 'definir':
            run_command(['pactl', 'set-sink-volume', '@DEFAULT_SINK@', f'{value}%'])
        run_command(['pactl', 'set-sink-mute', '@DEFAULT_SINK@', '1' if action == 'mute' else '0'])
    else:
        raise RuntimeError('Controle de volume requer wpctl (WirePlumber) ou pactl (PulseAudio).')


def notify(title, message):
    try:
        if IS_WINDOWS:
            from winotify import Notification
            Notification(app_id='Ayla', title=title, msg=message).show()
        else:
            run_command(['notify-send', title, message], timeout=5)
    except (ImportError, OSError, RuntimeError, subprocess.SubprocessError):
        pass


def capture_screen(region=None):
    from PIL import Image, ImageGrab
    if is_wayland():
        if region:
            raise RuntimeError('Captura por coordenadas de janela indisponível no Wayland. Use captura da tela.')
        desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
        with tempfile.TemporaryDirectory(prefix='ayla-screen-') as folder:
            path = Path(folder) / 'screen.png'
            if 'kde' in desktop and shutil.which('spectacle'):
                # Uma instância existente pode receber a solicitação por D-Bus
                # e fazer o processo chamado sair antes de gravar a imagem.
                command = ['spectacle', '-b', '-n', '-f', '-i', '-o', str(path)]
            elif shutil.which('grim'):
                command = ['grim', str(path)]
            elif shutil.which('gnome-screenshot'):
                command = ['gnome-screenshot', '-f', str(path)]
            else:
                raise RuntimeError('Captura no Wayland requer Spectacle (KDE), grim (wlroots) ou gnome-screenshot compatível com a sessão.')
            run_command(command, timeout=15)
            deadline = time.monotonic() + 5
            while True:
                try:
                    with Image.open(path) as img:
                        return img.convert('RGB')
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise RuntimeError(
                            f'{command[0]} terminou, mas não produziu uma imagem legível '
                            'em até 5 segundos. Verifique se a captura foi autorizada pelo desktop.'
                        ) from exc
                    time.sleep(0.05)
    box = None if region is None else (region[0], region[1], region[0] + region[2], region[1] + region[3])
    return ImageGrab.grab(bbox=box)


def list_windows():
    if IS_WINDOWS:
        import pygetwindow
        return [{'title': w.title, 'region': (w.left, w.top, w.width, w.height)}
                for w in pygetwindow.getAllWindows() if w.title]
    if is_wayland():
        raise RuntimeError('Wayland não expõe a lista global de janelas por título. Use ver_tela_atual ou uma sessão X11.')
    output = run_command(['wmctrl', '-lG'])
    windows = []
    for line in output.splitlines():
        parts = line.split(None, 7)
        if len(parts) == 8:
            windows.append({'id': parts[0], 'title': parts[7], 'region': tuple(map(int, parts[2:6]))})
    return windows


def read_clipboard():
    """Retorna (text/files/image, conteúdo), usando a sessão gráfica atual."""
    if is_wayland():
        base = ['wl-paste', '--no-newline']
        types = run_command(['wl-paste', '--list-types'], timeout=3).splitlines()
        flag = '--type'
    else:
        base = ['xclip', '-selection', 'clipboard', '-o']
        types = run_command([*base, '-t', 'TARGETS'], timeout=3).splitlines()
        flag = '-t'
    for mime, kind in [('image/png', 'image'), ('text/uri-list', 'files'),
                       ('x-special/gnome-copied-files', 'files'),
                       ('text/plain;charset=utf-8', 'text'), ('UTF8_STRING', 'text'), ('text/plain', 'text')]:
        if mime not in types:
            continue
        result = subprocess.run([*base, flag, mime], capture_output=True, timeout=3, check=True)
        if kind == 'image':
            return kind, result.stdout
        text = result.stdout.decode('utf-8', errors='replace')
        if kind == 'files':
            paths = []
            for line in text.splitlines():
                uri = urlparse(line)
                if uri.scheme == 'file' and uri.netloc in {'', 'localhost'}:
                    paths.append(unquote(uri.path))
            return kind, paths
        return kind, text
    return None, None


def startup_path():
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'autostart' / 'ayla.desktop'


def desktop_quote(value):
    value = str(value).replace('%', '%%')
    for char in ('\\', '"', '`', '$'):
        value = value.replace(char, '\\' + char)
    return '"' + value.replace('\\', '\\\\') + '"'


def set_startup(enabled):
    path = startup_path()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    command = ' '.join(desktop_quote(v) for v in (sys.executable, BASE_DIR / 'Ayla.py'))
    content = '[Desktop Entry]\nType=Application\nName=Ayla\nExec=' + command + '\nTerminal=false\n'
    path.write_text(content, encoding='utf-8')


def launch_app(target):
    target = str(target).strip()
    if not target:
        raise ValueError('Informe o aplicativo.')
    path = resolve_path(target)
    if path.exists():
        if path.suffix.lower() in {'.exe', '.bat', '.cmd', '.lnk'} and not IS_WINDOWS:
            raise ValueError('Executável do Windows: instale a versão Linux ou configure Wine explicitamente.')
        if path.suffix == '.desktop' and not IS_WINDOWS:
            run_command(['gio', 'launch', str(path)])
        elif path.is_file() and os.access(path, os.X_OK) and not IS_WINDOWS:
            subprocess.Popen([str(path)], cwd=BASE_DIR)
        else:
            open_path(path)
        return
    args = shlex.split(target, posix=not IS_WINDOWS)
    if args and shutil.which(args[0]):
        subprocess.Popen(args, cwd=BASE_DIR)
        return
    raise FileNotFoundError(f'Aplicativo não encontrado no PATH: {target}')


def play_wav_fallback(path):
    """Backend secundário para arquivos WAV; pygame continua sendo o principal."""
    if IS_WINDOWS:
        import winsound
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
    else:
        import sounddevice
        import soundfile
        data, rate = soundfile.read(str(path), dtype='float32')
        sounddevice.play(data, rate, blocking=False)


def stop_wav_fallback():
    if IS_WINDOWS:
        import winsound
        winsound.PlaySound(None, winsound.SND_PURGE)
    else:
        import sounddevice
        sounddevice.stop()
