import time

# Garante compatibilidade se o arquivo for executado/importado individualmente
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

def roll_no_mudae() -> str:
    """
    Executa o macro de roll no bot Mudae do Discord.
    Copia '$wa' para a área de transferência, pressiona Ctrl+V e Enter 8 vezes.
    Em seguida, copia '$tu' para a área de transferência, pressiona Ctrl+V e Enter 1 vez.
    """
    # Tenta obter das variáveis globais ou importar localmente
    pyautogui_ok = globals().get("PYAUTOGUI_OK", False)
    if not pyautogui_ok:
        try:
            import pyautogui
            pyautogui_ok = True
        except ImportError:
            pyautogui_ok = False

    pyperclip_ok = globals().get("PYPERCLIP_OK", False)
    if not pyperclip_ok:
        try:
            import pyperclip
            pyperclip_ok = True
        except ImportError:
            pyperclip_ok = False

    if not pyautogui_ok:
        return "⚠️ pyautogui não está disponível."
    if not pyperclip_ok:
        return "⚠️ pyperclip não está disponível."

    import pyautogui
    import pyperclip

    try:
        # Envia uma notificação opcional se disponível para avisar o usuário
        winotify_ok = globals().get("WINOTIFY_OK", False)
        if winotify_ok:
            try:
                from winotify import Notification
                Notification(
                    app_id="Ayla IA",
                    title="Roll no Mudae 🎲",
                    msg="Iniciando macro! Clique no chat do Discord AGORA (você tem 3 segundos)."
                ).show()
            except Exception:
                pass

        # Pequena contagem regressiva para dar tempo de focar na janela do Discord
        # Também faz uns bips sonoros para chamar atenção
        for count in range(3, 0, -1):
            try:
                import winsound
                winsound.Beep(800, 150)
            except Exception:
                pass
            time.sleep(1.0)

        # 1. Coloca '$wa' no clipboard
        pyperclip.copy("$wg")
        time.sleep(0.5)

        # 2. Executa Ctrl+V e Enter 9 vezes
        for _ in range(9):
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.1)
            pyautogui.press("enter")
            # Intervalo para o Discord enviar o comando sem engasgar ou dar spam
            time.sleep(0.8)

        # 3. Coloca '$tu' no clipboard
        pyperclip.copy("$tu")
        time.sleep(0.3)

        # 4. Executa Ctrl+V e Enter 1 vez
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.1)
        pyautogui.press("enter")

        return "✅ Modo Roll no Mudae executado com sucesso! Divirta-se nos rolls! <:ayla_feliz:1508877425394712727>"
    except Exception as e:
        return f"❌ Erro ao executar o Roll no Mudae: {e}"

TOOL_MAP["roll_no_mudae"] = roll_no_mudae
FUNCTION_DECLARATIONS.append({
    "name": "roll_no_mudae",
    "description": "Executa o macro de rolar no bot Mudae do Discord. Copia '$wa' e envia (Ctrl+V + Enter) 8 vezes, depois copia '$tu' e envia 1 vez.",
    "parameters": {
        "type": "object",
        "properties": {}
    }
})
