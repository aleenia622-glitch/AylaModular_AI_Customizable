"""
Módulo de interface e gerenciamento de janela do Google Antigravity CLI — Modo Layka Antigravity 🐾.
"""
# ══════════════════════════════════════════════════════════
#  ANTIGRAVITY WINDOW — Terminal Visual Bonito do Layka Antigravity (agy) 🐾
#  Visual idêntico ao Antigravity CLI oficial com logotipo pixel-art arco-íris
# ══════════════════════════════════════════════════════════

import sys
import socket
import json
import time
import os

# Configurar encoding UTF-8 no stdout/stderr no Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if sys.platform == "win32":
    os.system("")

# Estilos e Cores ANSI (TrueColor / 256 Cores)
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"

# Paleta Arco-Íris do Antigravity
ORANGE = "\033[38;2;255;130;45m"
YELLOW = "\033[38;2;255;190;40m"
PINK   = "\033[38;2;240;95;170m"
PURPLE = "\033[38;2;160;90;245m"
BLUE   = "\033[38;2;75;140;255m"
CYAN   = "\033[38;2;45;210;255m"
GREEN  = "\033[38;2;50;215;130m"
WHITE  = "\033[38;2;245;245;250m"
GRAY   = "\033[38;2;130;140;160m"
DARK_GRAY = "\033[38;2;70;75;90m"

# Logotipo Pixel-Art Arco-Íris idêntico ao Google Antigravity CLI oficial
RAINBOW_LOGO = f"""
  {ORANGE}▄{RESET}
 {ORANGE}▄{YELLOW}█{PINK}▄{RESET}
{YELLOW}▄{PINK}█{PURPLE}█{BLUE}█{RESET}
{PINK}█{PURPLE}█{RESET} {BLUE}█{CYAN}█{RESET}
{PURPLE}█{BLUE}▀{RESET}   {CYAN}▀{CYAN}█{RESET}
"""

BANNER = f"""{RAINBOW_LOGO}
{WHITE}{BOLD}Welcome to {PINK}Layka Antigravity CLI{WHITE} (Ayla & Layka Integration Agent) 🐾.{RESET}
{GRAY}Connecting to Ayla & Layka Agent Server...{RESET}
"""

def main():
    port = 49153
    for i, arg in enumerate(sys.argv):
        if arg == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])

    print(BANNER)

    while True:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tentativas = 0
        while tentativas < 60:
            try:
                s.connect(("127.0.0.1", port))
                break
            except Exception:
                time.sleep(0.5)
                tentativas += 1

        if tentativas >= 60:
            print(f"{PINK}[Erro] Não foi possível conectar ao servidor do Layka Antigravity na porta {port}.{RESET}")
            time.sleep(3)
            return

        print(f"{GREEN}✔ Connected! Ayla, Layka & Google Antigravity CLI active session ready. 🐾{RESET}\n")
        print(f"{DARK_GRAY}{'─' * 66}{RESET}\n")

        buffer = ""
        try:
            while True:
                data = s.recv(4096)
                if not data:
                    print(f"\n{YELLOW}⠋ Conexão encerrada pelo servidor. Aguardando nova instrução...{RESET}\n")
                    break

                buffer += data.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        evento = json.loads(line)
                        tipo = evento.get("type", "")

                        if tipo == "status":
                            msg = evento.get("text", "")
                            print(f"{CYAN}⠋ Status:{RESET} {msg}")

                        elif tipo == "prompt":
                            prompt = evento.get("text", "")
                            print(f"\n{BLUE}╭── 💬 DA AYLA & LAYKA ──────────────────────────────────────────╮{RESET}")
                            print(f"{WHITE}│ {BOLD}{prompt}{RESET}")
                            print(f"{BLUE}╰────────────────────────────────────────────────────────────────╯{RESET}\n")

                        elif tipo == "model_start":
                            modelo = evento.get("model", "Layka Antigravity Agent")
                            print(f"{PURPLE}⠋ Processing with {BOLD}{modelo}{RESET}{PURPLE}...{RESET}")

                        elif tipo == "tool_call":
                            nome = evento.get("name", "")
                            args = evento.get("args", {})
                            args_str = json.dumps(args, ensure_ascii=False)
                            if len(args_str) > 100:
                                args_str = args_str[:97] + "..."
                            print(f"{YELLOW}🛠️  Executing tool {BOLD}{nome}{RESET}{YELLOW} -> {args_str}{RESET}")

                        elif tipo == "tool_result":
                            nome = evento.get("name", "")
                            res = evento.get("result", "")
                            res_preview = str(res).replace("\n", " ")
                            if len(res_preview) > 130:
                                res_preview = res_preview[:127] + "..."
                            print(f"{GRAY}   └─ Result ({nome}): {res_preview}{RESET}")

                        elif tipo == "response":
                            resp = evento.get("text", "")
                            modelo = evento.get("model", "Layka Antigravity AGY")
                            print(f"\n{GREEN}╭── 🐾 LAYKA ANTIGRAVITY CLI ({modelo}) ────────────────────────────╮{RESET}")
                            print(f"{WHITE}{resp}{RESET}")
                            print(f"{GREEN}╰────────────────────────────────────────────────────────────────╯{RESET}\n")
                            print(f"{CYAN}⠋ Session active — awaiting next instruction...{RESET}\n")

                        elif tipo == "close":
                            msg = evento.get("text", "Session closed.")
                            print(f"\n{PINK}🔒 [Session Closed]{RESET} {msg}")
                            print(f"{GRAY}Closing window in 3 seconds...{RESET}")
                            time.sleep(3)
                            return

                    except Exception as e:
                        print(f"{GRAY}[Log] {line}{RESET}")

        except KeyboardInterrupt:
            print(f"\n{YELLOW}⠋ Session terminated by user.{RESET}")
            break
        except Exception as e:
            print(f"\n{PINK}Connection error: {e}{RESET}")
        finally:
            s.close()

        time.sleep(0.5)

if __name__ == "__main__":
    main()
