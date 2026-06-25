CONFIRMACAO_DESTRUTIVA = "SIM, tenho certeza"

def deletar_arquivo(caminho: str, confirmar: str = "") -> str:
    try:
        if (confirmar or "").strip() != CONFIRMACAO_DESTRUTIVA:
            return (
                "⚠️ Apagar arquivos é uma ação sensível. "
                f"Para continuar, chame a ferramenta com confirmar='{CONFIRMACAO_DESTRUTIVA}'."
            )
        p = Path(caminho).expanduser().resolve()
        if not p.exists(): return f"Não encontrado: {p}"
        if SEND2TRASH_OK:
            send2trash(str(p))
            return f"✅ Enviado para Lixeira: {p}"
        if p.is_dir(): shutil.rmtree(str(p))
        else: p.unlink()
        return f"⚠️ Deletado PERMANENTEMENTE: {p}"
    except Exception as e: return f"Erro: {e}"

TOOL_MAP["deletar_arquivo"] = deletar_arquivo
FUNCTION_DECLARATIONS.append({
    "name": "deletar_arquivo",
    "description": "Envia arquivo/pasta para a Lixeira. Ação sensível: só executa com confirmação literal.",
    "parameters": {
        "type": "object",
        "properties": {
            "caminho": {"type": "string"},
            "confirmar": {
                "type": "string",
                "description": "Obrigatório para executar: SIM, tenho certeza"
            }
        },
        "required": ["caminho", "confirmar"]
    }
})
