def pesquisar_pokedex(nome_pokemon: str) -> str:
    """
    Pesquisa um Pokémon na PokéAPI e baixa sua fotinho!
    """
    global ULTIMA_IMAGEM_GERADA
    try:
        url = f"https://pokeapi.co/api/v2/pokemon/{nome_pokemon.lower().strip()}"
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return f"❌ Poxa, não encontrei o Pokémon '{nome_pokemon}' na Pokédex!"
        
        data = resp.json()
        nome = data.get("name", nome_pokemon).title()
        tipos = ", ".join([t["type"]["name"].title() for t in data.get("types", [])])
        habilidades = ", ".join([h["ability"]["name"].title() for h in data.get("abilities", [])])
        peso = data.get("weight", 0) / 10
        altura = data.get("height", 0) / 10
        
        sprite_url = data.get("sprites", {}).get("other", {}).get("official-artwork", {}).get("front_default")
        if not sprite_url:
            sprite_url = data.get("sprites", {}).get("front_default")
            
        if sprite_url:
            img_resp = requests.get(sprite_url, timeout=10)
            if img_resp.status_code == 200:
                projeto_raiz = Path(__file__).resolve().parent.parent
                PASTA_AYLA = projeto_raiz / "Aylafotitos"
                PASTA_AYLA.mkdir(parents=True, exist_ok=True)
                from datetime import datetime as dt
                caminho = str(PASTA_AYLA / f"pokemon_{nome}_{dt.now().strftime('%Y%m%d_%H%M%S')}.png")
                with open(caminho, "wb") as f:
                    f.write(img_resp.content)
                ULTIMA_IMAGEM_GERADA = caminho
        
        info = (
            f"Pokédex - {nome}\\n"
            f"Tipos: {tipos}\\n"
            f"Habilidades: {habilidades}\\n"
            f"Altura: {altura}m | Peso: {peso}kg"
        )
        return f"✅ Achei o {nome}! Aqui estão as informações (Gere uma mensagem bem fofinha com elas e avise que você mandou a fotinho dele!):\\n{info}"
    except Exception as e:
        return f"Erro ao consultar a Pokédex: {e}"

TOOL_MAP["pesquisar_pokedex"] = pesquisar_pokedex
if "pesquisar_pokedex" not in [fd["name"] for fd in FUNCTION_DECLARATIONS]:
    FUNCTION_DECLARATIONS.append({
        "name": "pesquisar_pokedex", 
        "description": "Pesquisa um Pokémon na Pokédex usando a PokéAPI. Retorna informações e baixa a fotinho dele para mandar no Discord. Use isso quando pedirem para pesquisar um Pokémon na Pokédex.", 
        "parameters": {
            "type": "object", 
            "properties": {
                "nome_pokemon": {"type": "string", "description": "Nome do Pokémon (em inglês) para pesquisar"}
            }, 
            "required": ["nome_pokemon"]
        }
    })
