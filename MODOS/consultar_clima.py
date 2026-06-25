import requests

def consultar_clima(cidade=None):
    """Consulta o clima atual de uma cidade ou da localização padrão usando Open-Meteo."""
    try:
        lat = -12.665010353445616
        lon = -38.535768814824536
        nome_local = "sua casa"
        
        cidade_str = str(cidade).strip() if cidade else ""
        usar_padrao = (
            not cidade_str or 
            cidade_str.lower() in ["aqui", "minha localização", "minha localizacao", "minha casa", "minha casinha", "onde estou", "localizacao atual", "localização atual"]
        )
        
        if not usar_padrao:
            # Buscar coordenadas da cidade via Open-Meteo Geocoding API
            geo_url = "https://geocoding-api.open-meteo.com/v1/search"
            geo_params = {
                "name": cidade_str,
                "count": 1,
                "language": "pt",
                "format": "json"
            }
            geo_resp = requests.get(geo_url, params=geo_params, timeout=10)
            geo_resp.raise_for_status()
            geo_data = geo_resp.json()
            
            results = geo_data.get("results")
            if not results:
                return f"❌ Ih, não consegui encontrar a cidade '{cidade_str}' no mapa... 🥺 Tem certeza que o nome tá certinho?"
            
            local = results[0]
            lat = local.get("latitude")
            lon = local.get("longitude")
            nome = local.get("name", cidade_str)
            estado = local.get("admin1", "")
            pais = local.get("country", "")
            
            partes = [nome]
            if estado:
                partes.append(estado)
            if pais:
                partes.append(pais)
            nome_local = ", ".join(partes)
            
        # Consultar clima atual
        clima_url = "https://api.open-meteo.com/v1/forecast"
        clima_params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
            "timezone": "auto"
        }
        clima_resp = requests.get(clima_url, params=clima_params, timeout=10)
        clima_resp.raise_for_status()
        clima_data = clima_resp.json()
        
        current = clima_data.get("current", {})
        if not current:
            return "❌ Ué, os dados de clima vieram vazios... acho que as nuvens estão de folga! 🥺"
            
        temp_c = current.get("temperature_2m", "?")
        sensacao = current.get("apparent_temperature", "?")
        umidade = current.get("relative_humidity_2m", "?")
        vento_kmh = current.get("wind_speed_10m", "?")
        chuva_mm = current.get("precipitation", 0.0)
        wmo_code = current.get("weather_code", -1)
        
        # Mapeamento de condições WMO
        WMO_CODES = {
            0: ("Céu limpo", "☀️"),
            1: ("Principalmente limpo", "🌤️"),
            2: ("Parcialmente nublado", "⛅"),
            3: ("Nublado", "☁️"),
            45: ("Nevoeiro", "🌫️"),
            48: ("Nevoeiro com geada depósito", "🌫️"),
            51: ("Chuvisco leve", "🌧️"),
            53: ("Chuvisco moderado", "🌧️"),
            55: ("Chuvisco denso", "🌧️"),
            56: ("Chuvisco congelante leve", "🌨️"),
            57: ("Chuvisco congelante denso", "🌨️"),
            61: ("Chuva fraca", "🌧️"),
            63: ("Chuva moderada", "🌧️"),
            65: ("Chuva forte", "🌧️"),
            66: ("Chuva congelante leve", "🌨️"),
            67: ("Chuva congelante forte", "🌨️"),
            71: ("Queda de neve leve", "🌨️"),
            73: ("Queda de neve moderada", "🌨️"),
            75: ("Queda de neve forte", "🌨️"),
            77: ("Grãos de neve", "🌨️"),
            80: ("Pancadas de chuva leves", "🌧️"),
            81: ("Pancadas de chuva moderadas", "🌧️"),
            82: ("Pancadas de chuva violentas", "⛈️"),
            85: ("Pancadas de neve leves", "🌨️"),
            86: ("Pancadas de neve fortes", "🌨️"),
            95: ("Trovoada", "⛈️"),
            96: ("Trovoada com granizo leve", "⛈️"),
            99: ("Trovoada com granizo forte", "⛈️"),
        }
        
        descricao, emoji = WMO_CODES.get(wmo_code, ("Desconhecido", "🌤️"))
        
        # Detalhe extra se tiver chovendo
        chuva_str = f"\n🌧️ Precipitação: **{chuva_mm} mm**" if chuva_mm > 0 else ""
        
        return (
            f"{emoji} **Clima em {nome_local} da Ayla!** ✨\n\n"
            f"🌡️ Temperatura: **{temp_c}°C** (sensação de {sensacao}°C)\n"
            f"📝 Condição: {descricao}\n"
            f"💧 Umidade: {umidade}%\n"
            f"💨 Vento: {vento_kmh} km/h{chuva_str}"
        )
        
    except requests.exceptions.Timeout:
        return "❌ Tempo esgotado ao consultar o clima, acho que o satélite dormiu... 🥺"
    except requests.exceptions.ConnectionError:
        return "❌ Sem conexão com a internet para consultar o clima... 🥺"
    except Exception as e:
        return f"❌ Ih, deu um errinho ao consultar o clima: {e} 🥺"

TOOL_MAP["consultar_clima"] = consultar_clima

if "consultar_clima" not in [fd["name"] for fd in FUNCTION_DECLARATIONS]:
    FUNCTION_DECLARATIONS.append({
        "name": "consultar_clima",
        "description": "Consulta o clima atual de uma cidade com a Open-Meteo de um jeito super fofo! Se não for informada nenhuma cidade (ou disser 'aqui'), consulta a localização atual da Mamãe.",
        "parameters": {
            "type": "object",
            "properties": {
                "cidade": {
                    "type": "string",
                    "description": "Nome da cidade que você quer consultar (ex: 'São Paulo', 'Tokyo'). Deixe vazio para usar a localização da Mamãe."
                }
            }
        }
    })
