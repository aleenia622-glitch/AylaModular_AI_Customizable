"""Operações internas de arquivo sem depender de modos carregados."""
from pathlib import Path
import os
import shutil
import subprocess
from ayla_platform import IS_WINDOWS


def mover_sem_sobrescrever(source, directory):
    source, directory = Path(source), Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    number = 0
    while True:
        suffix = f' ({number})' if number else ''
        target = directory / f'{source.stem}{suffix}{source.suffix}'
        try:
            output = target.open('xb')
        except FileExistsError:
            number += 1
            continue
        try:
            with output, source.open('rb') as original:
                shutil.copyfileobj(original,output)
                output.flush()
                os.fsync(output.fileno())
            shutil.copystat(source,target)
            source.unlink()
            return target
        except Exception:
            # Remove somente o destino exclusivo criado por esta tentativa.
            target.unlink(missing_ok=True)
            raise


def executar_powershell(comando, timeout=30):
    if not IS_WINDOWS:
        return 'Este comando requer PowerShell do Windows. Use executar_comando para Bash no Linux.'
    result = subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',comando],
                            capture_output=True,text=True,timeout=timeout,encoding='utf-8',errors='replace',
                            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        return f'Erro ({result.returncode}): {result.stderr.strip()}'
    return result.stdout.strip() or 'Sem resultados.'
