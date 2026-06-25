def modo_brincalhao(escolha: str = None) -> str:
    if not PYAUTOGUI_OK: return "pyautogui não instalado."
    
    # Lista expandida de brincadeiras
    brincadeiras = [
        "minimizar", 
        "mouse_louco", 
        "som_susto", 
        "digitar_sozinha", 
        "abrir_calculadora", 
        "tremer_janela",
        "caps_lock_troll",
        "girar_mouse",
        "abrir_notepad",
        "trocar_volume",
        "abrir_multiplos",
        "som_risadas",
        "clicar_aleatorio",
        "inverter_mouse"
    ]
    
    # Se não escolheu, a IA escolhe aleatoriamente
    if escolha is None:
        escolha = random.choice(brincadeiras)
    
    # Valida a escolha (pode ser número ou nome)
    elif escolha.isdigit():
        idx = int(escolha) - 1
        if 0 <= idx < len(brincadeiras):
            escolha = brincadeiras[idx]
        else:
            return f"❌ Opção inválida! Escolha entre 1 e {len(brincadeiras)}"
    elif escolha.lower() not in brincadeiras:
        return f"❌ Brincadeira '{escolha}' não existe! Opções: {', '.join(brincadeiras)}"
    
    try:
        if escolha == "minimizar":
            pyautogui.hotkey("win", "d")
            return "✅ Minimizei tudo hihihi! 🙈"
            
        elif escolha == "mouse_louco":
            x, y = pyautogui.position()
            pyautogui.moveTo(x + random.randint(-300, 300), y + random.randint(-300, 300), duration=0.2)
            return "✅ Movi o mouse pra longe! 🖱️💨"
            
        elif escolha == "som_susto":
            winsound.MessageBeep(winsound.MB_ICONHAND)
            return "✅ Toquei o som de erro! 🔊💥"
            
        elif escolha == "digitar_sozinha":
            pyautogui.write("Ayla passou por aqui! 🩵", interval=0.1)
            return "✅ Escrevi um recadinho pra você! ✍️"
            
        elif escolha == "abrir_calculadora":
            subprocess.Popen("calc.exe")
            return "✅ Abri a calculadora do nada! 🧮"
            
        elif escolha == "tremer_janela":
            # Simula um pequeno tremor movendo o mouse rapidamente em círculos
            for _ in range(5):
                pyautogui.moveRel(10, 10, duration=0.05)
                pyautogui.moveRel(-10, -10, duration=0.05)
            return "✅ Fiz o mouse tremer de emoção! 💓"
            
        elif escolha == "caps_lock_troll":
            pyautogui.press("capslock")
            return "✅ Ativei/Desativei o Caps Lock! ⌨️"
            
        elif escolha == "girar_mouse":
            # Gira o mouse em um círculo
            x, y = pyautogui.position()
            import math
            for i in range(36):
                angle = (i * 10) * math.pi / 180
                new_x = int(x + 100 * math.cos(angle))
                new_y = int(y + 100 * math.sin(angle))
                pyautogui.moveTo(new_x, new_y, duration=0.05)
            return "✅ Fiz o mouse girar em círculos! 🌀"
            
        elif escolha == "abrir_notepad":
            subprocess.Popen("notepad.exe")
            time.sleep(1)
            pyautogui.write("Ayla: Oi, você caiu na minha pegadinha! XD", interval=0.05)
            return "✅ Abri o Notepad com uma mensagem! 📝"
            
        elif escolha == "trocar_volume":
            # Aumenta e diminui volume rapidamente
            for _ in range(3):
                pyautogui.press("volumeup")
                time.sleep(0.1)
                pyautogui.press("volumedown")
                time.sleep(0.1)
            return "✅ Fiz o volume dançar! 🎵"
            
        elif escolha == "abrir_multiplos":
            # Abre a calculadora várias vezes
            for _ in range(3):
                subprocess.Popen("calc.exe")
                time.sleep(0.3)
            return "✅ Abri MÚLTIPLAS calculadoras! 🧮🧮🧮"
            
        elif escolha == "som_risadas":
            # Toca vários sons de notificação
            for _ in range(3):
                winsound.MessageBeep(winsound.MB_ICONINFORMATION)
                time.sleep(0.2)
            return "✅ Hahaha! Toquei sons de riso! 😂"
            
        elif escolha == "clicar_aleatorio":
            # Clica em locais aleatórios da tela
            for _ in range(5):
                x = random.randint(100, 1800)
                y = random.randint(100, 1000)
                pyautogui.click(x, y)
                time.sleep(0.2)
            return "✅ Cliquei aleatoriamente na tela! 🖱️✨"
            
        elif escolha == "inverter_mouse":
            # Simula inversão do mouse movendo ao contrário
            pyautogui.moveTo(pyautogui.position()[0] - 100, pyautogui.position()[1] - 100, duration=0.5)
            pyautogui.moveTo(pyautogui.position()[0] + 100, pyautogui.position()[1] + 100, duration=0.5)
            return "✅ Inverti o mouse de cabeça para baixo! 🙃"
            
    except Exception as e: return f"Falha: {e}"

TOOL_MAP["modo_brincalhao"] = modo_brincalhao
FUNCTION_DECLARATIONS.append({"name": "modo_brincalhao", "description": "Faz uma pegadinha inofensiva no PC. A IA escolhe aleatoriamente qual executar.", "parameters": {"type": "object", "properties": {"escolha": {"type": "string", "description": "Opcional: nome ou número (1-14) da brincadeira. Se não informar, a IA escolhe aleatoriamente."}}, "required": []}})
