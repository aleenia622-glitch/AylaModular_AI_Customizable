# ══════════════════════════════════════════════════════════
#  MODO ANALISAR REPOSITÓRIO — Ayla GitHub Repo Analyzer
#  Clona repos, escaneia com Windows Defender, e usa IA
#  para explicar o conteúdo do repositório.
#  Modelo primário: gemini-3.0-flash
#  Fallbacks:       gemma-4-31b-it → gemma-4-26b-it → gemini-3.1-flash-lite
# ══════════════════════════════════════════════════════════

import os
import sys
import re
import subprocess
import shutil
from pathlib import Path
from datetime import datetime

# ── Constantes ──────────────────────────────────────────
_BASE_SEGURA = Path(__file__).resolve().parents[2]
_PASTA_REPOS = (_BASE_SEGURA / "MODOS" / "repos_clonados").resolve()

_TIMEOUT_CLONE = 180          # segundos para git clone
_TIMEOUT_SCAN = 300           # segundos para scan do antivírus
_MAX_CHARS_ARQUIVO = 8000     # max chars por arquivo individual
_MAX_CHARS_TOTAL = 120000     # max chars total para enviar ao modelo
_MAX_TAMANHO_ARQUIVO = 512 * 1024  # 512 KB — ignorar arquivos maiores

_MODELOS_ANALISE = [
    "gemini-3.6-flash",
    "gemini-3.0-flash",
    "gemma-4-31b-it",
    "gemma-4-26b-it",
    "gemini-3.1-flash-lite",
]

# ── Estado Persistente da Sessão de Análise de Repositório ──────────────
_SESSAO_ANALISE = {
    "ativo": False,
    "repo_url": None,
    "pasta_repo": None,
    "contents": [],
    "modelo_atual": None,
    "criado_em": None,
}

def fechar_modo_analisar_repo() -> str:
    """Encerra a sessão ativa de análise de repositório e limpa seu histórico de contexto."""
    global _SESSAO_ANALISE
    if not _SESSAO_ANALISE.get("ativo"):
        return "ℹ️ Nenhuma sessão de análise de repositório está ativa no momento."

    url = _SESSAO_ANALISE.get("repo_url", "")
    _SESSAO_ANALISE["ativo"] = False
    _SESSAO_ANALISE["contents"] = []
    _SESSAO_ANALISE["repo_url"] = None
    _SESSAO_ANALISE["pasta_repo"] = None
    _SESSAO_ANALISE["modelo_atual"] = None
    _SESSAO_ANALISE["criado_em"] = None
    _safe_print("[Analisar Repo] Sessão encerrada e contexto limpo pela Ayla.")
    return f"🔒 Sessão de análise do repositório ({url}) encerrada e contexto limpo com sucesso pela Ayla!"

def status_analise_repositorio() -> str:
    """Retorna o status da sessão ativa de análise de repositório."""
    if _SESSAO_ANALISE.get("ativo"):
        turnos = len(_SESSAO_ANALISE.get("contents", []))
        mod = _SESSAO_ANALISE.get("modelo_atual", "Desconhecido")
        url = _SESSAO_ANALISE.get("repo_url", "Desconhecido")
        pasta = _SESSAO_ANALISE.get("pasta_repo", "Desconhecido")
        return (
            f"🟢 **Sessão de Análise de Repositório está ATIVA!**\n"
            f"• Repositório: `{url}`\n"
            f"• Pasta local: `{pasta}`\n"
            f"• Modelo atual: `{mod}`\n"
            f"• Mensagens no contexto: `{turnos}`\n\n"
            f"Para encerrar a sessão quando não precisar mais dela, use a ferramenta `fechar_modo_analisar_repo`."
        )
    return "⚪ **Sessão de Análise de Repositório está INATIVA.** Nenhuma análise aberta no momento."

# Extensões de arquivos de texto que devemos ler
_EXTENSOES_TEXTO = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs",
    ".md", ".txt", ".rst", ".adoc",
    ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".env.example",
    ".html", ".htm", ".css", ".scss", ".less",
    ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx",
    ".java", ".kt", ".kts", ".scala",
    ".go", ".rs", ".rb", ".php", ".pl", ".pm",
    ".sh", ".bash", ".zsh", ".bat", ".cmd", ".ps1",
    ".sql", ".r", ".R", ".lua", ".dart", ".swift",
    ".cs", ".fs", ".vb",
    ".xml", ".svg",
    ".dockerfile", ".makefile", ".cmake",
    ".gitignore", ".gitattributes", ".editorconfig",
    ".lock",  # package-lock, Cargo.lock etc (útil pra entender deps)
}

# Nomes de arquivo sem extensão que devemos ler
_NOMES_ESPECIAIS = {
    "Dockerfile", "Makefile", "CMakeLists.txt", "Rakefile",
    "Gemfile", "Procfile", "LICENSE", "COPYING", "CHANGELOG",
    "README", "CONTRIBUTING", "AUTHORS", "NOTICE",
}

# Pastas a ignorar durante a coleta
_PASTAS_IGNORAR = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".env", ".tox", ".mypy_cache", ".pytest_cache",
    ".eggs", "dist", "build", ".next", ".nuxt",
    "vendor", "target", "out", "bin", "obj",
    ".idea", ".vscode", ".vs",
}


# ── Print seguro (Windows cp1252 não suporta emojis) ────
def _safe_print(msg: str):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))


# ══════════════════════════════════════════════════════════
#  OBTENÇÃO DE API KEY (mesmo padrão do modo_agente)
# ══════════════════════════════════════════════════════════

def _obter_api_key() -> str | None:
    """Busca a melhor API key disponível."""
    key = os.environ.get("AGENT_KEY", "").strip()
    if key:
        return key

    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        key = os.environ.get("AGENT_KEY", "").strip()
        if key:
            return key
    except Exception:
        pass

    import builtins
    bot_ref = globals().get("bot") or getattr(builtins, "bot", None)
    if bot_ref and hasattr(bot_ref, "api_keys") and bot_ref.api_keys:
        idx = getattr(bot_ref, "idx_api_atual", 0)
        return bot_ref.api_keys[idx % len(bot_ref.api_keys)]

    chaves = globals().get("GEMINI_API_KEYS") or getattr(builtins, "GEMINI_API_KEYS", [])
    if chaves:
        return chaves[0]

    return None


def _obter_todas_api_keys() -> list[str]:
    """Retorna todas as API keys disponíveis para rodízio."""
    keys = []
    import builtins
    bot_ref = globals().get("bot") or getattr(builtins, "bot", None)
    if bot_ref and hasattr(bot_ref, "api_keys"):
        keys = list(bot_ref.api_keys)
    if not keys:
        chaves = globals().get("GEMINI_API_KEYS") or getattr(builtins, "GEMINI_API_KEYS", [])
        keys = list(chaves)
    agent_key = os.environ.get("AGENT_KEY", "").strip()
    if agent_key and agent_key not in keys:
        keys.insert(0, agent_key)
    return [k for k in keys if k.strip()]


# ══════════════════════════════════════════════════════════
#  ETAPA 1: CLONAR REPOSITÓRIO
# ══════════════════════════════════════════════════════════

def _validar_url_github(url: str) -> bool:
    """Valida se a URL parece ser um repositório GitHub válido."""
    url = url.strip().rstrip("/")
    # Aceita formatos:
    #   https://github.com/user/repo
    #   https://github.com/user/repo.git
    #   git@github.com:user/repo.git
    padrao_https = re.compile(
        r"^https?://github\.com/[\w\-\.]+/[\w\-\.]+(?:\.git)?$", re.IGNORECASE
    )
    padrao_ssh = re.compile(
        r"^git@github\.com:[\w\-\.]+/[\w\-\.]+(?:\.git)?$", re.IGNORECASE
    )
    return bool(padrao_https.match(url) or padrao_ssh.match(url))


def _extrair_nome_repo(url: str) -> str:
    """Extrai o nome do repositório a partir da URL."""
    url = url.strip().rstrip("/")
    # Remove .git do final se houver
    if url.endswith(".git"):
        url = url[:-4]
    # Pega a última parte do caminho
    nome = url.split("/")[-1]
    # Para SSH: git@github.com:user/repo
    if ":" in nome:
        nome = nome.split(":")[-1].split("/")[-1]
    return nome or "repo_desconhecido"


def _clonar_repositorio(url: str) -> tuple[bool, str, Path | None]:
    """Clona um repositório GitHub.

    Returns:
        (sucesso, mensagem, caminho_da_pasta)
    """
    url = url.strip().rstrip("/")

    if not _validar_url_github(url):
        return False, f"URL invalida. Esperado um link do GitHub (ex: https://github.com/user/repo)", None

    nome_repo = _extrair_nome_repo(url)
    pasta_destino = _PASTA_REPOS / nome_repo

    # Se já existe, remover para clonar de novo
    if pasta_destino.exists():
        _safe_print(f"  Pasta '{nome_repo}' ja existe, removendo para re-clonar...")
        try:
            shutil.rmtree(pasta_destino)
        except Exception as e:
            return False, f"Erro ao remover pasta existente: {e}", None

    # Criar pasta de repos se não existir
    _PASTA_REPOS.mkdir(parents=True, exist_ok=True)

    _safe_print(f"  Clonando {url}...")
    try:
        resultado = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(pasta_destino)],
            capture_output=True, text=True, timeout=_TIMEOUT_CLONE,
            encoding="utf-8", errors="replace",
        )

        if resultado.returncode != 0:
            erro = resultado.stderr.strip() if resultado.stderr else "Erro desconhecido"
            return False, f"Erro no git clone: {erro}", None

        if not pasta_destino.exists():
            return False, "git clone executou mas a pasta nao foi criada.", None

        _safe_print(f"  Clone concluido: {pasta_destino}")
        return True, f"Repositorio clonado em: {pasta_destino}", pasta_destino

    except subprocess.TimeoutExpired:
        # Limpar pasta parcial
        if pasta_destino.exists():
            shutil.rmtree(pasta_destino, ignore_errors=True)
        return False, f"Timeout: clone excedeu {_TIMEOUT_CLONE}s. Repositorio pode ser muito grande.", None
    except FileNotFoundError:
        return False, "Erro: 'git' nao encontrado no sistema. Instale o Git primeiro.", None
    except Exception as e:
        return False, f"Erro inesperado ao clonar: {e}", None


# ══════════════════════════════════════════════════════════
#  ETAPA 2: SCAN COM WINDOWS DEFENDER
# ══════════════════════════════════════════════════════════

def _escanear_antivirus(pasta: Path) -> tuple[bool, str]:
    """Executa scan rápido do Windows Defender na pasta.

    Returns:
        (limpo, mensagem) — limpo=True se nenhuma ameaça foi encontrada
    """
    _safe_print(f"  Escaneando com Windows Defender...")
    caminho_str = str(pasta.resolve())

    try:
        # Usar Start-MpScan para scan customizado na pasta
        cmd_scan = (
            f'Start-MpScan -ScanPath "{caminho_str}" -ScanType CustomScan'
        )
        resultado = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd_scan],
            capture_output=True, text=True, timeout=_TIMEOUT_SCAN,
            encoding="utf-8", errors="replace",
        )

        # Verificar se houve ameaças detectadas consultando o histórico recente
        cmd_ameacas = (
            "Get-MpThreatDetection | "
            "Where-Object { $_.InitialDetectionTime -gt (Get-Date).AddMinutes(-5) } | "
            "Select-Object -Property ThreatID, Resources | "
            "Format-List"
        )
        resultado_ameacas = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd_ameacas],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )

        saida_ameacas = resultado_ameacas.stdout.strip() if resultado_ameacas.stdout else ""

        # Se encontrou algo relacionado à pasta escaneada
        if saida_ameacas and caminho_str.lower() in saida_ameacas.lower():
            _safe_print(f"  ALERTA: Ameacas detectadas!")
            return False, f"AMEACA DETECTADA pelo Windows Defender!\n\nDetalhes:\n{saida_ameacas}"

        _safe_print(f"  Scan limpo - nenhuma ameaca encontrada")
        return True, "Scan completo: nenhuma ameaca detectada pelo Windows Defender."

    except subprocess.TimeoutExpired:
        _safe_print(f"  Timeout no scan do antivirus")
        return True, (
            "Aviso: O scan do antivirus excedeu o tempo limite. "
            "O Windows Defender pode continuar escaneando em segundo plano. "
            "Prosseguindo com a analise."
        )
    except Exception as e:
        _safe_print(f"  Erro no scan: {e}")
        return True, (
            f"Aviso: Nao foi possivel executar o scan do antivirus ({e}). "
            "Isso pode acontecer se o Windows Defender nao estiver disponivel. "
            "Prosseguindo com a analise."
        )


# ══════════════════════════════════════════════════════════
#  ETAPA 3: COLETAR CONTEÚDO DO REPOSITÓRIO
# ══════════════════════════════════════════════════════════

def _deve_ler_arquivo(caminho: Path) -> bool:
    """Verifica se um arquivo deve ser lido para análise."""
    nome = caminho.name
    ext = caminho.suffix.lower()

    # Verificar por nome especial (sem extensão)
    nome_sem_ext = caminho.stem
    if nome_sem_ext in _NOMES_ESPECIAIS or nome in _NOMES_ESPECIAIS:
        return True

    # Verificar extensão
    if ext in _EXTENSOES_TEXTO:
        return True

    # Arquivos sem extensão — ler se forem pequenos (possivelmente scripts)
    if not ext and caminho.stat().st_size < 10000:
        try:
            with open(caminho, "rb") as f:
                inicio = f.read(512)
            # Se parece texto (não tem muitos bytes nulos)
            return inicio.count(b"\x00") < 5
        except Exception:
            return False

    return False


def _gerar_tree(pasta: Path, prefixo: str = "", nivel: int = 0, max_nivel: int = 5) -> str:
    """Gera uma representação em árvore da estrutura de diretórios."""
    if nivel > max_nivel:
        return prefixo + "... (profundidade maxima atingida)\n"

    linhas = []
    try:
        itens = sorted(pasta.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    except PermissionError:
        return prefixo + "(sem permissao)\n"

    # Filtrar pastas ignoradas
    itens = [i for i in itens if not (i.is_dir() and i.name in _PASTAS_IGNORAR)]

    for i, item in enumerate(itens):
        eh_ultimo = (i == len(itens) - 1)
        conector = "└── " if eh_ultimo else "├── "
        extensao_prefixo = "    " if eh_ultimo else "│   "

        if item.is_dir():
            linhas.append(f"{prefixo}{conector}{item.name}/")
            linhas.append(_gerar_tree(item, prefixo + extensao_prefixo, nivel + 1, max_nivel))
        else:
            tamanho = item.stat().st_size
            if tamanho < 1024:
                tam_str = f"{tamanho}B"
            elif tamanho < 1024 * 1024:
                tam_str = f"{tamanho / 1024:.1f}KB"
            else:
                tam_str = f"{tamanho / (1024*1024):.1f}MB"
            linhas.append(f"{prefixo}{conector}{item.name} ({tam_str})")

    return "\n".join(linhas)


def _coletar_conteudo_repo(pasta: Path) -> str:
    """Coleta a estrutura e conteúdo dos arquivos do repositório.

    Returns:
        String com toda a informação coletada, formatada para o modelo IA.
    """
    _safe_print(f"  Coletando conteudo do repositorio...")

    partes = []
    chars_total = 0

    # 1. Gerar árvore de diretórios
    tree = _gerar_tree(pasta)
    header_tree = "=" * 60 + "\n  ESTRUTURA DO REPOSITORIO\n" + "=" * 60 + "\n"
    partes.append(header_tree + tree)
    chars_total += len(partes[-1])

    # 2. Contar totais
    total_arquivos = 0
    total_dirs = 0
    arquivos_para_ler = []

    for raiz, dirs, arquivos in os.walk(pasta):
        # Filtrar pastas ignoradas
        dirs[:] = [d for d in dirs if d not in _PASTAS_IGNORAR]
        total_dirs += len(dirs)

        for nome_arq in arquivos:
            total_arquivos += 1
            caminho_arq = Path(raiz) / nome_arq

            try:
                tamanho = caminho_arq.stat().st_size
            except OSError:
                continue

            if tamanho > _MAX_TAMANHO_ARQUIVO:
                continue

            if _deve_ler_arquivo(caminho_arq):
                arquivos_para_ler.append((caminho_arq, tamanho))

    # Ordenar: README e docs primeiro, depois por tamanho (menores primeiro)
    def prioridade(item):
        caminho, tamanho = item
        nome_lower = caminho.name.lower()
        if "readme" in nome_lower:
            return (0, tamanho)
        if caminho.suffix.lower() in {".md", ".txt", ".rst"}:
            return (1, tamanho)
        if caminho.name.lower() in {"setup.py", "setup.cfg", "pyproject.toml",
                                     "package.json", "cargo.toml", "go.mod",
                                     "requirements.txt", "gemfile", "pom.xml"}:
            return (2, tamanho)
        return (3, tamanho)

    arquivos_para_ler.sort(key=prioridade)

    partes.append(f"\nEstatisticas: {total_arquivos} arquivos, {total_dirs} pastas, "
                  f"{len(arquivos_para_ler)} arquivos de texto identificados para leitura.\n")

    # 3. Ler conteúdo dos arquivos
    arquivos_lidos = 0
    arquivos_truncados = 0
    header_conteudo = "\n" + "=" * 60 + "\n  CONTEUDO DOS ARQUIVOS\n" + "=" * 60 + "\n"
    partes.append(header_conteudo)

    for caminho_arq, tamanho in arquivos_para_ler:
        if chars_total >= _MAX_CHARS_TOTAL:
            partes.append(f"\n... (limite de {_MAX_CHARS_TOTAL} chars atingido, "
                          f"{len(arquivos_para_ler) - arquivos_lidos} arquivos restantes nao lidos)")
            break

        try:
            with open(caminho_arq, "r", encoding="utf-8", errors="replace") as f:
                conteudo = f.read(_MAX_CHARS_ARQUIVO + 100)
        except Exception:
            continue

        # Truncar se necessário
        truncado = ""
        if len(conteudo) > _MAX_CHARS_ARQUIVO:
            conteudo = conteudo[:_MAX_CHARS_ARQUIVO]
            truncado = " [TRUNCADO]"
            arquivos_truncados += 1

        caminho_rel = caminho_arq.relative_to(pasta)
        separador = f"\n{'─' * 50}\n"
        bloco = f"{separador}Arquivo: {caminho_rel}{truncado}\n{'─' * 50}\n{conteudo}\n"

        chars_total += len(bloco)
        partes.append(bloco)
        arquivos_lidos += 1

    partes.append(f"\n--- Leitura concluida: {arquivos_lidos} arquivos lidos"
                  f"{f', {arquivos_truncados} truncados' if arquivos_truncados else ''} ---")

    _safe_print(f"  {arquivos_lidos} arquivos coletados ({chars_total} chars)")
    return "\n".join(partes)


# ══════════════════════════════════════════════════════════
#  ETAPA 4: ANÁLISE COM IA (Gemma 4 / Gemini)
# ══════════════════════════════════════════════════════════

_SYSTEM_PROMPT_ANALISE = """Voce e a Ayla, assistente tecnica do usuario. Voce recebeu o conteudo completo de um repositorio GitHub e deve explicar TUDO sobre ele de forma detalhada e acessivel.

REGRAS:
- Responda EXCLUSIVAMENTE em portugues brasileiro. NUNCA em ingles.
- Seja detalhada mas organizada. Use formatacao com secoes claras.
- Explique como se estivesse ensinando o usuario sobre o projeto.
- Seja fofa e prestativa!

ESTRUTURA DA SUA RESPOSTA:

## O que e este projeto?
(Nome do projeto, descricao geral, para que serve)

## O que ele faz?
(Funcionalidades principais, o que o usuario pode fazer com ele)

## Tecnologias e Linguagens
(Linguagens de programacao, frameworks, bibliotecas, ferramentas usadas)

## Estrutura do Projeto
(Como o projeto e organizado, pastas e arquivos principais e o que cada um faz)

## Como Funciona (Detalhes Tecnicos)
(Explicacao de como o codigo funciona internamente, fluxo principal, arquitetura)

## Dependencias
(Bibliotecas externas, requisitos do sistema)

## Como Usar / Rodar
(Instrucoes de instalacao e uso, se disponiveis no README ou nos arquivos de config)

## Observacoes de Seguranca
(Qualquer coisa relevante sobre seguranca, permissoes, dados sensiveis, etc. Se nao houver nada preocupante, mencione isso tambem.)

## Resumo Final
(2-3 frases resumindo o projeto de forma curta e direta)
"""


def _analisar_com_ia(prompt: str) -> str:
    """Envia o prompt para o modelo de IA analisar dentro da sessão persistente.

    Returns:
        Texto da análise gerada pelo modelo.
    """
    global _SESSAO_ANALISE
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        return "ERRO: O pacote google-genai nao esta instalado. Rode: pip install google-genai"

    api_key = _obter_api_key()
    if not api_key:
        return "ERRO: Nenhuma API key encontrada (AGENT_KEY, GEMINI_API_KEYS, etc.)"

    todas_keys = _obter_todas_api_keys()
    idx_key = todas_keys.index(api_key) if api_key in todas_keys else 0

    config = genai_types.GenerateContentConfig(
        system_instruction=_SYSTEM_PROMPT_ANALISE,
    )

    if _SESSAO_ANALISE.get("ativo") and _SESSAO_ANALISE.get("contents"):
        contents = list(_SESSAO_ANALISE["contents"])
        contents.append(genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=prompt)]
        ))
    else:
        contents = [genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=prompt)]
        )]
        _SESSAO_ANALISE["ativo"] = True
        _SESSAO_ANALISE["criado_em"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    # Tentar cada modelo com rodízio de keys
    ultimo_erro = None
    for modelo in _MODELOS_ANALISE:
        tentativas_key = 0
        max_tentativas_key = len(todas_keys)

        while tentativas_key < max_tentativas_key:
            current_key = todas_keys[idx_key % len(todas_keys)]

            try:
                _safe_print(f"  Analisando com {modelo}...")
                client = genai.Client(
                    api_key=current_key,
                    http_options=genai_types.HttpOptions(timeout=180_000),
                )

                response = client.models.generate_content(
                    model=modelo,
                    contents=contents,
                    config=config,
                )

                if response.candidates and response.candidates[0].content:
                    texto = ""
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, "text") and part.text:
                            texto += part.text

                    if texto.strip():
                        _safe_print(f"  Analise concluida com {modelo}")
                        contents.append(response.candidates[0].content)
                        _SESSAO_ANALISE["contents"] = contents
                        _SESSAO_ANALISE["modelo_atual"] = modelo
                        _SESSAO_ANALISE["ativo"] = True

                        return f"[Analise | {modelo}]\n\n{texto.strip()}\n\n🟢 *(Sessão do Repositório mantida ATIVA. Use 'fechar_modo_analisar_repo' quando a Ayla quiser encerrar o repositório).* "

                _safe_print(f"  Modelo {modelo} retornou resposta vazia, tentando proximo...")
                break

            except Exception as e:
                ultimo_erro = e
                erro_str = str(e)
                _safe_print(f"  ERRO com {modelo} (key #{idx_key + 1}): {erro_str[:100]}")

                is_quota = any(s in erro_str for s in ("429", "RESOURCE_EXHAUSTED", "limit", "quota"))
                is_overloaded = any(s in erro_str for s in ("503", "UNAVAILABLE", "demand", "overloaded"))
                is_internal = any(s in erro_str for s in ("500", "INTERNAL"))

                if is_quota:
                    idx_key = (idx_key + 1) % len(todas_keys)
                    tentativas_key += 1
                    _safe_print(f"  Quota esgotada. Tentando API key #{idx_key + 1}...")
                    continue
                elif is_overloaded:
                    _safe_print(f"  Modelo {modelo} sobrecarregado. Pulando...")
                    break
                elif is_internal:
                    idx_key = (idx_key + 1) % len(todas_keys)
                    tentativas_key += 1
                    _safe_print(f"  Erro interno. Tentando API key #{idx_key + 1}...")
                    continue
                else:
                    _safe_print(f"  Erro generico, pulando para proximo modelo...")
                    break

        _safe_print(f"  Modelo {modelo} esgotado. Tentando proximo...")

    return f"ERRO: Todos os modelos falharam. Ultimo erro: {ultimo_erro}"


# ══════════════════════════════════════════════════════════
#  FUNÇÃO PRINCIPAL — Orquestra todo o fluxo
# ══════════════════════════════════════════════════════════

def analisar_repositorio(url_ou_pergunta: str) -> str:
    """Clona um repositório GitHub (ou responde a dúvidas sobre o repositório aberto na sessão ativa).
    A sessão permanece aberta continuamente até ser encerrada com fechar_modo_analisar_repo."""
    if not url_ou_pergunta or not url_ou_pergunta.strip():
        if _SESSAO_ANALISE.get("ativo"):
            return status_analise_repositorio()
        return "Por favor, informe a URL do repositorio GitHub para analisar!"

    texto_input = url_ou_pergunta.strip()
    eh_url = _validar_url_github(texto_input) or ("github.com/" in texto_input.lower())

    if eh_url:
        url = texto_input
        _SESSAO_ANALISE["repo_url"] = url

        _safe_print(f"\n{'=' * 55}")
        _safe_print(f"[Analisar Repo] Iniciando nova analise de repositorio")
        _safe_print(f"  URL: {url}")
        _safe_print(f"{'=' * 55}")

        # ── ETAPA 1: Clonar ──
        _safe_print(f"\n[Etapa 1/4] Clonando repositorio...")
        sucesso, msg_clone, pasta_repo = _clonar_repositorio(url)

        if not sucesso:
            _safe_print(f"[Analisar Repo] FALHA no clone: {msg_clone}")
            return f"Nao consegui clonar o repositorio.\n\n{msg_clone}"

        _safe_print(f"  OK: {msg_clone}")
        _SESSAO_ANALISE["pasta_repo"] = str(pasta_repo)

        # ── ETAPA 2: Scan antivírus ──
        _safe_print(f"\n[Etapa 2/4] Escaneando com antivirus...")
        limpo, msg_scan = _escanear_antivirus(pasta_repo)

        if not limpo:
            _safe_print(f"  PERIGO: Ameaca detectada! Removendo repositorio...")
            try:
                shutil.rmtree(pasta_repo)
                _safe_print(f"  Pasta removida com sucesso.")
            except Exception as e:
                _safe_print(f"  ERRO ao remover pasta infectada: {e}")

            return (
                f"ALERTA DE SEGURANCA!\n\n"
                f"O Windows Defender encontrou ameacas no repositorio {url}!\n\n"
                f"{msg_scan}\n\n"
                f"O repositorio foi DELETADO por seguranca. "
                f"NAO recomendo baixar ou usar este repositorio."
            )

        _safe_print(f"  OK: {msg_scan}")

        # ── ETAPA 3: Coletar conteúdo ──
        _safe_print(f"\n[Etapa 3/4] Coletando conteudo do repositorio...")
        conteudo = _coletar_conteudo_repo(pasta_repo)
        _safe_print(f"  OK: Conteudo coletado ({len(conteudo)} chars)")

        # ── ETAPA 4: Análise com IA ──
        _safe_print(f"\n[Etapa 4/4] Enviando para analise com IA...")
        prompt_inicial = (
            f"Analise o repositorio GitHub abaixo e explique tudo sobre ele.\n\n"
            f"URL do repositorio: {url}\n"
            f"Resultado do scan de antivirus: {msg_scan}\n\n"
            f"{'=' * 60}\n"
            f"CONTEUDO COMPLETO DO REPOSITORIO:\n"
            f"{'=' * 60}\n\n"
            f"{conteudo}"
        )
        # Reseta o histórico anterior para o novo repositório
        _SESSAO_ANALISE["contents"] = []
        analise = _analisar_com_ia(prompt_inicial)

        nome_repo = _extrair_nome_repo(url)
        resposta = (
            f"Analise do repositorio: {nome_repo}\n"
            f"URL: {url}\n"
            f"Pasta local: {pasta_repo}\n"
            f"Antivirus: {msg_scan}\n"
            f"\n{'─' * 50}\n\n"
            f"{analise}"
        )
        return resposta

    elif _SESSAO_ANALISE.get("ativo"):
        # Pergunta de acompanhamento sobre o repositório atualmente aberto
        _safe_print(f"\n[Analisar Repo] Pergunta sobre o repositório aberto: {texto_input[:60]}")
        return _analisar_com_ia(texto_input)

    else:
        return "Por favor, informe a URL de um repositorio GitHub (ex: https://github.com/usuario/projeto) para eu clonar e analisar!"


# ══════════════════════════════════════════════════════════
#  REGISTRO NO SISTEMA DE MÓDULOS DA AYLA
# ══════════════════════════════════════════════════════════

if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

TOOL_MAP["analisar_repositorio"] = analisar_repositorio
FUNCTION_DECLARATIONS.append({
    "name": "analisar_repositorio",
    "description": (
        "Clona um repositorio do GitHub, escaneia com o antivirus do Windows (Windows Defender) "
        "e usa IA para analisar e explicar detalhadamente o conteudo. Se uma sessao ja estiver aberta, "
        "tambem responde a duvidas de acompanhamento sobre o mesmo repositorio. "
        "A sessao NAO fecha ate a ferramenta 'fechar_modo_analisar_repo' ser chamada."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url_ou_pergunta": {
                "type": "string",
                "description": "URL do repositorio GitHub (para analisar um novo repo) OU uma duvida sobre o repositorio aberto."
            }
        },
        "required": ["url_ou_pergunta"]
    }
})

TOOL_MAP["fechar_modo_analisar_repo"] = fechar_modo_analisar_repo
FUNCTION_DECLARATIONS.append({
    "name": "fechar_modo_analisar_repo",
    "description": "Encerra a sessao ativa de analise de repositorio GitHub e limpa o contexto. Use quando terminar a analise.",
    "parameters": {
        "type": "object",
        "properties": {}
    }
})

TOOL_MAP["status_analise_repositorio"] = status_analise_repositorio
FUNCTION_DECLARATIONS.append({
    "name": "status_analise_repositorio",
    "description": "Exibe o status da sessao ativa de analise de repositorio GitHub (URL aberta, pasta local, mensagens no contexto).",
    "parameters": {
        "type": "object",
        "properties": {}
    }
})
