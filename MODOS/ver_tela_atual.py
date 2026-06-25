def ver_tela_atual() -> str:
    if not PYAUTOGUI_OK: return "pyautogui não instalado."
    try:
        from datetime import datetime
        print("Va ate o que voce quer que eu veja em 5 segundos.....")
        for segundos_restantes in range(5, 0, -1):
            print(f"👀 Olhando a tela em {segundos_restantes}...")
            time.sleep(1)

        projeto_raiz = Path(__file__).resolve().parent.parent
        PASTA_AYLA = projeto_raiz / "Aylafotitos"
        PASTA_AYLA.mkdir(parents=True, exist_ok=True)
        caminho_print = str(PASTA_AYLA / f"Ayla_visao_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        pyautogui.screenshot().save(caminho_print)
        
        # ULTIMA_IMAGEM_GERADA = caminho_print  # Removido para evitar o upload automático do print no Discord
        with open(caminho_print, "rb") as f: img_bytes = f.read()
        part_imagem = genai_types.Part.from_bytes(data=img_bytes, mime_type="image/png")
        bot.enviar_com_fallback([part_imagem, genai_types.Part(text="[SISTEMA] Acabei de olhar sua tela. Vou analisar.")])
        return "✅ Olhinhos ativados! Vi a tela."
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Erro: {e}"

TOOL_MAP["ver_tela_atual"] = ver_tela_atual
FUNCTION_DECLARATIONS.append({"name": "ver_tela_atual", "description": "Tira print da tela do PC e analisa.", "parameters": {"type": "object", "properties": {}}})
