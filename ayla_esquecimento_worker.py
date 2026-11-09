"""Transporte isolado da curadoria; encerrar o processo encerra todas as tentativas."""
import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path


class AnaliseProcesso:
    def __init__(self, api_key=None, modelo_glm=None, raciocinio='auto'):
        self.eventos = queue.Queue(maxsize=64)
        self.parado = threading.Event()
        self.inicio = time.monotonic()
        self.process = subprocess.Popen(
            [sys.executable, '-u', str(Path(__file__).resolve())],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding='utf-8')
        self.process.stdin.write(json.dumps(dict(
            api_key=api_key, modelo_glm=modelo_glm, raciocinio=raciocinio)) + '\n')
        self.process.stdin.close()
        self.reader = threading.Thread(target=self._ler, daemon=True)
        self.reader.start()

    def _publicar(self, evento):
        while not self.parado.is_set():
            try:
                self.eventos.put(evento, timeout=0.1)
                return
            except queue.Full:
                pass

    def _ler(self):
        try:
            for linha in self.process.stdout:
                if self.parado.is_set():
                    break
                if linha.startswith('AYLA_EVENT:'):
                    self._publicar(json.loads(linha[len('AYLA_EVENT:'):]))
        finally:
            self.process.stdout.close()
            self._publicar(['fim', None, None])

    def parar(self):
        self.parado.set()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=0.2)
        self.reader.join(timeout=0.2)


def main():
    import os
    parent = os.getppid()
    def vigiar():
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline and os.getppid() == parent:
            time.sleep(1)
        os._exit(1)
    threading.Thread(target=vigiar, daemon=True).start()
    from ayla_esquecimento import analisar, ModelosEsgotados
    options = json.loads(sys.stdin.readline())
    def enviar(*evento):
        print('AYLA_EVENT:' + json.dumps(evento, ensure_ascii=False), flush=True)
    try:
        result = analisar(**options,
            progresso=lambda msg: enviar('forgetting_progress', msg),
            avaliacao=lambda kind, item: enviar('forgetting_item', kind, item))
        enviar('forgetting_result', result, None)
    except Exception as exc:
        enviar('forgetting_result', {'oferecer_glm': isinstance(exc, ModelosEsgotados)},
               'Análise interrompida: ' + type(exc).__name__)
    finally:
        # Threads de transporte não devem sobreviver ao resultado ou timeout.
        sys.stdout.flush()
        os._exit(0)


if __name__ == '__main__':
    main()
