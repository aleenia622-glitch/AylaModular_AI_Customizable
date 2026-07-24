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
        base = Path(r"C:\Users\Aleenia\Desktop") / nome_projeto
        base.mkdir(parents=True, exist_ok=True)
        
        if arquivos:
            # 1. Normaliza as chaves do dicionário de arquivos (ex: index_html -> index.html)
            arquivos_normalizados = {}
            for nome_arquivo, conteudo in arquivos.items():
                for ext in ["html", "css", "js", "json", "py", "txt", "md"]:
                    if nome_arquivo.endswith(f"_{ext}"):
                        nome_arquivo = nome_arquivo.replace(f"_{ext}", f".{ext}")
                arquivos_normalizados[nome_arquivo] = conteudo

            # 2. Se houver index.html, tenta embutir o style.css e script.js nele para gerar um único arquivo
            if "index.html" in arquivos_normalizados:
                html = arquivos_normalizados["index.html"]
                import re
                
                # Embutir CSS se existir
                css_key = None
                for k in arquivos_normalizados.keys():
                    if k.endswith(".css"):
                        css_key = k
                        break
                if css_key:
                    css_conteudo = arquivos_normalizados[css_key]
                    padrao_link = rf'<link\s+[^>]*href=["\']{re.escape(css_key)}["\'][^>]*>'
                    tag_style = f"<style>\n{css_conteudo}\n</style>"
                    if re.search(padrao_link, html):
                        html = re.sub(padrao_link, tag_style, html)
                    else:
                        html = html.replace("</head>", f"  {tag_style}\n</head>")
                
                # Embutir JS se existir
                js_key = None
                for k in arquivos_normalizados.keys():
                    if k.endswith(".js"):
                        js_key = k
                        break
                if js_key:
                    js_conteudo = arquivos_normalizados[js_key]
                    padrao_script = rf'<script\s+[^>]*src=["\']{re.escape(js_key)}["\'][^>]*>\s*</script>'
                    tag_script = f"<script>\n{js_conteudo}\n</script>"
                    if re.search(padrao_script, html):
                        html = re.sub(padrao_script, tag_script, html)
                    else:
                        html = html.replace("</body>", f"  {tag_script}\n</body>")
                
                # Grava o index.html consolidado
                (base / "index.html").write_text(html, encoding="utf-8")
                
                # Salva uma cópia na pasta ScriptsCriados
                scripts_criados_dir = Path(r"C:\Users\Aleenia\Documents\AI\ScriptsCriados")
                scripts_criados_dir.mkdir(parents=True, exist_ok=True)
                (scripts_criados_dir / f"{nome_projeto}.html").write_text(html, encoding="utf-8")
                
                # Grava outros arquivos adicionais (que não sejam os CSS/JS já embutidos)
                for nome_arquivo, conteudo in arquivos_normalizados.items():
                    if nome_arquivo != "index.html" and nome_arquivo != css_key and nome_arquivo != js_key:
                        (base / nome_arquivo).write_text(conteudo, encoding="utf-8")
            else:
                # Se não houver index.html, grava os arquivos recebidos normalmente
                for nome_arquivo, conteudo in arquivos_normalizados.items():
                    (base / nome_arquivo).write_text(conteudo, encoding="utf-8")
        else:
            # Template Premium Padrão (Fallback) - Tudo consolidado em um só index.html
            html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{nome_projeto} - Premium Workspace</title>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    :root {{ --accent-color: #38bdf8; }}
    body {{ background: #0b0f19; color: white; font-family: 'Outfit', sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
    .card {{ background: rgba(17,24,39,0.8); padding: 40px; border-radius: 28px; border: 1px solid rgba(255,255,255,0.1); text-align: center; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="card">
      <h1>{nome_projeto}</h1>
      <p>Ambiente criado automaticamente. Edite o index.html para começar!</p>
    </div>
  </div>
  <script>
    console.log('🚀 Ambiente Premium Iniciado!');
  </script>
</body>
</html>"""
            
            (base / "index.html").write_text(html_content, encoding="utf-8")
            
            # Salva uma cópia na pasta ScriptsCriados
            scripts_criados_dir = Path(r"C:\Users\Aleenia\Documents\AI\ScriptsCriados")
            scripts_criados_dir.mkdir(parents=True, exist_ok=True)
            (scripts_criados_dir / f"{nome_projeto}.html").write_text(html_content, encoding="utf-8")
        
        # Abre no navegador o index.html (se existir)
        index_path = base / "index.html"
        if index_path.exists():
            webbrowser.open(index_path.as_uri())
            
            # Sinaliza para a Ayla enviar o arquivo index.html no Discord
            import ayla_state
            ayla_state.ULTIMA_IMAGEM_GERADA.set(str(index_path))
        
        # Abre a pasta no explorador do Windows
        os.startfile(base)
        
        return f"✅ Ambiente '{nome_projeto}' configurado com sucesso no Desktop, copiado para 'ScriptsCriados' e enviado no Discord!"
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
    "description": "Cria ambiente web no Desktop. Consolida automaticamente arquivos CSS e JS recebidos diretamente dentro do index.html para gerar um arquivo único.",
    "parameters": {
        "type": "object",
        "properties": {
            "nome_projeto": {"type": "string", "description": "Nome da pasta do projeto"},
            "arquivos": {
                "type": "object", 
                "description": "Dicionário { 'nome_arquivo': 'conteúdo' }. Ex: {'index.html': '...', 'style.css': '...', 'script.js': '...'}. O script embutirá o CSS/JS automaticamente no HTML para gerar um arquivo único.",
                "additionalProperties": {"type": "string"}
            }
        },
        "required": ["nome_projeto"]
    }
})
