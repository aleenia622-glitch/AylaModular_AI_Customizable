import subprocess
import re

def _winget_instalado() -> bool:
    """Verifica se o winget está instalado e disponível no PATH."""
    try:
        r = subprocess.run(["winget", "--version"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False

def _pesquisar_winget(nome_app: str) -> list[dict]:
    """
    Pesquisa pacotes no winget.
    Retorna lista de dicts com: nome, pacote_id, versao, correspondencia, origem.
    """
    try:
        # Executa winget search com --accept-source-agreements para evitar interações
        cmd = ["winget", "search", nome_app, "-n", "8", "--accept-source-agreements"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20, encoding="utf-8", errors="replace")
        
        if r.returncode != 0 and not r.stdout.strip():
            return []
            
        lines = r.stdout.splitlines()
        
        # Encontra a linha de traços que separa o cabeçalho dos dados
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
        
        # Encontra as posições das colunas com base no cabeçalho
        idx_name = 0
        
        # Procura por ID / Id
        idx_id = header_lower.find("id")
        if idx_id == -1:
            idx_id = 35  # Fallback comum se falhar
            
        # Procura por Versão / Version
        idx_ver = -1
        for v_word in ["versão", "versao", "version", "versn"]:
            idx_ver = header_lower.find(v_word)
            if idx_ver != -1:
                break
        if idx_ver == -1:
            idx_ver = 60  # Fallback comum se falhar
            
        # Procura por Correspondência / Match
        idx_match = -1
        for m_word in ["correspondência", "correspondencia", "match"]:
            idx_match = header_lower.find(m_word)
            if idx_match != -1:
                break
                
        # Procura por Origem / Source
        idx_src = -1
        for s_word in ["origem", "source"]:
            idx_src = header_lower.find(s_word)
            if idx_src != -1:
                break
                
        # Monta a lista de colunas ativas e suas posições iniciais
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
            # Ignora linhas informativas do winget
            line_lower = line_str.lower()
            if line_str.startswith("<") or "contratos" in line_lower or "termos" in line_lower or "acordo" in line_lower:
                continue
                
            pkg = {}
            for i, (start, name) in enumerate(cols):
                end = cols[i+1][0] if i+1 < len(cols) else None
                val = line[start:end].strip() if start < len(line) else ""
                pkg[name] = val
                
            # Verifica se pelo menos o nome e o ID estão presentes
            if pkg.get("nome") and pkg.get("pacote_id"):
                # Filtra cabeçalhos acidentais caso restem
                if pkg["nome"].lower() in ("nome", "name") and pkg["pacote_id"].lower() in ("id", "identifier"):
                    continue
                resultados.append(pkg)
                
        return resultados
    except Exception as e:
        print(f"⚠️ Erro ao pesquisar no winget: {e}")
        return []

CONFIRMACAO_INSTALAR = "SIM, tenho certeza"

def instalar_app(nome_app: str, confirmar: str = "") -> str:
    """
    Pesquisa um aplicativo no winget e instala o mais relevante.
    
    - nome_app: Nome do aplicativo para pesquisar (ex: "firefox", "vscode", "7zip")
    - confirmar: "SIM, tenho certeza" para instalar o primeiro resultado direto.
                 Qualquer outro valor apenas lista os resultados encontrados.
    """
    if not nome_app or not nome_app.strip():
        return "⚠️ Preciso do nome do aplicativo para pesquisar!"

    # 1. Verifica se o winget está instalado
    if not _winget_instalado():
        return (
            "❌ O winget (Gerenciador de Pacotes do Windows) não está disponível.\n"
            "💡 O winget é nativo no Windows 10/11. Certifique-se de que ele está atualizado."
        )

    # 2. Pesquisa no winget
    resultados = _pesquisar_winget(nome_app)

    if not resultados:
        return (
            f"😢 Não encontrei nenhum pacote para '{nome_app}' no winget!\n"
            f"💡 Tente outro nome ou pesquise com um termo diferente."
        )

    # 3. Monta a lista de resultados
    lista_texto = f"🦅 **Resultados no winget para '{nome_app}':**\n\n"
    for i, pkg in enumerate(resultados, 1):
        lista_texto += f"**{i}.** 📦 **{pkg['nome']}** (v{pkg.get('versao', '?')})\n"
        lista_texto += f"   🆔 ID: `{pkg['pacote_id']}`"
        if pkg.get('origem'):
            lista_texto += f" | 🌐 Origem: {pkg['origem']}"
        if pkg.get('correspondencia'):
            lista_texto += f" | 🔍 Correspondência: _{pkg['correspondencia']}_"
        lista_texto += "\n\n"

    # 4. Instala somente com confirmação literal
    if (confirmar or "").strip() == CONFIRMACAO_INSTALAR:
        pacote = resultados[0]
        lista_texto += f"⏳ **Instalando:** `{pacote['pacote_id']}` (v{pacote.get('versao', '?')})...\n\n"

        try:
            # Comando do winget para instalar mostrando o progresso no terminal
            cmd_winget = [
                "winget", "install", pacote["pacote_id"],
                "--accept-package-agreements",
                "--accept-source-agreements"
            ]
            
            # Executamos herdando o stdout/stderr para que o progresso apareça em tempo real no terminal do bot
            resultado = subprocess.run(
                cmd_winget,
                timeout=300
            )

            # Verifica se instalou checando com winget list --id
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

TOOL_MAP["instalar_app"] = instalar_app

FUNCTION_DECLARATIONS.append({
    "name": "instalar_app",
    "description": (
        "Pesquisa um aplicativo no repositório winget (Gerenciador de Pacotes do Windows). "
        "Só instala se confirmar='SIM, tenho certeza'; sem isso apenas lista resultados."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "nome_app": {
                "type": "string",
                "description": "Nome do aplicativo para pesquisar e instalar (ex: 'firefox', 'vscode', '7zip', 'discord')"
            },
            "confirmar": {
                "type": "string",
                "description": "Obrigatório para instalar o primeiro resultado: SIM, tenho certeza"
            }
        },
        "required": ["nome_app"]
    }
})
