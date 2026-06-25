import subprocess
from pathlib import Path


def _buscar_atalho_menu_iniciar(consulta: str):
    """Busca um atalho no Menu Iniciar do Windows"""
    try:
        menu_iniciar = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        
        if not menu_iniciar.exists():
            return None
        
        # Procura por arquivos .lnk que contenham a consulta
        for arquivo in menu_iniciar.rglob("*.lnk"):
            if consulta.lower() in arquivo.stem.lower():
                return arquivo
        
        return None
    except Exception:
        return None


def abrir_app(nome_ou_caminho: str) -> str:
    try:
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
        return f"Erro: {e}"


# Registrar apenas se as variáveis globais existirem
try:
    TOOL_MAP["abrir_app"] = abrir_app
    FUNCTION_DECLARATIONS.append({"name": "abrir_app", "description": "Abre programa", "parameters": {"type": "object", "properties": {"nome_ou_caminho": {"type": "string"}}}})
except NameError:
    pass



