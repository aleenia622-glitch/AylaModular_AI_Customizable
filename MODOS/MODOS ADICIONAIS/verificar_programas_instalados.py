"""Lista programas instalados e suas versões."""
import shutil
from ayla_platform import IS_WINDOWS, run_command

def verificar_programas_instalados():
    """Lista programas instalados no sistema via registro."""
    try:
        if not IS_WINDOWS:
            commands = [('dpkg-query', ['-W', '-f=${binary:Package} ${Version}\n']),
                        ('rpm', ['-qa', '--qf', '%{NAME} %{VERSION}-%{RELEASE}\n']),
                        ('pacman', ['-Q']), ('apk', ['info', '-v'])]
            sections = []
            for executable, args in commands:
                if shutil.which(executable):
                    sections.append(run_command([executable, *args]))
                    break
            if shutil.which('flatpak'):
                sections.append(run_command(['flatpak', 'list', '--app', '--columns=application,version']))
            if shutil.which('snap'):
                sections.append(run_command(['snap', 'list']))
            if not sections:
                return 'Nenhum gerenciador de pacotes suportado encontrado.'
            output = '\n'.join(sections)
            return '📦 Pacotes instalados:\n' + output[:12000] + ('\n... lista truncada' if len(output) > 12000 else '')
        cmd = (
            'Get-ItemProperty '
            'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*, '
            'HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* '
            '2>$null | '
            'Where-Object { $_.DisplayName } | '
            'Select-Object DisplayName, DisplayVersion | '
            'Sort-Object DisplayName | '
            'Format-Table -AutoSize -Wrap | '
            'Out-String -Width 300'
        )

        resultado = subprocess.run(
            ['powershell', '-NoProfile', '-Command', cmd],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30
        )

        if resultado.returncode != 0:
            return f"❌ Erro ao listar programas: {resultado.stderr.strip()}"

        saida = resultado.stdout.strip()
        if not saida:
            return "📋 Nenhum programa encontrado (saída vazia)."

        linhas = [l for l in saida.split('\n') if l.strip() and not l.strip().startswith('---')]
        total = max(len(linhas) - 1, 0)  # subtract header line

        if len(saida) > 3500:
            saida = saida[:3500] + "\n\n... (lista truncada por tamanho)"

        return f"📦 **Programas Instalados** ({total} encontrados):\n\n```\n{saida}\n```"

    except subprocess.TimeoutExpired:
        return "❌ Tempo esgotado ao listar programas instalados."
    except Exception as e:
        return f"❌ Erro ao verificar programas instalados: {e}"

TOOL_MAP["verificar_programas_instalados"] = verificar_programas_instalados

FUNCTION_DECLARATIONS.append({
    "name": "verificar_programas_instalados",
    "description": "Lista todos os programas instalados no sistema com nome e versão, ordenados alfabeticamente.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": []
    }
})
