"""Busca em código, diff, edição cirúrgica, execução de Python e árvore de diretório."""
# ══════════════════════════════════════════════════════════
#  FERRAMENTAS AVANÇADAS DE CÓDIGO — inspiradas no Layka Antigravity (AGY)
#  Complementa o ler_e_editar_arquivos.py com capacidades cirúrgicas:
#    • buscar_em_codigo      — grep/regex em arquivos do projeto
#    • diff_arquivos         — comparação linha a linha entre dois arquivos
#    • editar_por_target     — substituição por string exata (sem nº de linha)
#    • executar_python       — roda um trecho Python e retorna a saída
#    • arvore_diretorio      — árvore visual de pastas (estilo `tree`)
#    • contar_linhas_codigo  — estatísticas rápidas de um projeto
# ══════════════════════════════════════════════════════════

from __future__ import annotations
from ayla_paths import resolve_path, project_path
import difflib
import io
import os
import re
import subprocess
import sys
import threading
import traceback
from pathlib import Path

if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

_BASE = project_path().resolve()

# ──────────────────────────────────────────────────────────
#  UTILITÁRIOS INTERNOS
# ──────────────────────────────────────────────────────────

def _resolver(caminho: str) -> Path:
    p_str = (caminho or "").strip().strip('"').strip("'")
    if not p_str or p_str in (".", "./"):
        return _BASE
    try:
        p = resolve_path(p_str)
        if p.exists():
            return p.resolve()
    except Exception:
        pass
    cand = _BASE / p_str
    return cand.resolve() if cand.exists() else cand.resolve()


def _ler_texto(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


_EXT_CODIGO = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs",
    ".java", ".c", ".cpp", ".h", ".hpp", ".cs", ".go",
    ".rs", ".rb", ".php", ".swift", ".kt", ".lua", ".r",
    ".sh", ".bash", ".ps1", ".bat", ".cmd",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".env",
    ".html", ".htm", ".css", ".scss", ".less", ".vue",
    ".md", ".txt", ".sql", ".xml", ".csv", ".tsv",
    ".dart", ".vue", ".cfg", ".conf", ".log"
}


# ══════════════════════════════════════════════════════════
#  1. BUSCA EM CÓDIGO (grep inteligente)
# ══════════════════════════════════════════════════════════

def buscar_em_codigo(
    padrao: str,
    caminho: str = "",
    extensao: str = "",
    ignorar_maiusculas: bool = True,
    max_resultados: int = 60,
    contexto_linhas: int = 2,
    regex: bool = False,
) -> str:
    """
    Busca um padrão (texto ou regex) em arquivos de código dentro de uma pasta.
    Retorna arquivo, número de linha e contexto ao redor de cada ocorrência.

    Args:
        padrao (str): Texto ou expressão regular a buscar.
        caminho (str): Pasta ou arquivo onde buscar (padrão: pasta da Ayla).
        extensao (str): Filtrar por extensão(ões), ex: '.py' ou '.py,.js'.
        ignorar_maiusculas (bool): Busca case-insensitive (padrão: True).
        max_resultados (int): Limite máximo de resultados (padrão: 60).
        contexto_linhas (int): Linhas de contexto ao redor de cada match (padrão: 2).
        regex (bool): Se True, trata o padrão como expressão regular.
    """
    if not padrao or not padrao.strip():
        return "⚠️ Informe um padrão para buscar."

    base = _resolver(caminho)
    if not base.exists():
        return f"❌ Caminho não encontrado: `{caminho}`"

    # Filtros de extensão
    ext_filtros: set[str] = set()
    if extensao:
        for e in extensao.split(","):
            e = e.strip().lower()
            if e and not e.startswith("."):
                e = f".{e}"
            if e:
                ext_filtros.add(e)

    flags = re.IGNORECASE if ignorar_maiusculas else 0
    try:
        pat = re.compile(padrao if regex else re.escape(padrao), flags)
    except re.error as e:
        return f"❌ Padrão regex inválido: {e}"

    arquivos = []
    if base.is_file():
        arquivos = [base]
    else:
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for f in sorted(files):
                p = Path(root) / f
                if ext_filtros and p.suffix.lower() not in ext_filtros:
                    continue
                if p.suffix.lower() not in _EXT_CODIGO and not ext_filtros:
                    continue
                arquivos.append(p)

    resultados = []
    total_matches = 0

    for arq in sorted(arquivos):
        try:
            linhas = _ler_texto(arq).splitlines()
        except Exception:
            continue

        matches_arq = []
        for i, linha in enumerate(linhas):
            if pat.search(linha):
                total_matches += 1
                if total_matches > max_resultados:
                    break
                inicio = max(0, i - contexto_linhas)
                fim = min(len(linhas), i + contexto_linhas + 1)
                bloco = []
                for j in range(inicio, fim):
                    prefixo = "▶" if j == i else " "
                    bloco.append(f"  {prefixo} {j+1:4d} │ {linhas[j]}")
                matches_arq.append("\n".join(bloco))

        if matches_arq:
            try:
                rel = arq.relative_to(_BASE)
            except ValueError:
                rel = arq
            cabecalho = f"\n📄 **`{rel}`** ({len(matches_arq)} ocorrência(s))\n"
            resultados.append(cabecalho + "\n---\n".join(matches_arq))

        if total_matches > max_resultados:
            break

    if not resultados:
        tipo = "regex" if regex else "texto"
        return f"🔍 Nenhum resultado encontrado para {tipo} `{padrao}` em `{base.name}`."

    cabecalho = (
        f"🔍 **Busca:** `{padrao}` {'(regex)' if regex else ''}\n"
        f"📂 **Escopo:** `{base}`\n"
        f"✅ **{total_matches} ocorrência(s)** encontrada(s)"
        + (f" (mostrando primeiras {max_resultados})" if total_matches > max_resultados else "")
        + "\n"
        + "━" * 60
    )
    return cabecalho + "".join(resultados)


# ══════════════════════════════════════════════════════════
#  2. DIFF ENTRE ARQUIVOS
# ══════════════════════════════════════════════════════════

def diff_arquivos(
    arquivo1: str,
    arquivo2: str,
    contexto_linhas: int = 3,
    comparar_texto: str = "",
) -> str:
    """
    Compara dois arquivos e mostra as diferenças linha a linha (unified diff).
    Também pode comparar um arquivo com um texto fornecido diretamente.

    Args:
        arquivo1 (str): Caminho do primeiro arquivo (original).
        arquivo2 (str): Caminho do segundo arquivo (modificado). Pode ser vazio se comparar_texto for fornecido.
        contexto_linhas (int): Linhas de contexto ao redor das diferenças (padrão: 3).
        comparar_texto (str): Texto para comparar com arquivo1 (alternativa ao arquivo2).
    """
    try:
        p1 = _resolver(arquivo1)
        if not p1.exists() or not p1.is_file():
            return f"❌ Arquivo 1 não encontrado: `{arquivo1}`"

        linhas1 = _ler_texto(p1).splitlines(keepends=True)

        if comparar_texto:
            linhas2 = comparar_texto.splitlines(keepends=True)
            nome2 = "(texto fornecido)"
        else:
            p2 = _resolver(arquivo2)
            if not p2.exists() or not p2.is_file():
                return f"❌ Arquivo 2 não encontrado: `{arquivo2}`"
            linhas2 = _ler_texto(p2).splitlines(keepends=True)
            nome2 = str(p2.name)

        diff = list(difflib.unified_diff(
            linhas1,
            linhas2,
            fromfile=str(p1.name),
            tofile=nome2,
            n=contexto_linhas,
            lineterm=""
        ))

        if not diff:
            return f"✅ **Arquivos idênticos!** `{p1.name}` e `{nome2}` não têm diferenças."

        # Conta adições/remoções
        adicionadas = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
        removidas = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))

        cabecalho = (
            f"🔀 **Diff:** `{p1.name}` → `{nome2}`\n"
            f"➕ {adicionadas} linha(s) adicionada(s)  |  ➖ {removidas} linha(s) removida(s)\n"
            + "━" * 60 + "\n"
        )

        return cabecalho + "```diff\n" + "\n".join(diff) + "\n```"

    except Exception as e:
        return f"❌ Erro ao comparar arquivos: {e}"


# ══════════════════════════════════════════════════════════
#  3. EDIÇÃO CIRÚRGICA POR TARGET STRING
# ══════════════════════════════════════════════════════════

def editar_por_target(
    caminho: str,
    target: str,
    substituto: str,
    ocorrencia: int = 0,
    fazer_backup: bool = True,
) -> str:
    """
    Edita um arquivo substituindo uma string exata (target) por outra (substituto).
    Mais seguro que editar_arquivo modo 'substituir_texto' — mostra diff antes/depois.

    Args:
        caminho (str): Caminho do arquivo a editar.
        target (str): Texto exato a encontrar (incluindo espaços e quebras de linha).
        substituto (str): Texto de substituição.
        ocorrencia (int): Qual ocorrência substituir (0 = todas, 1 = primeira, 2 = segunda...).
        fazer_backup (bool): Se True, cria cópia .bak antes de editar.
    """
    try:
        path = _resolver(caminho)
        if not path.exists() or not path.is_file():
            return f"❌ Arquivo não encontrado: `{caminho}`"

        texto_original = _ler_texto(path)

        if target not in texto_original:
            # Tenta busca case-insensitive para dar dica
            if target.lower() in texto_original.lower():
                return (
                    f"⚠️ Target não encontrado com capitalização exata em `{path.name}`.\n"
                    f"💡 Encontrado com capitalização diferente. Ajuste o target e tente novamente."
                )
            return f"⚠️ Target não encontrado em `{path.name}`."

        total_ocorrencias = texto_original.count(target)

        if ocorrencia == 0:
            # Substituir todas
            novo_texto = texto_original.replace(target, substituto)
            qtd = total_ocorrencias
            msg_ocorrencia = f"todas as {qtd} ocorrências"
        elif 1 <= ocorrencia <= total_ocorrencias:
            # Substituir a N-ésima ocorrência
            partes = texto_original.split(target)
            # partes[0] + target + partes[1] + target + ... 
            # Para substituir a N-ésima: juntar as N-1 primeiras com target, depois substituir
            resultado = target.join(partes[:ocorrencia]) + substituto + target.join(partes[ocorrencia:])
            novo_texto = resultado
            qtd = 1
            msg_ocorrencia = f"ocorrência {ocorrencia} de {total_ocorrencias}"
        else:
            return f"⚠️ Ocorrência {ocorrencia} inválida. O target aparece {total_ocorrencias} vez(es)."

        # Backup
        if fazer_backup:
            try:
                bak = path.with_suffix(path.suffix + ".bak")
                bak.write_bytes(path.read_bytes())
            except Exception:
                pass

        path.write_text(novo_texto, encoding="utf-8")

        # Diff rápido para confirmar
        linhas_antes = texto_original.splitlines()
        linhas_depois = novo_texto.splitlines()
        diff = list(difflib.unified_diff(
            linhas_antes, linhas_depois,
            fromfile=f"{path.name} (antes)",
            tofile=f"{path.name} (depois)",
            n=2, lineterm=""
        ))

        diff_str = ""
        if diff:
            diff_str = "\n```diff\n" + "\n".join(diff[:60]) + ("\n... [diff truncado]" if len(diff) > 60 else "") + "\n```"

        return (
            f"✏️ **Edição cirúrgica aplicada!**\n"
            f"📄 Arquivo: `{path.name}`\n"
            f"🔢 Substituído: {msg_ocorrencia}\n"
            f"🔴 **Target:** `{target[:100]}{'...' if len(target)>100 else ''}`\n"
            f"🟢 **Substituto:** `{substituto[:100]}{'...' if len(substituto)>100 else ''}`"
            + diff_str
        )

    except Exception as e:
        return f"❌ Erro ao editar arquivo: {e}"


# ══════════════════════════════════════════════════════════
#  4. EXECUÇÃO DE PYTHON
# ══════════════════════════════════════════════════════════

def executar_python(
    codigo: str,
    timeout: int = 30,
    arquivo: str = "",
) -> str:
    """
    Executa um trecho de código Python e retorna stdout + stderr.
    Pode executar um arquivo .py existente ou um código inline.

    Args:
        codigo (str): Código Python a executar (inline). Ignorado se 'arquivo' for fornecido.
        timeout (int): Timeout em segundos (padrão: 30).
        arquivo (str): Caminho de um arquivo .py existente para executar.
    """
    try:
        if arquivo:
            path = _resolver(arquivo)
            if not path.exists() or not path.is_file():
                return f"❌ Arquivo não encontrado: `{arquivo}`"
            cmd = [sys.executable, str(path)]
            cwd = str(path.parent)
            descricao = f"`{path.name}`"
        else:
            if not codigo or not codigo.strip():
                return "⚠️ Forneça código Python para executar ou o caminho de um arquivo."
            cmd = [sys.executable, "-c", codigo]
            cwd = str(_BASE)
            linhas = codigo.strip().splitlines()
            preview = "\n".join(linhas[:5]) + ("\n..." if len(linhas) > 5 else "")
            descricao = f"código inline:\n```python\n{preview}\n```"

        resultado = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
        )

        stdout = resultado.stdout.strip()
        stderr = resultado.stderr.strip()
        rc = resultado.returncode

        saida = []
        if stdout:
            saida.append(f"📤 **stdout:**\n```\n{stdout}\n```")
        if stderr:
            saida.append(f"⚠️ **stderr:**\n```\n{stderr}\n```")
        if not stdout and not stderr:
            saida.append("*(sem saída)*")

        status = "✅ **Sucesso**" if rc == 0 else f"❌ **Erro** (exit code: {rc})"

        return (
            f"🐍 **Execução Python** — {descricao}\n"
            f"{status}\n"
            + "\n".join(saida)
        )

    except subprocess.TimeoutExpired:
        return f"⏱️ **Timeout!** O código excedeu {timeout}s e foi interrompido."
    except Exception as e:
        return f"❌ Erro ao executar Python: {e}"


# ══════════════════════════════════════════════════════════
#  5. ÁRVORE DE DIRETÓRIO VISUAL
# ══════════════════════════════════════════════════════════

def arvore_diretorio(
    caminho: str = "",
    profundidade: int = 3,
    mostrar_ocultos: bool = False,
    filtro_extensao: str = "",
    max_itens: int = 200,
) -> str:
    """
    Exibe a estrutura de um diretório no formato de árvore visual (estilo `tree`).

    Args:
        caminho (str): Pasta a exibir (padrão: pasta da Ayla).
        profundidade (int): Profundidade máxima da árvore (padrão: 3).
        mostrar_ocultos (bool): Se True, inclui arquivos/pastas ocultos.
        filtro_extensao (str): Mostrar apenas arquivos com esta extensão(ões).
        max_itens (int): Limite de itens na árvore (padrão: 200).
    """
    base = _resolver(caminho)
    if not base.exists():
        return f"❌ Caminho não encontrado: `{caminho}`"
    if not base.is_dir():
        return f"⚠️ `{base.name}` é um arquivo, não uma pasta. Use `ler_arquivo` para lê-lo."

    ext_filtros: set[str] = set()
    if filtro_extensao:
        for e in filtro_extensao.split(","):
            e = e.strip().lower()
            if e and not e.startswith("."):
                e = f".{e}"
            if e:
                ext_filtros.add(e)

    linhas = [f"📁 **`{base}`**"]
    contador = [0]
    truncado = [False]

    def _walk(pasta: Path, prefixo: str, nivel: int):
        if nivel > profundidade or truncado[0]:
            return
        try:
            entradas = sorted(pasta.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except PermissionError:
            linhas.append(f"{prefixo}└── ⛔ (sem permissão)")
            return

        entradas_visiveis = [
            e for e in entradas
            if (mostrar_ocultos or not e.name.startswith("."))
            and e.name != "__pycache__"
            and (not ext_filtros or e.is_dir() or e.suffix.lower() in ext_filtros)
        ]

        for i, entrada in enumerate(entradas_visiveis):
            if truncado[0]:
                break
            eh_ultimo = (i == len(entradas_visiveis) - 1)
            conector = "└──" if eh_ultimo else "├──"
            prox_prefixo = prefixo + ("    " if eh_ultimo else "│   ")

            if entrada.is_dir():
                try:
                    n = len(list(entrada.iterdir()))
                except Exception:
                    n = "?"
                linhas.append(f"{prefixo}{conector} 📁 `{entrada.name}/` *({n} itens)*")
                contador[0] += 1
                if contador[0] >= max_itens:
                    linhas.append(f"{prox_prefixo}... [truncado — mais de {max_itens} itens]")
                    truncado[0] = True
                    return
                _walk(entrada, prox_prefixo, nivel + 1)
            else:
                try:
                    tam = entrada.stat().st_size
                    tam_str = f"{tam/1024:.1f}KB" if tam >= 1024 else f"{tam}B"
                except Exception:
                    tam_str = "?"
                linhas.append(f"{prefixo}{conector} `{entrada.name}` *({tam_str})*")
                contador[0] += 1
                if contador[0] >= max_itens:
                    linhas.append(f"{prefixo}... [truncado — mais de {max_itens} itens]")
                    truncado[0] = True

    _walk(base, "", 0)
    return "\n".join(linhas)


# ══════════════════════════════════════════════════════════
#  6. ESTATÍSTICAS DE CÓDIGO
# ══════════════════════════════════════════════════════════

def contar_linhas_codigo(
    caminho: str = "",
    extensao: str = ".py",
) -> str:
    """
    Conta linhas de código, comentários e linhas em branco por arquivo em uma pasta.
    Útil para ter uma visão rápida do tamanho do projeto.

    Args:
        caminho (str): Pasta a analisar (padrão: pasta da Ayla).
        extensao (str): Extensão(ões) dos arquivos a contar (padrão: '.py').
    """
    base = _resolver(caminho)
    if not base.exists():
        return f"❌ Caminho não encontrado: `{caminho}`"

    ext_filtros: set[str] = set()
    for e in extensao.split(","):
        e = e.strip().lower()
        if not e.startswith("."):
            e = f".{e}"
        ext_filtros.add(e)

    arquivos_info = []
    total_codigo = total_comentarios = total_brancos = total_linhas = 0

    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
        for f in sorted(files):
            p = Path(root) / f
            if p.suffix.lower() not in ext_filtros:
                continue
            try:
                texto = _ler_texto(p)
                linhas = texto.splitlines()
                n_total = len(linhas)
                n_brancos = sum(1 for l in linhas if not l.strip())
                n_comentarios = sum(1 for l in linhas if l.strip().startswith(("#", "//", "/*", "*", "<!--")))
                n_codigo = n_total - n_brancos - n_comentarios

                total_codigo += n_codigo
                total_comentarios += n_comentarios
                total_brancos += n_brancos
                total_linhas += n_total

                try:
                    rel = p.relative_to(base)
                except ValueError:
                    rel = p.name

                arquivos_info.append((str(rel), n_total, n_codigo, n_comentarios, n_brancos))
            except Exception:
                continue

    if not arquivos_info:
        return f"❌ Nenhum arquivo `{extensao}` encontrado em `{base}`."

    arquivos_info.sort(key=lambda x: x[1], reverse=True)

    linhas_tabela = [
        "| Arquivo | Total | Código | Comentários | Brancos |",
        "|---------|------:|-------:|------------:|--------:|"
    ]
    for rel, tot, cod, com, bra in arquivos_info[:30]:
        linhas_tabela.append(f"| `{rel}` | {tot} | {cod} | {com} | {bra} |")

    if len(arquivos_info) > 30:
        linhas_tabela.append(f"| *... e mais {len(arquivos_info)-30} arquivos* | | | | |")

    rodape = (
        f"\n**Totais:** {len(arquivos_info)} arquivo(s) | "
        f"**{total_linhas}** linhas total | "
        f"**{total_codigo}** código | "
        f"**{total_comentarios}** comentários | "
        f"**{total_brancos}** em branco"
    )

    return (
        f"📊 **Estatísticas de Código** — `{base.name}` (`{extensao}`)\n\n"
        + "\n".join(linhas_tabela)
        + rodape
    )


# ══════════════════════════════════════════════════════════
#  REGISTRO
# ══════════════════════════════════════════════════════════

def register(tool_map: dict, function_declarations: list):
    """Registra as ferramentas avançadas de código no sistema da Ayla."""

    tool_map["buscar_em_codigo"] = buscar_em_codigo
    tool_map["diff_arquivos"] = diff_arquivos
    tool_map["editar_por_target"] = editar_por_target
    tool_map["executar_python"] = executar_python
    tool_map["arvore_diretorio"] = arvore_diretorio
    tool_map["contar_linhas_codigo"] = contar_linhas_codigo

    # Limpa declarações antigas
    nomes = {"buscar_em_codigo", "diff_arquivos", "editar_por_target",
             "executar_python", "arvore_diretorio", "contar_linhas_codigo"}
    for i in range(len(function_declarations) - 1, -1, -1):
        if function_declarations[i].get("name") in nomes:
            function_declarations.pop(i)

    function_declarations.append({
        "name": "buscar_em_codigo",
        "description": (
            "Busca um texto ou padrão regex em arquivos de código dentro de uma pasta. "
            "Retorna arquivo, número de linha e contexto. Ideal para encontrar funções, "
            "classes, variáveis ou qualquer padrão em um projeto."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "padrao": {"type": "string", "description": "Texto ou regex a buscar."},
                "caminho": {"type": "string", "description": "Pasta ou arquivo onde buscar (padrão: pasta da Ayla)."},
                "extensao": {"type": "string", "description": "Filtrar por extensão(ões), ex: '.py' ou '.py,.js'."},
                "ignorar_maiusculas": {"type": "boolean", "description": "Busca case-insensitive (padrão: True)."},
                "max_resultados": {"type": "integer", "description": "Limite de resultados (padrão: 60)."},
                "contexto_linhas": {"type": "integer", "description": "Linhas de contexto ao redor do match (padrão: 2)."},
                "regex": {"type": "boolean", "description": "Se True, trata o padrão como expressão regular."},
            },
            "required": ["padrao"]
        }
    })

    function_declarations.append({
        "name": "diff_arquivos",
        "description": (
            "Compara dois arquivos e mostra as diferenças linha a linha (unified diff). "
            "Também pode comparar um arquivo com um texto fornecido diretamente. "
            "Útil para revisar mudanças antes de aplicar ou verificar o que foi alterado."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "arquivo1": {"type": "string", "description": "Caminho do arquivo original."},
                "arquivo2": {"type": "string", "description": "Caminho do arquivo modificado (opcional se comparar_texto for fornecido)."},
                "contexto_linhas": {"type": "integer", "description": "Linhas de contexto ao redor das diferenças (padrão: 3)."},
                "comparar_texto": {"type": "string", "description": "Texto para comparar com arquivo1 (alternativa ao arquivo2)."},
            },
            "required": ["arquivo1"]
        }
    })

    function_declarations.append({
        "name": "editar_por_target",
        "description": (
            "Edita um arquivo substituindo uma string exata (target) por outra (substituto), "
            "sem precisar saber o número da linha. Mais cirúrgico e seguro que reescrever o arquivo todo. "
            "Mostra diff antes/depois para confirmação. Suporta substituir todas as ocorrências ou apenas uma específica."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "caminho": {"type": "string", "description": "Caminho do arquivo a editar."},
                "target": {"type": "string", "description": "Texto exato a encontrar (incluindo espaços e quebras de linha)."},
                "substituto": {"type": "string", "description": "Texto de substituição."},
                "ocorrencia": {"type": "integer", "description": "Qual ocorrência substituir (0=todas, 1=primeira, 2=segunda...). Padrão: 0."},
                "fazer_backup": {"type": "boolean", "description": "Se True, cria cópia .bak antes de editar (padrão: True)."},
            },
            "required": ["caminho", "target", "substituto"]
        }
    })

    function_declarations.append({
        "name": "executar_python",
        "description": (
            "Executa um trecho de código Python inline ou um arquivo .py e retorna stdout + stderr. "
            "Útil para testar funções, validar lógica, processar dados ou rodar scripts rápidos."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "codigo": {"type": "string", "description": "Código Python a executar inline (ignorado se 'arquivo' for fornecido)."},
                "timeout": {"type": "integer", "description": "Timeout em segundos (padrão: 30)."},
                "arquivo": {"type": "string", "description": "Caminho de um arquivo .py para executar (alternativa ao código inline)."},
            },
            "required": []
        }
    })

    function_declarations.append({
        "name": "arvore_diretorio",
        "description": (
            "Exibe a estrutura de um diretório no formato de árvore visual (estilo `tree`), "
            "mostrando pastas e arquivos com tamanhos. Mais legível que listar_pasta para "
            "entender a organização de um projeto."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "caminho": {"type": "string", "description": "Pasta a exibir (padrão: pasta da Ayla)."},
                "profundidade": {"type": "integer", "description": "Profundidade máxima da árvore (padrão: 3)."},
                "mostrar_ocultos": {"type": "boolean", "description": "Se True, inclui arquivos/pastas ocultos."},
                "filtro_extensao": {"type": "string", "description": "Mostrar apenas arquivos com esta extensão(ões), ex: '.py'."},
                "max_itens": {"type": "integer", "description": "Limite de itens na árvore (padrão: 200)."},
            },
            "required": []
        }
    })

    function_declarations.append({
        "name": "contar_linhas_codigo",
        "description": (
            "Conta linhas de código, comentários e linhas em branco por arquivo em uma pasta. "
            "Gera uma tabela com estatísticas de cada arquivo e totais do projeto."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "caminho": {"type": "string", "description": "Pasta a analisar (padrão: pasta da Ayla)."},
                "extensao": {"type": "string", "description": "Extensão(ões) dos arquivos a contar (padrão: '.py')."},
            },
            "required": []
        }
    })


# ── Auto-registro
register(TOOL_MAP, FUNCTION_DECLARATIONS)
