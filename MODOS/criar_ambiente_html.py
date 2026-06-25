import os
import webbrowser
from pathlib import Path
from typing import Dict, Optional

def criar_ambiente_html(nome_projeto: str, arquivos: Optional[Dict[str, str]] = None) -> str:
    """
    Cria um ambiente web no Desktop. 
    Se 'arquivos' for fornecido, cria exatamente os arquivos e conteúdos especificados,
    permitindo que a Ayla escolha se o CSS/JS será separado ou embutido no HTML.
    Se não, cria um template premium padrão.
    """
    try:
        base = Path.home() / "Desktop" / nome_projeto
        base.mkdir(parents=True, exist_ok=True)
        
        if arquivos:
            # Liberdade total: Ayla define cada arquivo e seu conteúdo
            for nome_arquivo, conteudo in arquivos.items():
                (base / nome_arquivo).write_text(conteudo, encoding="utf-8")
        else:
            # Template Premium Padrão (Fallback)
            html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{nome_projeto} - Premium Workspace</title>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <div class="container">
    <div class="card">
      <h1>{nome_projeto}</h1>
      <p>Ambiente criado automaticamente. Edite os arquivos para começar!</p>
    </div>
  </div>
  <script src="script.js"></script>
</body>
</html>"""
            css_content = ":root { --accent-color: #38bdf8; } body { background: #0b0f19; color: white; font-family: 'Outfit', sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; } .card { background: rgba(17,24,39,0.8); padding: 40px; border-radius: 28px; border: 1px solid rgba(255,255,255,0.1); text-align: center; }"
            js_content = "console.log('🚀 Ambiente Premium Iniciado!');"
            
            (base / "index.html").write_text(html_content, encoding="utf-8")
            (base / "style.css").write_text(css_content, encoding="utf-8")
            (base / "script.js").write_text(js_content, encoding="utf-8")
        
        # Abre no navegador o index.html (se existir)
        index_path = base / "index.html"
        if index_path.exists():
            webbrowser.open(index_path.as_uri())
        
        # Abre a pasta no explorador do Windows
        os.startfile(base)
        
        return f"✅ Ambiente '{nome_projeto}' configurado com sucesso no Desktop!"
    except Exception as e:
        return f"❌ Erro ao criar ambiente: {e}"

# Registro de compatibilidade da Ayla
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

TOOL_MAP["criar_ambiente_html"] = criar_ambiente_html
FUNCTION_DECLARATIONS.append({
    "name": "criar_ambiente_html",
    "description": "Cria ambiente web no Desktop. Pode receber um dicionário de arquivos para controle total da estrutura (CSS/JS juntos ou separados).",
    "parameters": {
        "type": "object",
        "properties": {
            "nome_projeto": {"type": "string", "description": "Nome da pasta do projeto"},
            "arquivos": {
                "type": "object", 
                "description": "Dicionário { 'nome_arquivo': 'conteúdo' }. Ex: {'index.html': '...', 'style.css': '...'}",
                "additionalProperties": {"type": "string"}
            }
        },
        "required": ["nome_projeto"]
    }
})
