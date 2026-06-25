def copiar_arquivo(origem: str, destino: str) -> str:
    try:
        src, dst = Path(origem).expanduser().resolve(), Path(destino).expanduser().resolve()
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir(): shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
        else: shutil.copy2(str(src), str(dst))
        return f"✅ Copiado: {src} → {dst}"
    except Exception as e: return f"Erro: {e}"

TOOL_MAP["copiar_arquivo"] = copiar_arquivo
FUNCTION_DECLARATIONS.append({"name": "copiar_arquivo", "description": "Copia arquivo", "parameters": {"type": "object", "properties": {"origem": {"type": "string"}, "destino": {"type": "string"}}}})
