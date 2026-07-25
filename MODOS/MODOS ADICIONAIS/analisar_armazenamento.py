# analisar_armazenamento.py - Analisa o armazenamento do PC
import os
import shutil
import time
from pathlib import Path

# Garante compatibilidade se o arquivo for executado/importado individualmente
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

def tamanho_legivel(tamanho_bytes):
    for unidade in ['B', 'KB', 'MB', 'GB', 'TB']:
        if tamanho_bytes < 1024.0:
            return f"{tamanho_bytes:.2f} {unidade}"
        tamanho_bytes /= 1024.0
    return f"{tamanho_bytes:.2f} PB"

def analisar_armazenamento(caminho_customizado: str = None) -> str:
    """
    Analisa o armazenamento do PC, listando o uso dos discos, o tamanho das pastas do usuário
    e os maiores arquivos encontrados para ajudar a liberar espaço.
    """
    inicio = time.time()
    
    # 1. Uso geral de discos
    drives = ['C:', 'D:', 'E:', 'F:']
    resumo_discos = []
    for drive in drives:
        path = drive + '\\'
        if os.path.exists(path):
            try:
                usage = shutil.disk_usage(path)
                total = usage.total
                used = usage.used
                free = usage.free
                pct = (used / total) * 100
                resumo_discos.append(
                    f"• **{drive}**: {tamanho_legivel(used)} / {tamanho_legivel(total)} usados ({pct:.1f}% em uso) | **Livre: {tamanho_legivel(free)}**"
                )
            except Exception:
                pass
                
    discos_str = "\n".join(resumo_discos) if resumo_discos else "Nenhum disco detectado."

    # 2. Definir pastas a analisar
    home = Path.home()
    if caminho_customizado:
        caminho_alvo = Path(caminho_customizado)
        if not caminho_alvo.exists():
            return f"❌ A pasta `{caminho_customizado}` não existe!"
    else:
        caminho_alvo = home

    # Lista de pastas importantes no perfil do usuário
    pastas_analise = []
    if not caminho_customizado:
        # Se for a home do usuário, analisamos as pastas padrão
        pastas_padrao = [
            ("Downloads", home / "Downloads"),
            ("Área de Trabalho", home / "Desktop"),
            ("Documentos", home / "Documents"),
            ("Vídeos", home / "Videos"),
            ("Imagens", home / "Pictures"),
            ("Músicas", home / "Music"),
            ("Temporários do Usuário", Path(os.environ.get('TEMP', home / 'AppData/Local/Temp'))),
            ("Temporários do Windows", Path(r"C:\Windows\Temp"))
        ]
        for nome, p in pastas_padrao:
            if p.exists():
                pastas_analise.append((nome, p))
    else:
        # Se for um caminho customizado, analisamos os subdiretórios de 1º nível dele
        pastas_analise.append((caminho_alvo.name, caminho_alvo))
        try:
            for entry in os.scandir(caminho_alvo):
                if entry.is_dir(follow_symlinks=False) and not entry.name.startswith('.'):
                    pastas_analise.append((entry.name, Path(entry.path)))
        except Exception:
            pass

    # 3. Escanear pastas e coletar tamanhos e arquivos grandes
    detalhes_pastas = []
    todos_arquivos_grandes = []
    tempo_limite = 8.0  # Limite de 8 segundos para evitar travamento do Discord
    limite_atingido = False

    def escancear_recursivo(caminho_dir, lista_grandes, limite_tempo, tempo_inicio):
        nonlocal limite_atingido
        tamanho_total = 0
        piles = [Path(caminho_dir)]
        
        while piles:
            if time.time() - tempo_inicio > limite_tempo:
                limite_atingido = True
                break
            
            pasta_atual = piles.pop()
            try:
                for entry in os.scandir(pasta_atual):
                    # Ignorar arquivos/pastas ocultos ou de sistema
                    if entry.name.startswith('.') or entry.name.startswith('$'):
                        continue
                    
                    # Pula AppData se não estiver explicitamente analisando ele
                    parts = Path(entry.path).parts
                    if 'AppData' in parts and 'Temp' not in parts:
                        if not (caminho_customizado and 'AppData' in Path(caminho_customizado).parts):
                            continue
                    
                    if entry.is_dir(follow_symlinks=False):
                        piles.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        try:
                            sz = entry.stat().st_size
                            tamanho_total += sz
                            if sz > 15 * 1024 * 1024:  # Arquivos maiores que 15MB
                                lista_grandes.append((entry.path, sz))
                        except Exception:
                            pass
            except Exception:
                pass
        return tamanho_total

    for nome, p in pastas_analise:
        if limite_atingido:
            break
        grandes_da_pasta = []
        tamanho_pasta = escancear_recursivo(p, grandes_da_pasta, tempo_limite, inicio)
        todos_arquivos_grandes.extend(grandes_da_pasta)
        if tamanho_pasta > 0 or p.exists():
            detalhes_pastas.append((nome, p, tamanho_pasta))

    # Ordenar pastas por tamanho decrescente
    detalhes_pastas.sort(key=lambda x: x[2], reverse=True)
    
    # Ordenar maiores arquivos
    todos_arquivos_grandes.sort(key=lambda x: x[1], reverse=True)
    top_arquivos = todos_arquivos_grandes[:15]

    # 4. Construir resposta formatada
    linhas = [
        "🔍 📊 **ANÁLISE DE ARMAZENAMENTO DA AYLA** 📊 🔍",
        "",
        "💾 **Espaço nos Discos:**",
        discos_str,
        "",
        f"📂 **Tamanho das Pastas Analisadas (Origem: `{caminho_alvo.resolve()}`):**"
    ]

    for nome, p, tam in detalhes_pastas:
        linhas.append(f"• **{nome}**: {tamanho_legivel(tam)} (`{p.name}`)")

    linhas.append("")
    linhas.append("🏆 **Top Maiores Arquivos Encontrados (para liberar espaço):**")
    
    if top_arquivos:
        for i, (caminho_arq, tam) in enumerate(top_arquivos, 1):
            p_arq = Path(caminho_arq)
            try:
                rel = p_arq.relative_to(home)
                rel_str = f"~\\{rel}"
            except Exception:
                rel_str = str(p_arq)
            linhas.append(f"  {i}. 📄 **{p_arq.name}** ({tamanho_legivel(tam)})")
            linhas.append(f"     📍 `{rel_str}`")
    else:
        linhas.append("  • Nenhum arquivo grande (>15MB) encontrado.")

    if limite_atingido:
        linhas.append("")
        linhas.append("⚠️ *Nota: A análise foi interrompida para não demorar demais, os dados acima são parciais.*")

    linhas.append("")
    linhas.append(f"⏱️ *Tempo de análise: {time.time() - inicio:.2f} segundos.*")

    return "\n".join(linhas)

TOOL_MAP["analisar_armazenamento"] = analisar_armazenamento
FUNCTION_DECLARATIONS.append({
    "name": "analisar_armazenamento",
    "description": "Analisa o armazenamento do PC: mostra espaço nos discos, tamanho das pastas do usuário e lista os maiores arquivos para liberar espaço.",
    "parameters": {
        "type": "object",
        "properties": {
            "caminho_customizado": {
                "type": "string",
                "description": "Opcional. Caminho de uma pasta específica para analisar. Se não fornecido, analisa as pastas de usuário padrão."
            }
        }
    }
})
