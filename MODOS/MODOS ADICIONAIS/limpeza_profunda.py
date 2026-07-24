import os
import shutil
import subprocess
import ctypes
from pathlib import Path

# Garante compatibilidade se o arquivo for executado/importado individualmente
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

def eh_administrador() -> bool:
    """Verifica se o processo possui privilégios de Administrador."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False

def formatar_tamanho(tamanho_bytes: int) -> str:
    """Converte bytes para um formato legível (KB, MB, GB, etc.)."""
    for unidade in ['B', 'KB', 'MB', 'GB', 'TB']:
        if tamanho_bytes < 1024.0:
            return f"{tamanho_bytes:.2f} {unidade}"
        tamanho_bytes /= 1024.0
    return f"{tamanho_bytes:.2f} PB"

def limpar_diretorio(caminho_dir: str) -> tuple[int, int, int]:
    """
    Remove arquivos e subpastas de um diretório recursivamente sem deletar o diretório raiz.
    Retorna (arquivos_removidos, pastas_removidas, bytes_liberados)
    """
    removidos_arq = 0
    removidos_pasta = 0
    bytes_liberados = 0
    
    path_dir = Path(caminho_dir)
    if not path_dir.exists() or not path_dir.is_dir():
        return (0, 0, 0)
        
    try:
        itens = list(path_dir.iterdir())
    except Exception:
        return (0, 0, 0)
        
    for item in itens:
        try:
            # Proteção contra links simbólicos
            if item.is_symlink():
                try:
                    item.unlink()
                    removidos_arq += 1
                except:
                    pass
                continue
                
            if item.is_file():
                try:
                    tamanho = item.stat().st_size
                except:
                    tamanho = 0
                item.unlink()
                removidos_arq += 1
                bytes_liberados += tamanho
            elif item.is_dir():
                sub_arqs, sub_pastas, sub_bytes = limpar_diretorio(str(item))
                removidos_arq += sub_arqs
                removidos_pasta += sub_pastas
                bytes_liberados += sub_bytes
                try:
                    item.rmdir()
                    removidos_pasta += 1
                except:
                    pass
        except Exception:
            pass  # Ignora erros (arquivos em uso ou sem permissão)
            
    return (removidos_arq, removidos_pasta, bytes_liberados)

def limpar_temporarios() -> str:
    """Limpa arquivos temporários do usuário (%TEMP%) e do Windows Temp."""
    logs = []
    
    user_temp = os.environ.get('TEMP') or os.environ.get('TMP')
    if user_temp and os.path.exists(user_temp):
        arqs, pastas, bytes_liberados = limpar_diretorio(user_temp)
        logs.append(f"📁 **Temporários do Usuário (%temp%):**\n• Removidos: {arqs} arquivos e {pastas} pastas\n• Espaço liberado: {formatar_tamanho(bytes_liberados)}")
    else:
        logs.append("📁 **Temporários do Usuário (%temp%):** Diretório não encontrado.")
        
    sys_temp = r"C:\Windows\Temp"
    if os.path.exists(sys_temp):
        arqs, pastas, bytes_liberados = limpar_diretorio(sys_temp)
        logs.append(f"📁 **Temporários do Sistema (C:\\Windows\\Temp):**\n• Removidos: {arqs} arquivos e {pastas} pastas\n• Espaço liberado: {formatar_tamanho(bytes_liberados)}")
    else:
        logs.append("📁 **Temporários do Sistema (C:\\Windows\\Temp):** Diretório não encontrado.")
        
    return "\n".join(logs)

def limpar_shadow_copies() -> str:
    """Exclui cópias de sombra antigas via WMI/PowerShell ou vssadmin."""
    if not eh_administrador():
        return "🔐 **Cópias de Sombra (Shadow Copies):** Requer privilégios de Administrador para exclusão total de Shadow Copies."

    # Tenta usar WMI no PowerShell (mais compatível em sistemas cliente)
    wmi_cmd = "Get-WmiObject Win32_ShadowCopy | ForEach-Object { $_.Delete() }"
    res_wmi = subprocess.run(["powershell", "-NoProfile", "-Command", wmi_cmd], capture_output=True, text=True, errors="replace")
    if res_wmi.returncode == 0:
        return "✅ **Cópias de Sombra (Shadow Copies):** Todas as cópias antigas foram excluídas com sucesso via WMI/PowerShell!"

    # Fallback para vssadmin
    cmd = "vssadmin delete shadows /all /quiet"
    res = subprocess.run(["cmd", "/c", cmd], capture_output=True, text=True, encoding="cp850", errors="replace")
    output = (res.stdout or "") + (res.stderr or "")
    if res.returncode == 0:
        return "✅ **Cópias de Sombra (Shadow Copies):** Excluídas com sucesso via vssadmin!"
        
    if "no items found" in output.lower() or "não há itens correspondentes" in output.lower():
        return "ℹ️ **Cópias de Sombra (Shadow Copies):** Nenhuma cópia antiga foi encontrada no sistema."
        
    return f"❌ **Cópias de Sombra (Shadow Copies):** Falha ao excluir:\n• WMI: {res_wmi.stderr.strip()}\n• VssAdmin: {output.strip()}"

def gerenciar_sysmain(acao: str) -> str:
    """Gerencia e otimiza o serviço SysMain (Superfetch)."""
    acao = acao.lower().strip()
    if acao not in ["status", "otimizar", "desativar", "ativar", "reiniciar"]:
        return f"⚠️ Ação '{acao}' inválida para o serviço SysMain."

    # Verifica se o serviço existe
    check_cmd = "Get-Service -Name SysMain -ErrorAction SilentlyContinue"
    res = subprocess.run(["powershell", "-NoProfile", "-Command", check_cmd], capture_output=True, text=True, errors="replace")
    if res.returncode != 0 or not res.stdout.strip():
        return "❌ **Serviço SysMain (Superfetch):** Não encontrado neste sistema."

    is_admin = eh_administrador()

    if acao == "status":
        status_cmd = "Get-Service -Name SysMain | Select-Object -Property Name, Status, StartType | ConvertTo-Json"
        status_res = subprocess.run(["powershell", "-NoProfile", "-Command", status_cmd], capture_output=True, text=True, errors="replace")
        if status_res.returncode == 0:
            try:
                import json
                info = json.loads(status_res.stdout.strip())
                status = info.get("Status", "Desconhecido")
                start_type = info.get("StartType", "Desconhecido")
                
                # Mapeia os estados
                status_str = "Em Execução" if status in [4, "Running"] else "Parado"
                start_map = {0: "Boot", 1: "System", 2: "Automatic", 3: "Manual", 4: "Disabled"}
                start_type_str = start_map.get(start_type, str(start_type))
                
                return f"ℹ️ **Status do SysMain (Superfetch):**\n• Estado: {status_str}\n• Inicialização: {start_type_str}"
            except:
                return f"ℹ️ **Status do SysMain (Superfetch):** {status_res.stdout.strip()}"
        return f"❌ **Serviço SysMain:** Falha ao verificar status: {status_res.stderr.strip()}"

    if not is_admin:
        return f"🔐 **Serviço SysMain (Superfetch):** Ação '{acao}' requer privilégios de Administrador."

    if acao == "desativar":
        cmd = "Stop-Service -Name SysMain -Force -ErrorAction SilentlyContinue; Set-Service -Name SysMain -StartupType Disabled"
        res = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, errors="replace")
        if res.returncode == 0:
            return "✅ **Serviço SysMain (Superfetch):** Serviço parado e desativado com sucesso!"
        return f"❌ **Serviço SysMain:** Falha ao desativar: {res.stderr.strip()}"

    elif acao == "ativar":
        cmd = "Set-Service -Name SysMain -StartupType Automatic; Start-Service -Name SysMain"
        res = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, errors="replace")
        if res.returncode == 0:
            return "✅ **Serviço SysMain (Superfetch):** Serviço ativado e iniciado com sucesso!"
        return f"❌ **Serviço SysMain:** Falha ao ativar: {res.stderr.strip()}"

    elif acao == "reiniciar":
        cmd = "Restart-Service -Name SysMain -Force"
        res = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, errors="replace")
        if res.returncode == 0:
            return "✅ **Serviço SysMain (Superfetch):** Serviço reiniciado com sucesso!"
        return f"❌ **Serviço SysMain:** Falha ao reiniciar: {res.stderr.strip()}"

    elif acao == "otimizar":
        # Verifica se o disco primário é SSD
        media_cmd = "Get-PhysicalDisk | Select-Object -Property DeviceId, MediaType | ConvertTo-Json"
        media_res = subprocess.run(["powershell", "-NoProfile", "-Command", media_cmd], capture_output=True, text=True, errors="replace")
        
        is_ssd = False
        if media_res.returncode == 0:
            try:
                import json
                disks = json.loads(media_res.stdout.strip())
                if not isinstance(disks, list):
                    disks = [disks]
                for disk in disks:
                    media_type = disk.get("MediaType", "").upper()
                    if "SSD" in media_type:
                        is_ssd = True
                        break
            except:
                pass
                
        if is_ssd:
            cmd = "Stop-Service -Name SysMain -Force -ErrorAction SilentlyContinue; Set-Service -Name SysMain -StartupType Disabled"
            res = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, errors="replace")
            if res.returncode == 0:
                return "⚡ **SysMain (Superfetch) Otimizado:**\n• Drive SSD detectado. O serviço foi **parado e desativado** para evitar desgaste por escritas desnecessárias no SSD."
            return f"❌ **SysMain Otimizado:** Falha ao desativar: {res.stderr.strip()}"
        else:
            cmd = "Restart-Service -Name SysMain -Force"
            res = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, errors="replace")
            if res.returncode == 0:
                return "⚡ **SysMain (Superfetch) Otimizado:**\n• Drive SSD não detectado. O serviço foi **reiniciado** para refrescar o cache em memória (HDD)."
            return f"❌ **SysMain Otimizado:** Falha ao reiniciar: {res.stderr.strip()}"

def limpar_caches_sistema() -> str:
    """Limpa caches gerais do sistema (DNS, Prefetch, Windows Update Download Cache)."""
    logs = []
    
    # 1. DNS Cache (Não requer Admin)
    dns_cmd = "ipconfig /flushdns"
    dns_res = subprocess.run(["cmd", "/c", dns_cmd], capture_output=True, text=True, errors="replace")
    if dns_res.returncode == 0:
        logs.append("✅ **Cache de DNS:** Liberado/limpo.")
    else:
        logs.append(f"⚠️ **Cache de DNS:** Erro ao limpar: {dns_res.stderr.strip()}")
        
    # 2. Windows Update Download Cache
    update_path = r"C:\Windows\SoftwareDistribution\Download"
    is_admin = eh_administrador()
    if is_admin:
        stop_res = subprocess.run(["powershell", "-NoProfile", "-Command", "Stop-Service -Name wuauserv -Force"], capture_output=True, text=True, errors="replace")
        arqs, pastas, bytes_del = limpar_diretorio(update_path)
        start_res = subprocess.run(["powershell", "-NoProfile", "-Command", "Start-Service -Name wuauserv"], capture_output=True, text=True, errors="replace")
        logs.append(f"✅ **Cache de Atualizações (SoftwareDistribution):** Limpo {arqs} arquivos ({formatar_tamanho(bytes_del)})")
    else:
        # Tenta sem parar o serviço (parcial)
        arqs, pastas, bytes_del = limpar_diretorio(update_path)
        if arqs > 0:
            logs.append(f"⚠️ **Cache de Atualizações:** Limpo parcialmente {arqs} arquivos ({formatar_tamanho(bytes_del)}). Alguns arquivos podem estar em uso.")
        else:
            logs.append("🔐 **Cache de Atualizações:** Requer privilégios de Administrador para parar o serviço e limpar tudo.")
            
    # 3. Prefetch (C:\Windows\Prefetch)
    prefetch_path = r"C:\Windows\Prefetch"
    if is_admin:
        arqs, pastas, bytes_del = limpar_diretorio(prefetch_path)
        logs.append(f"✅ **Cache Prefetch:** Limpo {arqs} arquivos ({formatar_tamanho(bytes_del)})")
    else:
        logs.append("🔐 **Cache Prefetch:** Requer privilégios de Administrador.")
        
    return "\n".join(logs)

def limpeza_profunda(
    limpar_temps: bool = True,
    deletar_shadows: bool = False,
    acao_sysmain: str = "status",
    limpar_caches: bool = True
) -> str:
    """
    Realiza uma faxina profunda no sistema Windows para melhorar a performance.
    
    Argumentos:
    - limpar_temps (bool): Se deve limpar %temp% e C:\\Windows\\Temp. Padrão True.
    - deletar_shadows (bool): Se deve excluir Shadow Copies (requer Admin). Padrão False.
    - acao_sysmain (str): Ação para o Superfetch (SysMain): 'status', 'otimizar', 'desativar', 'ativar', 'reiniciar', 'nenhum'. Padrão 'status'.
    - limpar_caches (bool): Se deve limpar DNS, Prefetch e atualizações. Padrão True.
    """
    resumos = []
    is_admin = eh_administrador()
    
    resumos.append(
        f"🧹 ✨ **FAXINA PROFUNDA DO WINDOWS DA AYLA** ✨ 🧹\n"
        f"• Modo de Execução: {'Administrador (Completo) 🔓' if is_admin else 'Usuário Padrão (Limitado) 🔒'}"
    )
    
    if limpar_temps:
        resumos.append("⚙️ **[1/4] Limpeza de Arquivos Temporários:**\n" + limpar_temporarios())
        
    if deletar_shadows:
        resumos.append("⚙️ **[2/4] Limpeza de Shadow Copies:**\n" + limpar_shadow_copies())
        
    if acao_sysmain.lower().strip() != "nenhum":
        resumos.append(f"⚙️ **[3/4] Gerenciamento do SysMain (Ação: {acao_sysmain}):**\n" + gerenciar_sysmain(acao_sysmain))
        
    if limpar_caches:
        resumos.append("⚙️ **[4/4] Limpeza de Caches de Sistema:**\n" + limpar_caches_sistema())
        
    resumos.append("✨ **Faxina concluída! O computador da Mamãe agora está super leve e rapidinho! 🩵**")
    return "\n\n".join(resumos)

TOOL_MAP["limpeza_profunda"] = limpeza_profunda
FUNCTION_DECLARATIONS.append({
    "name": "limpeza_profunda",
    "description": "Realiza uma faxina profunda no Windows (arquivos temporários, shadow copies, otimização do serviço SysMain/Superfetch e caches em geral).",
    "parameters": {
        "type": "object",
        "properties": {
            "limpar_temps": {
                "type": "boolean",
                "description": "Se deve limpar arquivos temporários (%temp% e Windows Temp). Padrão é True."
            },
            "deletar_shadows": {
                "type": "boolean",
                "description": "Se deve excluir Shadow Copies antigas (necessita admin). Padrão é False."
            },
            "acao_sysmain": {
                "type": "string",
                "description": "Ação para o SysMain (Superfetch): 'status' (padrão), 'otimizar', 'desativar', 'ativar', 'reiniciar', ou 'nenhum'."
            },
            "limpar_caches": {
                "type": "boolean",
                "description": "Se deve limpar caches como DNS, Prefetch e histórico de downloads do Windows Update. Padrão é True."
            }
        }
    }
})
