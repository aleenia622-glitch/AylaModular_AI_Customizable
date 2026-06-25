
def screenshot_janela(titulo):
    """Captura screenshot de uma janela específica pelo título."""
    try:
        if not PYAUTOGUI_OK:
            return "❌ pyautogui não está disponível neste sistema."

        import pygetwindow as gw

        janelas = gw.getWindowsWithTitle(titulo)
        if not janelas:
            todas = gw.getAllTitles()
            sugestoes = [t for t in todas if t.strip() and titulo.lower() in t.lower()]
            if sugestoes:
                lista = "\n".join(f"  • {s}" for s in sugestoes[:10])
                return f"🔍 Janela '{titulo}' não encontrada. Janelas similares:\n{lista}"
            return f"❌ Nenhuma janela encontrada com o título '{titulo}'."

        janela = janelas[0]

        if janela.isMinimized:
            janela.restore()
            import time
            time.sleep(0.5)

        left = max(janela.left, 0)
        top = max(janela.top, 0)
        width = janela.width
        height = janela.height

        if width <= 0 or height <= 0:
            return "❌ A janela tem dimensões inválidas (pode estar minimizada ou oculta)."

        screenshot = pyautogui.screenshot(region=(left, top, width, height))

        projeto_raiz = Path(__file__).resolve().parent.parent
        pasta = projeto_raiz / "Aylafotitos"
        pasta.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        titulo_limpo = re.sub(r'[<>:"/\\|?*]', '_', titulo)[:50]
        nome_arquivo = f"janela_{titulo_limpo}_{timestamp}.png"
        caminho = pasta / nome_arquivo

        screenshot.save(str(caminho))

        global ULTIMA_IMAGEM_GERADA
        ULTIMA_IMAGEM_GERADA = str(caminho)

        return (
            f"📸 Screenshot da janela capturada!\n"
            f"🪟 Janela: {janela.title}\n"
            f"📐 Dimensões: {width}x{height}\n"
            f"📁 Salva em: {caminho}"
        )
    except ImportError:
        return "❌ pygetwindow não está instalado. Instale com: pip install pygetwindow"
    except Exception as e:
        return f"❌ Erro ao capturar screenshot da janela: {e}"

TOOL_MAP["screenshot_janela"] = screenshot_janela

FUNCTION_DECLARATIONS.append({
    "name": "screenshot_janela",
    "description": "Captura um screenshot de uma janela específica pelo título e salva na pasta Aylafotitos.",
    "parameters": {
        "type": "object",
        "properties": {
            "titulo": {
                "type": "string",
                "description": "Título (ou parte do título) da janela a ser capturada."
            }
        },
        "required": ["titulo"]
    }
})
