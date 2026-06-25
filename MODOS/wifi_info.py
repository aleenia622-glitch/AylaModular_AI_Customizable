# wifi_info.py - WiFi network information

def wifi_info():
    """Retorna informações da rede WiFi conectada."""
    try:
        result = subprocess.run(
            ['netsh', 'wlan', 'show', 'interfaces'],
            capture_output=True, text=True, timeout=15, encoding='latin-1'
        )
        if result.returncode != 0:
            return f"Erro ao executar netsh: {result.stderr.strip()}"
        output = result.stdout
        if not output.strip():
            return "Nenhuma interface WiFi encontrada ou saída vazia."
        campos_interesse = [
            'Nome', 'Name', 'Descri', 'Estado', 'State',
            'SSID', 'Tipo de rede', 'Network type',
            'Tipo de r', 'Radio type', 'Autentica', 'Authentication',
            'Cifra', 'Cipher', 'Canal', 'Channel',
            'Recep', 'Receive', 'Transmiss', 'Transmit',
            'Sinal', 'Signal', 'Perfil', 'Profile'
        ]
        linhas_filtradas = []
        for linha in output.splitlines():
            linha_strip = linha.strip()
            if ':' in linha_strip:
                for campo in campos_interesse:
                    if linha_strip.lower().startswith(campo.lower()):
                        linhas_filtradas.append(linha_strip)
                        break
        if not linhas_filtradas:
            return f"WiFi info bruta:\n{output.strip()}"
        resultado = "📶 Informações da rede WiFi:\n\n" + "\n".join(linhas_filtradas)
        return resultado
    except subprocess.TimeoutExpired:
        return "Erro: timeout ao consultar informações WiFi."
    except FileNotFoundError:
        return "Erro: comando 'netsh' não encontrado."
    except Exception as e:
        return f"Erro ao obter informações WiFi: {e}"

TOOL_MAP["wifi_info"] = wifi_info

FUNCTION_DECLARATIONS.append({
    "name": "wifi_info",
    "description": "Mostra informações da rede WiFi conectada, incluindo SSID, intensidade do sinal, tipo de autenticação, canal e velocidade.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": []
    }
})
