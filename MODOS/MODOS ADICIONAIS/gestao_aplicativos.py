"""Abre e fecha aplicativos e pesquisa ou instala pacotes no sistema."""
import os
import shutil
import shlex
from ayla_platform import IS_WINDOWS, launch_app, run_command
import subprocess
import re
from pathlib import Path

if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []


# ══════════════════════════════════════════════════════════
#  1. ABRIR APLICATIVO
# ══════════════════════════════════════════════════════════

def _buscar_atalho_menu_iniciar(consulta: str):
    """Busca um atalho no Menu Iniciar do Windows."""
    try:
        menu_iniciar = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        if not menu_iniciar.exists():
            return None
        for arquivo in menu_iniciar.rglob("*.lnk"):
            if consulta.lower() in arquivo.stem.lower():
                return arquivo
        return None
    except Exception:
        return None


def abrir_app(nome_ou_caminho: str) -> str:
    """
    Abre um aplicativo ou programa no computador pelo nome, atalho do Menu Iniciar ou caminho completo.
    """
    try:
        if not IS_WINDOWS:
            launch_app(nome_ou_caminho)
            return f'✅ Aplicativo iniciado: {nome_ou_caminho}'
        caminho_informado = Path(nome_ou_caminho).expanduser()
        if caminho_informado.exists():
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", f"Start-Process '{str(caminho_informado)}'"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return f"✅ Abrindo: {nome_ou_caminho}"

        consulta = nome_ou_caminho.strip()
        atalho = _buscar_atalho_menu_iniciar(consulta)

        if atalho is not None:
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", f"Start-Process '{str(atalho)}'"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return f"✅ Abrindo atalho encontrado no Menu Iniciar: {atalho.name}"

        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", f"Start-Process '{consulta}'"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return f"✅ Tentando abrir: {nome_ou_caminho}"
    except Exception as e:
        return f"Erro ao abrir aplicativo: {e}"


# ══════════════════════════════════════════════════════════
#  2. FECHAR APLICATIVO
# ══════════════════════════════════════════════════════════

def fechar_app(nome_processo: str) -> str:
    """
    Encerra um aplicativo ou processo em execução no Windows pelo nome.
    """
    try:
        if not IS_WINDOWS:
            import psutil
            matches = [p for p in psutil.process_iter(['pid', 'name']) if p.info['name'] == nome_processo]
            if not matches:
                return f'Processo não encontrado: {nome_processo}'
            errors = []
            for process in matches:
                try:
                    process.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
                    errors.append(f'{process.pid}: {exc}')
            _, alive = psutil.wait_procs(matches, timeout=3)
            if errors or alive:
                return 'Encerramento incompleto: ' + '; '.join(errors + [f'PID {p.pid} ainda ativo' for p in alive])
            return f'✅ {len(matches)} processo(s) encerrado(s).'
        nome = nome_processo.replace(".exe", "")
        subprocess.run(["powershell", "-NoProfile", "-Command", f"Stop-Process -Name '{nome}' -Force"], capture_output=True)
        return f"✅ Processo '{nome}' encerrado (se existia)."
    except Exception as e:
        return f"Erro ao fechar aplicativo: {e}"


# ══════════════════════════════════════════════════════════
#  3. INSTALAR APLICATIVO (WINGET)
# ══════════════════════════════════════════════════════════

def _winget_instalado() -> bool:
    try:
        r = subprocess.run(["winget", "--version"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def _pesquisar_winget(nome_app: str) -> list[dict]:
    try:
        cmd = ["winget", "search", nome_app, "-n", "8", "--accept-source-agreements"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20, encoding="utf-8", errors="replace")
        if r.returncode != 0 and not r.stdout.strip():
            return []
            
        lines = r.stdout.splitlines()
        dash_idx = -1
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped and all(c == '-' for c in stripped) and len(stripped) > 5:
                dash_idx = idx
                break
                
        if dash_idx <= 0:
            return []
            
        header = lines[dash_idx - 1]
        header_lower = header.lower()
        
        idx_name = 0
        idx_id = header_lower.find("id")
        if idx_id == -1:
            idx_id = 35
            
        idx_ver = -1
        for v_word in ["versão", "versao", "version", "versn"]:
            idx_ver = header_lower.find(v_word)
            if idx_ver != -1:
                break
        if idx_ver == -1:
            idx_ver = 60
            
        idx_match = -1
        for m_word in ["correspondência", "correspondencia", "match"]:
            idx_match = header_lower.find(m_word)
            if idx_match != -1:
                break
                
        idx_src = -1
        for s_word in ["origem", "source"]:
            idx_src = header_lower.find(s_word)
            if idx_src != -1:
                break
                
        cols = [(idx_name, "nome"), (idx_id, "pacote_id"), (idx_ver, "versao")]
        if idx_match != -1:
            cols.append((idx_match, "correspondencia"))
        if idx_src != -1:
            cols.append((idx_src, "origem"))
            
        cols.sort(key=lambda x: x[0])
        
        resultados = []
        for line in lines[dash_idx + 1:]:
            line_str = line.strip()
            if not line_str:
                continue
            line_lower = line_str.lower()
            if line_str.startswith("<") or "contratos" in line_lower or "termos" in line_lower or "acordo" in line_lower:
                continue
                
            pkg = {}
            for i, (start, name) in enumerate(cols):
                end = cols[i+1][0] if i+1 < len(cols) else None
                val = line[start:end].strip() if start < len(line) else ""
                pkg[name] = val
                
            if pkg.get("nome") and pkg.get("pacote_id"):
                if pkg["nome"].lower() in ("nome", "name") and pkg["pacote_id"].lower() in ("id", "identifier"):
                    continue
                resultados.append(pkg)
                
        return resultados
    except Exception as e:
        print(f"⚠️ Erro ao pesquisar no winget: {e}")
        return []

def _instalar_linux(nome_app, confirmar):
    managers = [
        ('dnf', ['search', nome_app], ['install', '-y']),
        ('apt-get', None, ['install', '-y']),
        ('pacman', ['-Ss', nome_app], ['-S', '--noconfirm']),
        ('zypper', ['search', nome_app], ['--non-interactive', 'install']),
        ('apk', ['search', nome_app], ['add']),
    ]
    for executable, search, install in managers:
        if not shutil.which(executable):
            continue
        try:
            if confirmar.strip() != CONFIRMACAO_INSTALAR:
                command = ['apt-cache', 'search', nome_app] if executable == 'apt-get' else [executable, *search]
                output = run_command(command, timeout=60)
                return output[:8000] + "\nPara instalar, informe o nome EXATO do pacote em nome_app e confirmar='SIM, tenho certeza'."
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9+_.:@-]*', nome_app):
                return 'Informe um único nome exato de pacote, sem opções ou espaços.'
            command = [shutil.which(executable), *install, nome_app]
            if os.geteuid() != 0:
                if not shutil.which('pkexec'):
                    return 'Execute no terminal: sudo ' + shlex.join(command)
                command.insert(0, 'pkexec')
            output = run_command(command, timeout=300)
            return '✅ Gerenciador concluiu a instalação.\n' + output[-3000:]
        except Exception as exc:
            return f'Falha no gerenciador de pacotes: {exc}'
    return 'Gerenciador não suportado. Instale o aplicativo pelo gerenciador da distribuição.'


CONFIRMACAO_INSTALAR = "SIM, tenho certeza"

def instalar_app(nome_app: str, confirmar: str = "") -> str:
    """
    Pesquisa um aplicativo no winget e instala o mais relevante.
    """
    if not nome_app or not nome_app.strip():
        return "⚠️ Preciso do nome do aplicativo para pesquisar!"

    if not IS_WINDOWS:
        return _instalar_linux(nome_app, confirmar)

    if not _winget_instalado():
        return (
            "❌ O winget (Gerenciador de Pacotes do Windows) não está disponível.\n"
            "💡 O winget é nativo no Windows 10/11. Certifique-se de que ele está atualizado."
        )

    resultados = _pesquisar_winget(nome_app)

    if not resultados:
        return f"😢 Não encontrei nenhum pacote para '{nome_app}' no winget!\n💡 Tente outro nome ou pesquise com um termo diferente."

    lista_texto = f"🦅 **Resultados no winget para '{nome_app}':**\n\n"
    for i, pkg in enumerate(resultados, 1):
        lista_texto += f"**{i}.** 📦 **{pkg['nome']}** (v{pkg.get('versao', '?')})\n"
        lista_texto += f"   🆔 ID: `{pkg['pacote_id']}`"
        if pkg.get('origem'):
            lista_texto += f" | 🌐 Origem: {pkg['origem']}"
        if pkg.get('correspondencia'):
            lista_texto += f" | 🔍 Correspondência: _{pkg['correspondencia']}_"
        lista_texto += "\n\n"

    if (confirmar or "").strip() == CONFIRMACAO_INSTALAR:
        pacote = resultados[0]
        lista_texto += f"⏳ **Instalando:** `{pacote['pacote_id']}` (v{pacote.get('versao', '?')})...\n\n"

        try:
            cmd_winget = [
                "winget", "install", pacote["pacote_id"],
                "--accept-package-agreements",
                "--accept-source-agreements"
            ]
            resultado = subprocess.run(cmd_winget, timeout=300)

            check = subprocess.run(
                ["winget", "list", "--id", pacote["pacote_id"], "--accept-source-agreements"],
                capture_output=True, text=True, timeout=20,
                encoding="utf-8", errors="replace"
            )

            if check.returncode == 0:
                lista_texto += f"✅ **{pacote['nome']}** instalado com sucesso!"
            else:
                lista_texto += (
                    f"⚠️ O comando de instalação foi executado (exit code: {resultado.returncode}), "
                    f"mas não consegui confirmar se a instalação foi concluída.\n"
                    f"Verifique no menu Iniciar se o aplicativo foi instalado."
                )

        except subprocess.TimeoutExpired:
            lista_texto += f"⚠️ Timeout durante a instalação (5 min). O app pode estar instalando em segundo plano."
        except Exception as e:
            lista_texto += f"❌ Erro ao instalar: {e}"
    else:
        lista_texto += (
            "⚠️ Instalar aplicativos é uma ação sensível.\n"
            f"💡 Para instalar o primeiro resultado, chame a ferramenta com confirmar='{CONFIRMACAO_INSTALAR}'."
        )

    return lista_texto


TOOL_MAP["abrir_app"] = abrir_app
TOOL_MAP["fechar_app"] = fechar_app
TOOL_MAP["instalar_app"] = instalar_app
TOOL_MAP["gestao_aplicativos"] = abrir_app

FUNCTION_DECLARATIONS.append({
    "name": "abrir_app",
    "description": "Abre um aplicativo ou programa no computador pelo nome, atalho do Menu Iniciar ou caminho completo do executável.",
    "parameters": {
        "type": "object",
        "properties": {
            "nome_ou_caminho": {"type": "string", "description": "Nome do app (ex: 'chrome', 'notepad'), atalho do Menu Iniciar ou caminho do .exe"}
        },
        "required": ["nome_ou_caminho"]
    }
})

FUNCTION_DECLARATIONS.append({
    "name": "fechar_app",
    "description": "Encerra um aplicativo ou processo do sistema pelo nome (ex: 'chrome', 'notepad', 'discord'). Use para forçar o fechamento de programas.",
    "parameters": {
        "type": "object",
        "properties": {
            "nome_processo": {"type": "string", "description": "Nome do processo a encerrar (com ou sem .exe, ex: 'chrome' ou 'chrome.exe')"}
        },
        "required": ["nome_processo"]
    }
})

FUNCTION_DECLARATIONS.append({
    "name": "instalar_app",
    "description": "Pesquisa pacotes no gerenciador do sistema. No Linux, a instalação exige nome exato do pacote e confirmar='SIM, tenho certeza'. No Windows usa winget. Sem confirmação apenas pesquisa.",
    "parameters": {
        "type": "object",
        "properties": {
            "nome_app": {"type": "string", "description": "Nome do aplicativo para pesquisar e instalar (ex: 'firefox', 'vscode', '7zip', 'discord')"},
            "confirmar": {"type": "string", "description": "Obrigatório para instalar o primeiro resultado: SIM, tenho certeza"}
        },
        "required": ["nome_app"]
    }
})
