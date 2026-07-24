# ══════════════════════════════════════════════════════════
#  AGENTE WINDOW — Terminal Visual do Modo Agente da Ayla
# ══════════════════════════════════════════════════════════

import sys
import socket
import json
import time
import os

# Configurar encoding UTF-8 no stdout/stderr do Python no Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

if sys.platform == "win32":
    os.system("")

# Cores ANSI
RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BLUE = "\033[94m"
GRAY = "\033[90m"

BANNER = f"""{CYAN}{BOLD}
══════════════════════════════════════════════════════════════════
  🤖 AYLA CODE AGENT — MODO AGENTE DE CÓDIGO INTERATIVO
  Sessão Ativa | Conectado ao Core da Ayla
══════════════════════════════════════════════════════════════════
{RESET}"""

def main():
    port = 49152
    for i, arg in enumerate(sys.argv):
        if arg == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])

    print(BANNER)
    print(f"{GRAY}[Janela] Conectando ao servidor do agente na porta {port}...{RESET}")

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tentativas = 0
    while tentativas < 30:
        try:
            s.connect(("127.0.0.1", port))
            break
        except Exception:
            time.sleep(0.3)
            tentativas += 1

    if tentativas >= 30:
        print(f"{RED}[Erro] Nao foi possivel conectar ao servidor do agente na porta {port}.{RESET}")
        time.sleep(3)
        return

    print(f"{GREEN}[Janela] Conectado com sucesso! Aguardando tarefas da Ayla...{RESET}\n")

    buffer = ""
    try:
        while True:
            data = s.recv(4096)
            if not data:
                print(f"{YELLOW}\n[Janela] Conexão encerrada pelo servidor.{RESET}")
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
                        print(f"{GRAY}[Status] {msg}{RESET}")

                    elif tipo == "prompt":
                        prompt = evento.get("text", "")
                        print(f"\n{CYAN}{BOLD}══════════════════════════════════════════════════════════════════{RESET}")
                        print(f"{CYAN}{BOLD}📩 DA AYLA:{RESET} {prompt}")
                        print(f"{CYAN}{BOLD}══════════════════════════════════════════════════════════════════{RESET}\n")

                    elif tipo == "model_start":
                        modelo = evento.get("model", "")
                        print(f"{MAGENTA}🧠 [Agente] Processando com modelo {BOLD}{modelo}{RESET}{MAGENTA}...{RESET}")

                    elif tipo == "tool_call":
                        nome = evento.get("name", "")
                        args = evento.get("args", {})
                        args_str = json.dumps(args, ensure_ascii=False)
                        if len(args_str) > 120:
                            args_str = args_str[:117] + "..."
                        print(f"{YELLOW}🛠️  [Ferramenta] {BOLD}{nome}{RESET}{YELLOW} -> {args_str}{RESET}")

                    elif tipo == "tool_result":
                        nome = evento.get("name", "")
                        res = evento.get("result", "")
                        res_preview = res.replace("\n", " ")
                        if len(res_preview) > 150:
                            res_preview = res_preview[:147] + "..."
                        print(f"{GRAY}   └─ Resposta ({nome}): {res_preview}{RESET}")

                    elif tipo == "response":
                        resp = evento.get("text", "")
                        modelo = evento.get("model", "Gemini")
                        print(f"\n{GREEN}{BOLD}💬 RESPOSTA DO AGENTE ({modelo}):{RESET}")
                        print(f"{GREEN}{resp}{RESET}\n")
                        print(f"{GRAY}🟢 [Modo Agente Mantido ATIVO — Aguardando proxima mensagem da Ayla]{RESET}\n")

                    elif tipo == "close":
                        msg = evento.get("text", "Sessao encerrada.")
                        print(f"\n{RED}{BOLD}🔒 [Sessão Encerrada]{RESET} {msg}")
                        print(f"{GRAY}Fechando janela em 3 segundos...{RESET}")
                        time.sleep(3)
                        return

                except Exception as e:
                    print(f"{GRAY}[Log] {line}{RESET}")

    except KeyboardInterrupt:
        print(f"\n{YELLOW}[Janela] Encerrada pelo usuario.{RESET}")
    except Exception as e:
        print(f"\n{RED}[Janela] Erro de conexao: {e}{RESET}")
    finally:
        s.close()

if __name__ == "__main__":
    main()
