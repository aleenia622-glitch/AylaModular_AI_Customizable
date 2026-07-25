import winsound
import time
import threading

if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

def _tocar_melodia(notas):
    for frequencia, duracao in notas:
        if frequencia == 0:
            time.sleep(duracao / 1000.0)
        else:
            winsound.Beep(frequencia, duracao)

def tocar_sfx(tipo: str) -> str:
    """
    Toca um efeito sonoro fofo usando o beeper do Windows em uma thread.
    """
    tipo = tipo.lower().strip()
    
    # Cada tipo tem um padrão de (Frequência, Duração_em_ms)
    melodias = {
        "sucesso": [(880, 100), (988, 100), (1047, 200)], # La, Si, Do
        "erro": [(300, 150), (250, 250)], # Tom caindo, triste
        "poing": [(700, 100), (900, 100), (1100, 150)], # Som pulando
        "magia": [(523, 100), (659, 100), (784, 100), (1047, 300)], # Arpejo mágico (Do, Mi, Sol, Do alta)
        "alerta": [(800, 100), (0, 100), (800, 100)] # Bip bip
    }
    
    if tipo not in melodias:
        # Tenta tocar um som padrão do Windows como fallback
        winsound.MessageBeep(winsound.MB_OK)
        return "Tocado som padrão do sistema."
    
    # Roda numa thread separada pra não travar a Ayla enquanto o som toca
    notas = melodias[tipo]
    t = threading.Thread(target=_tocar_melodia, args=(notas,), daemon=True)
    t.start()
    
    return f"🎵 Toquei o efeito sonoro de '{tipo}' com sucesso no fone do(a) usuário(a)!"

TOOL_MAP["tocar_sfx"] = tocar_sfx

FUNCTION_DECLARATIONS.append({
    "name": "tocar_sfx",
    "description": "Toca um efeito sonoro fofo e curtinho no fone/caixa de som do PC do(a) usuário(a). Ótimo para usar quando você terminar de gerar uma imagem, avisar algo importante ou fizer um barulhinho de erro fofo.",
    "parameters": {
        "type": "object",
        "properties": {
            "tipo": {
                "type": "string",
                "enum": ["sucesso", "erro", "poing", "magia", "alerta"],
                "description": "O tipo do efeito sonoro que você quer tocar."
            }
        },
        "required": ["tipo"]
    }
})
