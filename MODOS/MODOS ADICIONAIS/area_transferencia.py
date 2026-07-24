import os

if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

def ler_area_transferencia() -> str:
    """
    Lê o conteúdo atual da área de transferência (Ctrl+C).
    Pode retornar texto puro ou caminhos de arquivos se a Mamãe copiou um arquivo no Explorer.
    """
    try:
        import win32clipboard
    except ImportError:
        return "⚠️ Para ler arquivos da área de transferência, preciso do pacote `pywin32`. A Mamãe precisa rodar `pip install pywin32` no terminal."
    aberto = False
    resultado = "Área de transferência está vazia ou contém formato não suportado."
    
    try:
        # Primeiro tenta ler usando PIL para imagens (prints, cópia direta da web, etc)
        try:
            from PIL import ImageGrab
            imagem = ImageGrab.grabclipboard()
            if imagem:
                if isinstance(imagem, list):
                    # Às vezes retorna lista de caminhos no Mac/Linux, mas no Windows geralmente é imagem
                    pass
                elif hasattr(imagem, 'save'):
                    pasta_temp = os.path.join(os.environ.get("TEMP", "C:\\Temp"))
                    os.makedirs(pasta_temp, exist_ok=True)
                    caminho_img = os.path.join(pasta_temp, "ayla_clipboard.png")
                    imagem.save(caminho_img, "PNG")
                    
                    import sys
                    PASTA_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    if PASTA_RAIZ not in sys.path:
                        sys.path.append(PASTA_RAIZ)
                    import ayla_state
                    
                    # Passa a imagem lida para a Ayla analisar na resposta atual
                    # (como se fosse um anexo enviado junto)
                    with open(caminho_img, "rb") as f:
                        bytes_img = f.read()
                    
                    imagens_atuais = ayla_state.ULTIMAS_IMAGENS_MODULO.get() or []
                    imagens_atuais.append((bytes_img, "image/png"))
                    ayla_state.ULTIMAS_IMAGENS_MODULO.set(imagens_atuais)
                    
                    return "🖼️ **Imagem copiada (Ctrl+C):**\nConsegui ler a imagem da sua área de transferência e já anexei ela nos meus olhos! Diga o que você quer que eu faça com ela."
        except Exception as e:
            print(f"Aviso ao tentar ler imagem do clipboard com PIL: {e}")

        # Se não for imagem pura, abre o clipboard para ver arquivos e texto
        win32clipboard.OpenClipboard()
        aberto = True
        
        # Verifica se tem arquivos copiados (CF_HDROP)
        if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_HDROP):
            dados = win32clipboard.GetClipboardData(win32clipboard.CF_HDROP)
            if dados:
                resultado = "📂 **Arquivos copiados (Ctrl+C):**\n"
                for arquivo in dados:
                    resultado += f"• `{arquivo}`\n"
                resultado += "\nDica: Você pode ler esses arquivos com a ferramenta `ler_arquivo` ou usar a Ayla para analisar os bytes caso envie anexado!"
        
        # Se não tem arquivo, verifica se tem texto unicode (CF_UNICODETEXT)
        elif win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
            dados = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
            if dados:
                # Limita o tamanho do texto para não estourar contexto
                texto = str(dados).strip()
                if len(texto) > 10000:
                    texto = texto[:10000] + "\n... [Texto muito longo truncado]"
                resultado = f"📝 **Texto copiado (Ctrl+C):**\n```\n{texto}\n```"
    except Exception as e:
        resultado = f"❌ Erro ao ler a área de transferência: {e}"
    finally:
        if aberto:
            try:
                win32clipboard.CloseClipboard()
            except:
                pass
        
    return resultado

TOOL_MAP["ler_area_transferencia"] = ler_area_transferencia

FUNCTION_DECLARATIONS.append({
    "name": "ler_area_transferencia",
    "description": "Lê exatamente o que está na área de transferência (Ctrl+C) do Windows. Pode ser um texto que a Alêenia copiou de um site ou o caminho de um arquivo/foto que ela copiou no explorador de arquivos.",
    "parameters": {
        "type": "object",
        "properties": {}
    }
})
