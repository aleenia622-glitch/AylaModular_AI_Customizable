def organizar_pasta(caminho: str) -> str:
    try:
        p = Path(caminho).expanduser().resolve()
        if not p.is_dir(): return f"Pasta não encontrada: {p}"
        ext_map = {
            "Imagens": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".ico"],
            "Documentos": [".txt", ".pdf", ".docx", ".xlsx", ".pptx", ".md", ".json", ".csv"],
            "Videos": [".mp4", ".mkv", ".avi", ".mov", ".wmv"],
            "Executaveis": [".exe", ".msi", ".bat", ".ps1"],
            "Compactados": [".zip", ".rar", ".7z", ".tar", ".gz"],
            "Audios": [".mp3", ".wav", ".ogg", ".flac", ".aac", ".wma"]
        }
        movidos = 0
        for item in p.iterdir():
            if item.is_file() and not item.name.startswith("temp_"):
                for pasta, extensoes in ext_map.items():
                    if item.suffix.lower() in extensoes:
                        dest_dir = p / pasta
                        dest_dir.mkdir(exist_ok=True)
                        shutil.move(str(item), str(dest_dir / item.name))
                        movidos += 1
                        break
        return f"✅ Faxina concluída! Organizei {movidos} arquivos em subpastas."
    except Exception as e: return f"Erro: {e}"

TOOL_MAP["organizar_pasta"] = organizar_pasta
FUNCTION_DECLARATIONS.append({"name": "organizar_pasta", "description": "Organiza arquivos em subpastas por tipo.", "parameters": {"type": "object", "properties": {"caminho": {"type": "string"}}, "required": ["caminho"]}})
