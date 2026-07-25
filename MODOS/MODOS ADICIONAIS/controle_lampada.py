# -*- coding: utf-8 -*-
import socket
import time
import json
import colorsys
import threading
from pathlib import Path

# Constantes do protocolo CozyLife
CMD_INFO = 0
CMD_QUERY = 2
CMD_SET = 3

# Dicionário de cores em português para Matiz (Hue) e Saturação (0 a 1000)
CORES_PORTUGUES = {
    "vermelho": (0, 1000),
    "verde": (120, 1000),
    "azul": (240, 1000),
    "amarelo": (60, 1000),
    "ciano": (180, 1000),
    "magenta": (300, 1000),
    "rosa": (320, 800),
    "roxo": (270, 1000),
    "laranja": (30, 1000),
    "branco": (0, 0),      # Saturação zero = luz branca
    "quente": (0, 0),       # Tratado separadamente na temperatura
    "fria": (0, 0)          # Tratado separadamente na temperatura
}

# Caminho das configurações para salvar o IP
BASE_DIR = Path(__file__).resolve().parent.parent
SETTINGS_PATH = BASE_DIR / "ayla_settings.json"

def carregar_ip_settings() -> str:
    try:
        if SETTINGS_PATH.exists():
            dados = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            return dados.get("cozylife_bulb_ip", "")
    except Exception:
        pass
    return ""

def salvar_ip_settings(ip: str):
    try:
        if SETTINGS_PATH.exists():
            dados = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            dados["cozylife_bulb_ip"] = ip
            SETTINGS_PATH.write_text(json.dumps(dados, indent=4, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

def get_local_subnet():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Tenta se conectar a um IP qualquer para obter a interface local ativa
        s.connect(('10.255.255.255', 1))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = '127.0.0.1'
    finally:
        s.close()
    
    if local_ip == '127.0.0.1':
        return []
    
    parts = local_ip.split('.')
    if len(parts) == 4:
        base = f"{parts[0]}.{parts[1]}.{parts[2]}."
        return [f"{base}{i}" for i in range(1, 255)]
    return []

def scan_ip(ip, found_devices):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            s.connect((ip, 5555))
            sn = str(int(time.time() * 1000))
            msg = {
                "pv": 0,
                "cmd": CMD_INFO,
                "sn": sn,
                "msg": {}
            }
            s.sendall(json.dumps(msg).encode('utf-8') + b"\r\n")
            resp = s.recv(1024)
            data = json.loads(resp.decode('utf-8').strip())
            if data and data.get("res") == 0 and "msg" in data:
                found_devices.append({
                    "ip": ip,
                    "did": data["msg"].get("did", ""),
                    "mac": data["msg"].get("mac", ""),
                    "pid": data["msg"].get("pid", ""),
                    "dmn": data["msg"].get("dmn", "Lâmpada CozyLife")
                })
    except Exception:
        pass

def discover_cozylife_bulbs() -> list:
    ips = get_local_subnet()
    if not ips:
        return []
    found = []
    threads = []
    for ip in ips:
        t = threading.Thread(target=scan_ip, args=(ip, found))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    return found

def send_cozylife_payload(ip: str, cmd: int, payload: dict) -> dict:
    sn = str(int(time.time() * 1000))
    if cmd == CMD_SET:
        message = {
            'pv': 0,
            'cmd': cmd,
            'sn': sn,
            'msg': {
                'attr': [int(item) for item in payload.keys()],
                'data': payload,
            }
        }
    elif cmd == CMD_QUERY:
        message = {
            'pv': 0,
            'cmd': cmd,
            'sn': sn,
            'msg': {
                'attr': [0],
            }
        }
    else:
        return None

    message_str = json.dumps(message, separators=(',', ':',)) + "\r\n"
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(2.0)
        s.connect((ip, 5555))
        s.sendall(message_str.encode('utf-8'))
        
        # Espera pelo sn correspondente
        for _ in range(5):
            resp = s.recv(1024)
            if not resp:
                break
            resp_str = resp.decode('utf-8', errors='ignore')
            if sn in resp_str:
                try:
                    resp_json = json.loads(resp_str.strip())
                    if resp_json.get('msg') and isinstance(resp_json['msg'], dict):
                        return resp_json['msg'].get('data')
                except Exception:
                    pass
    return None

def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    hex_str = hex_str.lstrip('#').strip()
    if len(hex_str) == 3:
        hex_str = ''.join([c*2 for c in hex_str])
    if len(hex_str) == 6:
        return int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)
    raise ValueError("Formato HEX inválido. Use algo como #FF00FF ou 00FFCC.")

def rgb_to_hs(r: int, g: int, b: int) -> tuple[int, int]:
    r_n, g_n, b_n = r / 255.0, g / 255.0, b / 255.0
    h, s, v = colorsys.rgb_to_hsv(r_n, g_n, b_n)
    hue = round(h * 360.0)
    sat = round(s * 1000.0)
    return hue, sat

def controle_lampada(
    acao: str,
    ip: str = "",
    brilho: int = None,
    cor_nome: str = "",
    cor_hex: str = "",
    temperatura: int = None,
    matiz: int = None,
    saturacao: int = None
) -> str:
    try:
        acao = acao.lower().strip()
        
        # Resolvendo o IP
        if not ip:
            ip = carregar_ip_settings()
        
        if not ip and acao != "descobrir":
            # Auto-descoberta caso nenhum IP seja fornecido
            dispositivos = discover_cozylife_bulbs()
            if not dispositivos:
                return "❌ Nenhuma lâmpada CozyLife foi encontrada na rede local automaticamente. Por favor, forneça o IP manualmente."
            elif len(dispositivos) > 1:
                lista_ips = ", ".join([f"{d['ip']} ({d['dmn']})" for d in dispositivos])
                return f"⚠️ Encontrei múltiplas lâmpadas na rede: {lista_ips}. Por favor, configure o IP de uma delas."
            else:
                ip = dispositivos[0]["ip"]
                salvar_ip_settings(ip)
        
        if acao == "descobrir":
            dispositivos = discover_cozylife_bulbs()
            if not dispositivos:
                return "🔍 Nenhuma lâmpada CozyLife encontrada na rede local."
            res = "🔍 Lâmpadas CozyLife encontradas:\n"
            for d in dispositivos:
                res += f"- IP: {d['ip']} | Modelo: {d['dmn']} | ID: {d['did']}\n"
            return res.strip()
            
        if acao == "configurar":
            if not ip:
                return "❌ Por favor, especifique o IP para configurar."
            salvar_ip_settings(ip)
            return f"✅ IP da lâmpada configurado com sucesso para: {ip}"
            
        if acao == "desligar":
            send_cozylife_payload(ip, CMD_SET, {'1': 0})
            return "✅ Lâmpada desligada com sucesso."

        # Para ações que envolvem ligar ou mudar estado
        payload = {'1': 255, '2': 0}
        detalhes = []
        
        # Ajustes de cor por HEX
        if cor_hex:
            r, g, b = hex_to_rgb(cor_hex)
            h, s = rgb_to_hs(r, g, b)
            payload['5'] = h
            payload['6'] = s
            detalhes.append(f"cor HEX: {cor_hex} (Matiz: {h}, Saturação: {s/10}%)")
        
        # Ajustes de cor por nome em português
        elif cor_nome:
            cor_nome = cor_nome.lower().strip()
            if cor_nome in CORES_PORTUGUES:
                h, s = CORES_PORTUGUES[cor_nome]
                payload['5'] = h
                payload['6'] = s
                detalhes.append(f"cor: {cor_nome}")
                
                # Se pedir "quente", "fria" ou "branco"
                if cor_nome == "quente":
                    payload['3'] = 0
                    detalhes.append("temperatura: quente (0)")
                elif cor_nome == "fria":
                    payload['3'] = 1000
                    detalhes.append("temperatura: fria (1000)")
            else:
                return f"❌ Cor '{cor_nome}' não reconhecida. Cores válidas: vermelho, verde, azul, amarelo, ciano, magenta, rosa, roxo, laranja, branco, quente, fria."
                
        # Ajustes brutos de matiz e saturação
        if matiz is not None:
            payload['5'] = matiz
            detalhes.append(f"matiz: {matiz}")
        if saturacao is not None:
            # Converte escala 0-100 para 0-1000 do protocolo
            payload['6'] = saturacao * 10
            detalhes.append(f"saturação: {saturacao}%")
            
        # Ajuste de brilho (escala 0-100 para 0-1000)
        if brilho is not None:
            payload['4'] = brilho * 10
            detalhes.append(f"brilho: {brilho}%")
            
        # Ajuste de temperatura de cor (escala 0-100 para 0-1000)
        if temperatura is not None:
            payload['3'] = temperatura * 10
            detalhes.append(f"temperatura: {temperatura}%")

        if acao == "ligar" or detalhes:
            send_cozylife_payload(ip, CMD_SET, payload)
            desc_detalhes = ", ".join(detalhes) if detalhes else "com configurações atuais"
            return f"✅ Lâmpada ligada/atualizada: {desc_detalhes}."
            
        if acao == "status":
            estado = send_cozylife_payload(ip, CMD_QUERY, {})
            if not estado:
                return "❌ Não foi possível obter o status da lâmpada."
            
            ligado = "Ligada" if estado.get('1', 0) > 0 else "Desligada"
            brilho_atual = int(estado.get('4', 0) / 10)
            temp_atual = int(estado.get('3', 0) / 10)
            matiz_atual = estado.get('5', 0)
            sat_atual = int(estado.get('6', 0) / 10)
            
            return (
                f"💡 **Status da Lâmpada ({ip})**:\n"
                f"- Estado: **{ligado}**\n"
                f"- Brilho: **{brilho_atual}%**\n"
                f"- Temperatura de Cor: **{temp_atual}%** (0=Quente, 100=Fria)\n"
                f"- Matiz (Hue): **{matiz_atual}**\n"
                f"- Saturação: **{sat_atual}%**"
            )
            
    except Exception as e:
        return f"❌ Erro ao controlar a lâmpada: {e}"

TOOL_MAP["controle_lampada"] = controle_lampada
FUNCTION_DECLARATIONS.append({
    "name": "controle_lampada",
    "description": "Controla uma lâmpada inteligente CozyLife local (liga/desliga, altera cor por nome/HEX, brilho e temperatura de cor). Se o IP não for fornecido, a ferramenta tentará descobrir automaticamente na rede local.",
    "parameters": {
        "type": "object",
        "properties": {
            "acao": {
                "type": "string",
                "enum": ["ligar", "desligar", "status", "descobrir", "configurar"],
                "description": "Ação a ser executada: ligar, desligar, status, descobrir (escanear rede) ou configurar (salvar IP)."
            },
            "ip": {
                "type": "string",
                "description": "Opcional. Endereço IP da lâmpada. Se omitido, busca no cache ou escaneia a rede."
            },
            "brilho": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "description": "Opcional. Brilho da lâmpada em porcentagem (1 a 100)."
            },
            "cor_nome": {
                "type": "string",
                "description": "Opcional. Nome da cor em português (ex: azul, vermelho, verde, amarelo, rosa, roxo, laranja, ciano, branco, quente, fria)."
            },
            "cor_hex": {
                "type": "string",
                "description": "Opcional. Código da cor em formato hexadecimal (ex: #FF00FF ou FF0000)."
            },
            "temperatura": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "Opcional. Temperatura de cor branca em porcentagem (0 = luz mais quente/amarela, 100 = luz mais fria/branca)."
            },
            "matiz": {
                "type": "integer",
                "minimum": 0,
                "maximum": 360,
                "description": "Opcional. Matiz bruto (Hue) de 0 a 360."
            },
            "saturacao": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "Opcional. Saturação bruta de 0 a 100."
            }
        },
        "required": ["acao"]
    }
})
