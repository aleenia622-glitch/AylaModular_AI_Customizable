
def diario_ayla(acao, entrada=None):
    """Diário pessoal da Ayla com suporte a escrita, leitura e listagem."""
    try:
        caminho_diario = Path(__file__).resolve().parent.parent / "Ayla_Diario.json"
        caminho_diario.parent.mkdir(parents=True, exist_ok=True)

        if caminho_diario.exists():
            with open(caminho_diario, 'r', encoding='utf-8') as f:
                diario = json.load(f)
        else:
            diario = {"entradas": []}

        acao = acao.lower().strip()

        if acao == "escrever":
            if not entrada or not entrada.strip():
                return "✏️ Preciso de algo para escrever no diário! Passe o texto no parâmetro 'entrada'."

            agora = datetime.datetime.now()
            nova_entrada = {
                "data": agora.strftime("%d/%m/%Y"),
                "hora": agora.strftime("%H:%M:%S"),
                "timestamp": agora.isoformat(),
                "texto": entrada.strip()
            }
            diario["entradas"].append(nova_entrada)

            with open(caminho_diario, 'w', encoding='utf-8') as f:
                json.dump(diario, f, ensure_ascii=False, indent=2)

            return (
                f"📖 Entrada adicionada ao diário!\n"
                f"📅 Data: {nova_entrada['data']} às {nova_entrada['hora']}\n"
                f"✍️ \"{entrada.strip()[:100]}{'...' if len(entrada.strip()) > 100 else ''}\"\n"
                f"📊 Total de entradas: {len(diario['entradas'])}"
            )

        elif acao == "ler":
            if not diario["entradas"]:
                return "📖 O diário está vazio. Nenhuma entrada ainda!"

            if entrada and entrada.strip():
                data_busca = entrada.strip()
                encontradas = [e for e in diario["entradas"] if e["data"] == data_busca]
                if not encontradas:
                    return f"📖 Nenhuma entrada encontrada para a data '{data_busca}'."
                resultado = f"📖 **Entradas de {data_busca}** ({len(encontradas)} entrada(s)):\n\n"
                for i, e in enumerate(encontradas, 1):
                    resultado += f"🔹 **{e['hora']}**: {e['texto']}\n\n"
                return resultado
            else:
                ultimas = diario["entradas"][-5:]
                resultado = f"📖 **Últimas {len(ultimas)} entradas do diário:**\n\n"
                for e in ultimas:
                    resultado += f"🔹 **{e['data']} {e['hora']}**: {e['texto']}\n\n"
                return resultado

        elif acao == "listar":
            if not diario["entradas"]:
                return "📖 O diário está vazio. Nenhuma entrada ainda!"

            datas = {}
            for e in diario["entradas"]:
                data = e["data"]
                datas[data] = datas.get(data, 0) + 1

            resultado = f"📅 **Datas com entradas no diário** ({len(diario['entradas'])} total):\n\n"
            for data, qtd in sorted(datas.items(), key=lambda x: datetime.datetime.strptime(x[0], "%d/%m/%Y"), reverse=True):
                resultado += f"  📌 {data} — {qtd} entrada(s)\n"
            return resultado

        else:
            return "⚠️ Ação inválida. Use 'escrever', 'ler' ou 'listar'."

    except Exception as e:
        return f"❌ Erro no diário: {e}"

TOOL_MAP["diario_ayla"] = diario_ayla

FUNCTION_DECLARATIONS.append({
    "name": "diario_ayla",
    "description": "Diário pessoal da Ayla. Permite escrever novas entradas, ler entradas por data ou listar todas as datas com entradas.",
    "parameters": {
        "type": "object",
        "properties": {
            "acao": {
                "type": "string",
                "description": "Ação a executar: 'escrever' (nova entrada), 'ler' (ler entradas, opcionalmente por data), 'listar' (listar datas).",
                "enum": ["escrever", "ler", "listar"]
            },
            "entrada": {
                "type": "string",
                "description": "Texto da entrada (para 'escrever') ou data no formato DD/MM/YYYY (para 'ler'). Opcional para 'listar'."
            }
        },
        "required": ["acao"]
    }
})
