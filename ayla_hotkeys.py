"""Atalho de interrupção registrado no KDE, inclusive em sessões Wayland."""
import subprocess
from PySide6.QtCore import QObject, Qt, Slot, SLOT
from PySide6.QtDBus import QDBusConnection
from PySide6.QtGui import QKeySequence, QShortcut


class EndShortcut(QObject):
    def __init__(self, window, callback):
        super().__init__(window)
        self.callback = callback
        self.action = ['ayla', 'stop_voice', 'Ayla', 'Interromper fala']
        self.bus = QDBusConnection.sessionBus()
        self.registered = False
        self.local = QShortcut(QKeySequence('End'), window)
        self.local.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.local.activated.connect(callback)
        try:
            self._call('doRegister', self._action())
            component = '/component/ayla'
            if not self.bus.connect('org.kde.kglobalaccel', component,
                                    'org.kde.kglobalaccel.Component',
                                    'globalShortcutPressed', self,
                                    SLOT('_pressed(QString,QString,qlonglong)')):
                raise RuntimeError('Não foi possível conectar o sinal do atalho.')
            keys = self._call('setShortcut', self._action(),
                              str([int(Qt.Key.Key_End)]), '2')
            if str(int(Qt.Key.Key_End)) not in keys:
                raise RuntimeError('End já está reservado ou não foi aceito pelo KDE.')
            self.registered = True
            self.local.setEnabled(False)
            print('[Voz] Atalho End registrado no KDE/Wayland.')
        except Exception as exc:
            print(f'[Voz] End global indisponível: {exc}. End funciona com a janela da Ayla ativa.')

    def _action(self):
        return repr(self.action)

    def _call(self, method, *args):
        result = subprocess.run(
            ['gdbus', 'call', '--session', '--dest', 'org.kde.kglobalaccel',
             '--object-path', '/kglobalaccel', '--method',
             'org.kde.KGlobalAccel.' + method, *args],
            capture_output=True, text=True, timeout=3)
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        return result.stdout

    @Slot(str, str, 'qlonglong')
    def _pressed(self, component, action, timestamp):
        if component == 'ayla' and action == 'stop_voice':
            self.callback()

    def close(self):
        if self.registered:
            try:
                self._call('setInactive', self._action())
            except Exception as exc:
                print(f'[Voz] Não foi possível liberar End: {exc}')
            finally:
                self.registered = False
        self.bus.disconnect('org.kde.kglobalaccel', '/component/ayla',
                            'org.kde.kglobalaccel.Component',
                            'globalShortcutPressed', self,
                            SLOT('_pressed(QString,QString,qlonglong)'))
