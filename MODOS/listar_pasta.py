def listar_pasta(caminho: str = ".", extensao: str = "") -> str:
    try:
        p = Path(caminho).expanduser().resolve()
        if not p.is_dir(): return f"Pasta não encontrada: {p}"
        items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        if extensao:
            ext = extensao if extensao.startswith(".") else f".{extensao}"
            items = [i for i in items if i.suffix.lower() == ext.lower()]
        if not items: return "Pasta vazia."
        lines = [f"📂 {p}\n"]
        for d in [i for i in items if i.is_dir()][:50]: lines.append(f"  📁 {d.name}/")
        for f in [i for i in items if i.is_file()][:100]: lines.append(f"  📄 {f.name} ({f.stat().st_size/1024:.1f}KB)")
        return "\n".join(lines)
    except Exception as e: return f"Erro: {e}"

TOOL_MAP["listar_pasta"] = listar_pasta
FUNCTION_DECLARATIONS.append({"name": "listar_pasta", "description": "Lista diretório", "parameters": {"type": "object", "properties": {"caminho": {"type": "string"}, "extensao": {"type": "string"}}}})
