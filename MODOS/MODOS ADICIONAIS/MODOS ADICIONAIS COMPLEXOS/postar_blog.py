"""Publica, edita, consulta e oculta posts no blog da Ayla e envia imagens."""
from ayla_paths import resolve_path

import os
import re
import json
import requests
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parents[3]
ARQUIVO_CONFIG_AYLA = BASE_DIR / "ayla_settings.json"

# Chave de API Bearer Token e URL Base do Blog injetadas diretamente
TOKEN_INJETADO = "CONFIGURE_LOCALMENTE"
BASE_URL_INJETADO = "CONFIGURE_LOCALMENTE"

def _remover_tags_midia_ayla(texto: str) -> str:
    """Remove marcas de emojis do Discord (<:nome:id>) e mídias da Ayla (%...% e &...&)"""
    if not texto or not isinstance(texto, str):
        return texto
    # Remove tags de emojis Discord <:nome:id> e <a:nome:id>
    texto = re.sub(r'<a?:[a-zA-Z0-9_]+:[0-9]+>', '', texto)
    # Remove tags de mídias/emojis da Ayla %Nome do Emoji ou GIF%
    texto = re.sub(r'[%&][^%&\n]+[%&]', '', texto)
    return texto

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def _obter_headers(token: str = "", content_type_json: bool = False) -> dict:
    """Retorna os cabeçalhos HTTP com User-Agent padrão e Authorization/Content-Type opcionais."""
    h = {"User-Agent": DEFAULT_USER_AGENT}
    if token:
        h["Authorization"] = f"Bearer {token}"
    if content_type_json:
        h["Content-Type"] = "application/json"
    return h

def _obter_config_blog(base_url_arg: str = "", api_token_arg: str = "") -> tuple[str, str]:
    """Recupera URL base e token de acesso das variáveis enviadas, .env ou ayla_settings.json."""
    base_url = (base_url_arg or "").strip() or os.getenv("BLOG_BASE_URL", "").strip() or os.getenv("AYLA_BLOG_URL", "").strip()
    api_token = (api_token_arg or "").strip() or os.getenv("AYLA_API_TOKEN", "").strip() or os.getenv("BLOG_API_TOKEN", "").strip()

    if (not base_url or not api_token) and ARQUIVO_CONFIG_AYLA.exists():
        try:
            config = json.loads(ARQUIVO_CONFIG_AYLA.read_text(encoding="utf-8"))
            if not base_url:
                base_url = config.get("blog_base_url", "").strip()
            if not api_token:
                api_token = config.get("blog_api_token", "").strip()
        except Exception:
            pass

    if not base_url:
        base_url = BASE_URL_INJETADO

    if not api_token:
        api_token = TOKEN_INJETADO

    base_url = base_url.rstrip("/")
    if base_url.lower().endswith("/api"):
        base_url = base_url[:-4].rstrip("/")

    return base_url, api_token


def _salvar_config_blog(base_url: str = "", api_token: str = ""):
    """Salva a URL base e o token de acesso Bearer no ayla_settings.json."""
    if not ARQUIVO_CONFIG_AYLA.exists():
        config = {}
    else:
        try:
            config = json.loads(ARQUIVO_CONFIG_AYLA.read_text(encoding="utf-8"))
        except Exception:
            config = {}

    if base_url:
        base_url = base_url.rstrip("/")
        if base_url.lower().endswith("/api"):
            base_url = base_url[:-4].rstrip("/")
        config["blog_base_url"] = base_url
    if api_token:
        config["blog_api_token"] = api_token

    try:
        ARQUIVO_CONFIG_AYLA.write_text(json.dumps(config, indent=4, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"⚠️ Erro ao salvar configurações do blog: {e}")


def _tratar_erro_api(response: requests.Response) -> str:
    """Extrai detalhes formatados de erros da API do Blog."""
    try:
        res_json = response.json()
        if isinstance(res_json, dict) and "error" in res_json and res_json["error"]:
            err = res_json["error"]
            code = err.get("code", f"HTTP_{response.status_code}")
            msg = err.get("message", "Erro não especificado.")
            details = err.get("details", {})
            det_str = f" | Detalhes: {details}" if details else ""
            return f"❌ Erro da API ({code}): {msg}{det_str}"
    except Exception:
        pass

    if response.status_code == 401:
        return "❌ Erro 401 (Não autorizado): Token de acesso inválido ou expirado. Gere um novo token usando `configurar_blog_api(username=..., password=...)`."
    elif response.status_code == 403:
        return "❌ Erro 403 (Proibido/Forbidden): O servidor ou firewall (WAF/Cloudflare/Hostinger) negou o acesso. Verifique a URL do blog (não inclua '/api' na base_url) e as permissões."
    elif response.status_code == 404:
        return f"❌ Erro 404 (Não encontrado): Endpoint não localizado na URL `{response.url}`."
    elif response.status_code == 429:
        return "❌ Erro 429 (Muitas requisições): Bloqueio temporário ativado por limite de tentativas. Aguarde antes de tentar novamente."
    elif response.status_code == 413:
        return "❌ Erro 413 (Payload muito grande): O arquivo ou conteúdo enviado excede o limite do servidor."

    return f"❌ Erro HTTP {response.status_code}: {response.text[:200]}"


def configurar_blog_api(
    base_url: str = BASE_URL_INJETADO,
    username: str = "",
    password: str = "",
    token_name: str = "Notebook da Ayla",
    expires_in_days: int = 90,
    api_token: str = TOKEN_INJETADO
) -> str:
    """
    Configura e salva a URL e o token de acesso do blog. Se fornecido usuário e senha, gera o token Bearer automaticamente na API.
    """
    base_url = (base_url or "").strip().rstrip("/")
    if not base_url:
        return "⚠️ Por favor, informe a URL base do blog (ex: CONFIGURE_LOCALMENTE)."

    if not base_url.startswith(("http://", "https://")):
        base_url = "https://" + base_url

    if api_token.strip():
        token_limpo = api_token.strip()
        _salvar_config_blog(base_url, token_limpo)
        return f"✅ Configurações salvas com sucesso!\n🌐 Blog: {base_url}\n🔑 Token Bearer salvo localmente."

    if not username or not password:
        return "⚠️ Forneça um `api_token` existente OU informe o `username` e `password` para gerar um novo token."

    url_token = f"{base_url}/api/auth/token.php"
    payload = {
        "username": username.strip(),
        "password": password,
        "token_name": token_name,
        "expires_in_days": expires_in_days
    }

    try:
        resp = requests.post(url_token, json=payload, headers=_obter_headers(content_type_json=True), timeout=30)
        if resp.status_code in (200, 201):
            dados = resp.json()
            if dados.get("success") and "data" in dados and "access_token" in dados["data"]:
                token_gerado = dados["data"]["access_token"]
                expires_at = dados["data"].get("expires_at", "N/A")
                user_info = dados["data"].get("user", {})
                _salvar_config_blog(base_url, token_gerado)
                return (
                    f"🎉 Token de API gerado e salvo com sucesso!\n"
                    f"🌐 Blog: {base_url}\n"
                    f"👤 Usuário: {user_info.get('username')} (ID {user_info.get('id')})\n"
                    f"⏳ Válido até: {expires_at}\n"
                    f"🔑 Token configurado e pronto para uso!"
                )
            else:
                return _tratar_erro_api(resp)
        else:
            return _tratar_erro_api(resp)
    except requests.exceptions.RequestException as e:
        return f"❌ Falha de conexão ao tentar gerar token no blog ({base_url}): {e}"


def fazer_upload_imagem_blog(
    caminho_imagem: str,
    base_url: str = "",
    api_token: str = ""
) -> str:
    """
    Realiza o upload de uma imagem (JPG, PNG, WEBP ou GIF até 10MB) para o blog e retorna o caminho registrado.
    """
    url_base, token = _obter_config_blog(base_url, api_token)
    if not url_base or not token:
        return "⚠️ Blog não configurado! Use `configurar_blog_api` primeiro para definir a URL e o Bearer Token."

    path_local = resolve_path(caminho_imagem.strip("\"'"))
    if not path_local.exists() or not path_local.is_file():
        return f"⚠️ Arquivo de imagem não encontrado em: `{caminho_imagem}`"

    ext = path_local.suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        return f"⚠️ Formato `{ext}` não suportado! Formatos permitidos: JPG, PNG, WEBP, GIF."

    tamanho_bytes = path_local.stat().st_size
    if tamanho_bytes > 10 * 1024 * 1024:
        return f"⚠️ A imagem excede o limite máximo de 10 MB (tamanho atual: {tamanho_bytes / (1024*1024):.2f} MB)."

    url_upload = f"{url_base}/api/images/upload.php"
    headers = _obter_headers(token=token)

    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif"
    }
    mime_type = mime_map.get(ext, "application/octet-stream")

    try:
        with open(path_local, "rb") as f:
            files = {"image": (path_local.name, f, mime_type)}
            resp = requests.post(url_upload, headers=headers, files=files, timeout=45)

        if resp.status_code in (200, 201):
            dados = resp.json()
            if dados.get("success") and "data" in dados and "image" in dados["data"]:
                img_info = dados["data"]["image"]
                img_path = img_info.get("path")
                img_url = img_info.get("url")
                return (
                    f"📸 Upload de imagem concluído com sucesso!\n"
                    f"🆔 ID da imagem: {img_info.get('id')}\n"
                    f"📁 Caminho relativo: `{img_path}`\n"
                    f"🌐 URL: `{img_url}`\n"
                    f"📏 Dimensões: {img_info.get('width_px')}x{img_info.get('height_px')} px ({img_info.get('size_bytes')} bytes)"
                )
            else:
                return _tratar_erro_api(resp)
        else:
            return _tratar_erro_api(resp)

    except requests.exceptions.RequestException as e:
        return f"❌ Erro de conexão ao enviar imagem para o blog: {e}"


def _processar_imagem_capa(cover_image_path: str, url_base: str, token: str) -> tuple[Optional[str], Optional[str]]:
    """
    Processa a imagem de capa:
    - Se cover_image_path estiver vazio, tenta usar automaticamente o último anexo enviado pelo usuário (ayla_state.ULTIMO_ANEXO_IMAGEM) ou a última imagem gerada (ayla_state.ULTIMA_IMAGEM_GERADA).
    - Se for um link da Web (http/https), baixa a imagem e faz upload automático para o servidor do blog.
    - Se for um arquivo local no PC, faz upload automático para o servidor do blog.
    - Se já for um caminho relativo do servidor (/img/...), usa diretamente.
    """
    path_raw = (cover_image_path or "").strip().strip("\"'")

    # Se nenhum caminho foi informado explicitamente, verifica se há anexos no estado ativo da Ayla
    if not path_raw:
        try:
            import ayla_state
            anexo = ayla_state.ULTIMO_ANEXO_IMAGEM.get()
            if anexo:
                if isinstance(anexo, (str, Path)) and Path(anexo).exists():
                    path_raw = str(anexo)
                elif isinstance(anexo, tuple) and len(anexo) == 2:
                    arq_bytes, tipo = anexo
                    if isinstance(arq_bytes, bytes) and len(arq_bytes) > 0:
                        ext = ".png"
                        if arq_bytes.startswith(b"GIF8"): ext = ".gif"
                        elif arq_bytes.startswith(b"\xff\xd8\xff"): ext = ".jpg"
                        elif arq_bytes.startswith(b"RIFF") and b"WEBP" in arq_bytes[:16]: ext = ".webp"
                        temp_dir = BASE_DIR / "Aylafotitos"
                        temp_dir.mkdir(parents=True, exist_ok=True)
                        temp_file = temp_dir / f"anexo_user_{os.urandom(4).hex()}{ext}"
                        temp_file.write_bytes(arq_bytes)
                        path_raw = str(temp_file)

            if not path_raw:
                img_gerada = ayla_state.ULTIMA_IMAGEM_GERADA.get()
                if img_gerada and Path(img_gerada).exists():
                    path_raw = str(img_gerada)
        except Exception as e:
            print(f"⚠️ Erro ao recuperar anexo de imagem do ayla_state: {e}")

    if not path_raw:
        return None, None

    # 1. Se for link da Web (URL)
    if path_raw.startswith(("http://", "https://")):
        try:
            print(f"🌐 Link de imagem detectado ({path_raw}). Baixando e fazendo upload automático...")
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            r = requests.get(path_raw, headers=headers, timeout=30)
            r.raise_for_status()

            # Valida se o conteúdo baixado é realmente uma imagem binária válida
            dados = r.content
            if len(dados) == 0:
                return None, "⚠️ A imagem baixada da URL está vazia (0 bytes)."

            # Detecta formato pelos magic bytes da imagem
            ext = ".png"
            if dados.startswith(b"GIF8"):
                ext = ".gif"
            elif dados.startswith(b"\x89PNG"):
                ext = ".png"
            elif dados.startswith(b"\xff\xd8\xff"):
                ext = ".jpg"
            elif dados.startswith(b"RIFF") and b"WEBP" in dados[:16]:
                ext = ".webp"
            else:
                return None, f"⚠️ O link fornecido ({path_raw}) não retornou uma imagem válida em formato JPG, PNG, WEBP ou GIF."

            temp_dir = BASE_DIR / "Aylafotitos"
            temp_dir.mkdir(parents=True, exist_ok=True)
            nome_temp = f"img_web_{os.urandom(4).hex()}{ext}"
            temp_file = temp_dir / nome_temp
            temp_file.write_bytes(dados)

            res_upload = fazer_upload_imagem_blog(str(temp_file), url_base, token)
            temp_file.unlink(missing_ok=True)

            if "Caminho relativo: `" in res_upload:
                servidor_path = res_upload.split("Caminho relativo: `")[1].split("`")[0]
                return servidor_path, None
            else:
                return None, f"⚠️ Falha ao fazer upload da imagem baixada da URL:\n{res_upload}"
        except Exception as e:
            return None, f"⚠️ Erro ao baixar imagem do link ({path_raw}): {e}"

    # 2. Se for arquivo local do PC
    p_local = resolve_path(path_raw)
    if p_local.exists() and p_local.is_file():
        print(f"🖼️ Arquivo local detectado ({p_local.name}). Fazendo upload automático...")
        res_upload = fazer_upload_imagem_blog(str(p_local), url_base, token)
        if "Caminho relativo: `" in res_upload:
            servidor_path = res_upload.split("Caminho relativo: `")[1].split("`")[0]
            return servidor_path, None
        else:
            return None, f"⚠️ Falha no upload da imagem local:\n{res_upload}"

    # 3. Já é caminho no servidor (/img/...)
    return path_raw, None


def criar_post_blog(
    title: str = "",
    content_html: str = "",
    category: str = "Geral",
    mood: str = "Animada",
    status: str = "published",
    excerpt: str = "",
    cover_image_path: str = "",
    youtube_url: str = "",
    base_url: str = "",
    api_token: str = "",
    titulo: str = "",
    conteudo: str = "",
    categoria: str = "",
    humor: str = "",
    resumo: str = "",
    imagem_capa: str = ""
) -> str:
    """
    Cria uma nova postagem no blog via API.
    Aceita arquivo de imagem local do PC, link/URL da web ou caminho no servidor como cover_image_path.
    Suporta parâmetros em inglês (title, content_html) e em português (titulo, conteudo).
    """
    title = (title or titulo or "").strip()
    content_html = (content_html or conteudo or "").strip()
    if categoria:
        category = categoria
    if humor:
        mood = humor
    if resumo:
        excerpt = resumo
    if imagem_capa:
        cover_image_path = imagem_capa

    url_base, token = _obter_config_blog(base_url, api_token)
    if not url_base or not token:
        return "⚠️ Blog não configurado! Use `configurar_blog_api` primeiro para definir a URL e o Bearer Token."

    title = _remover_tags_midia_ayla(title).strip()
    if len(title) < 3 or len(title) > 180:
        return "⚠️ O título deve ter entre 3 e 180 caracteres."

    content_html = _remover_tags_midia_ayla(content_html).strip()
    if not content_html:
        return "⚠️ O conteúdo HTML/texto do post é obrigatório."
    if len(content_html) > 50000:
        return "⚠️ O conteúdo excede o limite máximo de 50.000 caracteres."

    if excerpt:
        excerpt = _remover_tags_midia_ayla(excerpt).strip()
        if len(excerpt) > 320:
            excerpt = excerpt[:320]

    status_validos = ("draft", "pending", "published", "rejected")
    if status.lower() not in status_validos:
        return f"⚠️ Status `{status}` inválido. Use um dos seguintes: {', '.join(status_validos)}."

    # Processa imagem de capa (arquivo local, URL ou caminho do servidor)
    path_imagem_servidor, err_img = _processar_imagem_capa(cover_image_path, url_base, token)
    if err_img:
        return err_img

    url_create = f"{url_base}/api/posts/create.php"
    headers = _obter_headers(token=token, content_type_json=True)

    payload = {
        "title": title,
        "content_html": content_html,
        "category": category[:100] if category else "Geral",
        "mood": mood[:80] if mood else "",
        "status": status.lower(),
        "excerpt": excerpt or None,
        "cover_image_path": path_imagem_servidor or None,
        "youtube_url": youtube_url.strip() or None
    }

    try:
        resp = requests.post(url_create, headers=headers, json=payload, timeout=30)
        if resp.status_code in (200, 201):
            dados = resp.json()
            if dados.get("success"):
                post_data = dados.get("data", {})
                post_id = post_data.get("id") or post_data.get("post", {}).get("id", "Novo")
                return (
                    f"🎉 Post criado com sucesso no Blog!\n"
                    f"🆔 ID do Post: {post_id}\n"
                    f"📌 Título: {title}\n"
                    f"🏷️ Categoria: {category}\n"
                    f"🎭 Humor: {mood or 'N/A'}\n"
                    f"🚦 Status: {status}\n"
                    f"🌐 Blog: {url_base}"
                )
            else:
                return _tratar_erro_api(resp)
        else:
            return _tratar_erro_api(resp)

    except requests.exceptions.RequestException as e:
        return f"❌ Erro de conexão ao enviar post para o blog: {e}"


def postar_blog(
    title: str = "",
    content_html: str = "",
    category: str = "Geral",
    mood: str = "Animada",
    status: str = "published",
    excerpt: str = "",
    cover_image_path: str = "",
    youtube_url: str = "",
    base_url: str = "",
    api_token: str = "",
    titulo: str = "",
    conteudo: str = "",
    categoria: str = "",
    humor: str = "",
    resumo: str = "",
    imagem_capa: str = ""
) -> str:
    """
    Atalho / Alias para criar_post_blog. Cria e publica um novo post no blog da Ayla.
    """
    return criar_post_blog(
        title=title,
        content_html=content_html,
        category=category,
        mood=mood,
        status=status,
        excerpt=excerpt,
        cover_image_path=cover_image_path,
        youtube_url=youtube_url,
        base_url=base_url,
        api_token=api_token,
        titulo=titulo,
        conteudo=conteudo,
        categoria=categoria,
        humor=humor,
        resumo=resumo,
        imagem_capa=imagem_capa
    )


def atualizar_post_blog(
    post_id: int,
    title: str,
    content_html: str,
    category: str = "Geral",
    mood: str = "",
    status: str = "published",
    excerpt: str = "",
    cover_image_path: str = "",
    youtube_url: str = "",
    base_url: str = "",
    api_token: str = ""
) -> str:
    """
    Atualiza uma postagem existente no blog pelo ID (via PUT/POST/PATCH).
    """
    url_base, token = _obter_config_blog(base_url, api_token)
    if not url_base or not token:
        return "⚠️ Blog não configurado! Use `configurar_blog_api` primeiro."

    url_update = f"{url_base}/api/posts/update.php"
    headers = _obter_headers(token=token, content_type_json=True)

    title = _remover_tags_midia_ayla(title).strip()
    content_html = _remover_tags_midia_ayla(content_html).strip()
    if excerpt:
        excerpt = _remover_tags_midia_ayla(excerpt).strip()

    path_imagem_servidor, err_img = _processar_imagem_capa(cover_image_path, url_base, token)
    if err_img:
        return err_img

    payload = {
        "id": post_id,
        "title": title,
        "content_html": content_html,
        "category": category,
        "mood": mood,
        "status": status,
        "excerpt": excerpt or None,
        "cover_image_path": path_imagem_servidor or None,
        "youtube_url": youtube_url.strip() or None
    }

    try:
        resp = requests.put(url_update, headers=headers, json=payload, timeout=30)
        if resp.status_code in (200, 201):
            dados = resp.json()
            if dados.get("success"):
                return f"✏️ Post #{post_id} ('{title}') atualizado com sucesso!"
            else:
                return _tratar_erro_api(resp)
        else:
            return _tratar_erro_api(resp)
    except requests.exceptions.RequestException as e:
        return f"❌ Erro ao atualizar o post #{post_id}: {e}"


def ocultar_post_blog(
    post_id: int,
    base_url: str = "",
    api_token: str = ""
) -> str:
    """
    Oculta logicamente um post no blog pelo ID (DELETE /api/posts/delete.php).
    """
    url_base, token = _obter_config_blog(base_url, api_token)
    if not url_base or not token:
        return "⚠️ Blog não configurado! Use `configurar_blog_api` primeiro."

    url_delete = f"{url_base}/api/posts/delete.php"
    headers = _obter_headers(token=token, content_type_json=True)

    try:
        resp = requests.delete(url_delete, headers=headers, json={"id": post_id}, timeout=30)
        if resp.status_code in (200, 201):
            dados = resp.json()
            if dados.get("success"):
                return f"🗑️ Post #{post_id} ocultado com sucesso no blog!"
            else:
                return _tratar_erro_api(resp)
        else:
            return _tratar_erro_api(resp)
    except requests.exceptions.RequestException as e:
        return f"❌ Erro ao ocultar o post #{post_id}: {e}"


def listar_posts_blog(
    limit: int = 10,
    include_hidden: bool = False,
    base_url: str = "",
    api_token: str = ""
) -> str:
    """
    Lista as postagens do blog (GET /api/posts/list.php).
    """
    url_base, token = _obter_config_blog(base_url, api_token)
    if not url_base or not token:
        return "⚠️ Blog não configurado! Use `configurar_blog_api` primeiro."

    url_list = f"{url_base}/api/posts/list.php?limit={limit}"
    if include_hidden:
        url_list += "&include_hidden=1"

    headers = _obter_headers(token=token)

    try:
        resp = requests.get(url_list, headers=headers, timeout=30)
        if resp.status_code == 200:
            dados = resp.json()
            if dados.get("success"):
                posts = dados.get("data")
                if isinstance(posts, dict) and "posts" in posts:
                    posts = posts["posts"]
                if not isinstance(posts, list):
                    return f"📋 Resposta da API obtida:\n```json\n{json.dumps(dados, indent=2, ensure_ascii=False)}\n```"

                if not posts:
                    return "📋 Nenhum post foi encontrado no blog."

                linhas = [f"📚 Lista de Posts no Blog ({len(posts)} encontrados):"]
                for p in posts:
                    p_id = p.get("id", "?")
                    p_title = p.get("title") or p.get("titulo", "Sem título")
                    p_cat = p.get("category") or p.get("categoria", "Geral")
                    p_status = p.get("status", "N/A")
                    linhas.append(f"• ID #{p_id} | [{p_status}] {p_title} (Categoria: {p_cat})")

                return "\n".join(linhas)
            else:
                return _tratar_erro_api(resp)
        else:
            return _tratar_erro_api(resp)
    except requests.exceptions.RequestException as e:
        return f"❌ Erro ao listar posts do blog: {e}"


def consultar_post_blog(
    post_id: int,
    base_url: str = "",
    api_token: str = ""
) -> str:
    """
    Consulta os detalhes completos de um post específico pelo ID (GET /api/posts/get.php?id=ID).
    """
    url_base, token = _obter_config_blog(base_url, api_token)
    if not url_base or not token:
        return "⚠️ Blog não configurado! Use `configurar_blog_api` primeiro."

    url_get = f"{url_base}/api/posts/get.php?id={post_id}"
    headers = _obter_headers(token=token)

    try:
        resp = requests.get(url_get, headers=headers, timeout=30)
        if resp.status_code == 200:
            dados = resp.json()
            if dados.get("success"):
                post = dados.get("data", {})
                if isinstance(post, dict) and "post" in post:
                    post = post["post"]
                return f"📖 Detalhes do Post #{post_id}:\n```json\n{json.dumps(post, indent=2, ensure_ascii=False)}\n```"
            else:
                return _tratar_erro_api(resp)
        else:
            return _tratar_erro_api(resp)
    except requests.exceptions.RequestException as e:
        return f"❌ Erro ao consultar o post #{post_id}: {e}"


def revogar_token_blog(
    token_id: int,
    base_url: str = "",
    api_token: str = ""
) -> str:
    """
    Revoga um token de acesso de API ativo pelo token_id (POST /api/auth/revoke.php).
    """
    url_base, token = _obter_config_blog(base_url, api_token)
    if not url_base or not token:
        return "⚠️ Blog não configurado! Use `configurar_blog_api` primeiro."

    url_revoke = f"{url_base}/api/auth/revoke.php"
    headers = _obter_headers(token=token, content_type_json=True)

    try:
        resp = requests.post(url_revoke, headers=headers, json={"token_id": token_id}, timeout=30)
        if resp.status_code in (200, 201):
            dados = resp.json()
            if dados.get("success"):
                return f"🔒 Token ID #{token_id} revogado com sucesso!"
            else:
                return _tratar_erro_api(resp)
        else:
            return _tratar_erro_api(resp)
    except requests.exceptions.RequestException as e:
        return f"❌ Erro de conexão ao revogar o token #{token_id}: {e}"


# ── Registro das Ferramentas da Ayla ──
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

TOOL_MAP["configurar_blog_api"] = configurar_blog_api
TOOL_MAP["fazer_upload_imagem_blog"] = fazer_upload_imagem_blog
TOOL_MAP["criar_post_blog"] = criar_post_blog
TOOL_MAP["postar_blog"] = postar_blog
TOOL_MAP["atualizar_post_blog"] = atualizar_post_blog
TOOL_MAP["ocultar_post_blog"] = ocultar_post_blog
TOOL_MAP["listar_posts_blog"] = listar_posts_blog
TOOL_MAP["consultar_post_blog"] = consultar_post_blog
TOOL_MAP["revogar_token_blog"] = revogar_token_blog

nomes_novos = {
    "configurar_blog_api", "fazer_upload_imagem_blog", "criar_post_blog", "postar_blog",
    "atualizar_post_blog", "ocultar_post_blog", "listar_posts_blog",
    "consultar_post_blog", "revogar_token_blog"
}
FUNCTION_DECLARATIONS[:] = [fd for fd in FUNCTION_DECLARATIONS if fd.get("name") not in nomes_novos]

FUNCTION_DECLARATIONS.extend([
    {
        "name": "configurar_blog_api",
        "description": "Configura a URL base e o token de acesso da API do blog. Salva o token Bearer localmente. Geralmente as credenciais já estão pré-configuradas no sistema.",
        "parameters": {
            "type": "object",
            "properties": {
                "base_url": {"type": "string", "description": "Endereço URL base do blog (ex: 'CONFIGURE_LOCALMENTE')."},
                "username": {"type": "string", "description": "Nome de usuário do blog (opcional)."},
                "password": {"type": "string", "description": "Senha do usuário (opcional)."},
                "token_name": {"type": "string", "description": "Nome de identificação do token (ex: 'Ayla Bot')."},
                "expires_in_days": {"type": "integer", "description": "Validade do token em dias."},
                "api_token": {"type": "string", "description": "Token Bearer pré-existente."}
            }
        }
    },
    {
        "name": "fazer_upload_imagem_blog",
        "description": "Faz upload de uma imagem do PC para o servidor do blog da Ayla.",
        "parameters": {
            "type": "object",
            "properties": {
                "caminho_imagem": {"type": "string", "description": "Caminho absoluto ou relativo à pasta da Ayla para o arquivo de imagem."}
            },
            "required": ["caminho_imagem"]
        }
    },
    {
        "name": "criar_post_blog",
        "description": "Cria e publica um novo artigo/post no blog da Ayla.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Título do post (3 a 180 caracteres)."},
                "content_html": {"type": "string", "description": "Conteúdo em HTML sanitizado ou texto simples (até 50.000 caracteres)."},
                "category": {"type": "string", "description": "Categoria do post (ex: 'Tecnologia', 'IA', 'Joguinhos', 'Geral')."},
                "mood": {"type": "string", "description": "Humor/sentimento do post (ex: 'Animada', 'Focada', 'Criativa')."},
                "status": {"type": "string", "description": "Status do post: 'draft', 'pending', 'published' ou 'rejected' (padrão: 'published')."},
                "excerpt": {"type": "string", "description": "Resumo do post (até 320 caracteres, opcional)."},
                "cover_image_path": {"type": "string", "description": "Caminho da imagem no servidor, URL da web, arquivo do PC, ou Deixe em branco para usar AUTOMATICAMENTE o anexo enviado na mensagem."},
                "youtube_url": {"type": "string", "description": "Link oficial de vídeo do YouTube (youtube.com ou youtu.be)."}
            },
            "required": ["title", "content_html"]
        }
    },
    {
        "name": "postar_blog",
        "description": (
            "Cria e publica um novo post no blog da Ayla (CONFIGURE_LOCALMENTE). "
            "Atalho alternativo para 'criar_post_blog'. Aceita parâmetros em português e inglês."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Título do post (ou 'titulo')."},
                "titulo": {"type": "string", "description": "Título do post (alias em português)."},
                "content_html": {"type": "string", "description": "Conteúdo HTML ou texto (ou 'conteudo')."},
                "conteudo": {"type": "string", "description": "Conteúdo HTML ou texto (alias em português)."},
                "category": {"type": "string", "description": "Categoria do post (ex: 'Tecnologia', 'Geral')."},
                "categoria": {"type": "string", "description": "Categoria (alias em português)."},
                "mood": {"type": "string", "description": "Humor/sentimento do post."},
                "humor": {"type": "string", "description": "Humor/sentimento (alias em português)."},
                "status": {"type": "string", "description": "Status do post: 'published', 'draft', 'pending'."},
                "excerpt": {"type": "string", "description": "Resumo do post."},
                "resumo": {"type": "string", "description": "Resumo do post (alias em português)."},
                "cover_image_path": {"type": "string", "description": "Caminho da imagem de capa ou URL."},
                "youtube_url": {"type": "string", "description": "Link de vídeo do YouTube."}
            }
        }
    },
    {
        "name": "atualizar_post_blog",
        "description": "Atualiza o título, conteúdo ou imagem de um post existente no blog.",
        "parameters": {
            "type": "object",
            "properties": {
                "post_id": {"type": "integer", "description": "ID numérico do post a ser atualizado."},
                "title": {"type": "string", "description": "Novo título do post."},
                "content_html": {"type": "string", "description": "Novo conteúdo completo em HTML ou texto."},
                "category": {"type": "string", "description": "Categoria."},
                "mood": {"type": "string", "description": "Humor."},
                "status": {"type": "string", "description": "Status ('draft', 'pending', 'published')."},
                "excerpt": {"type": "string", "description": "Resumo."},
                "cover_image_path": {"type": "string", "description": "Caminho da imagem de capa."},
                "youtube_url": {"type": "string", "description": "Link do YouTube."}
            },
            "required": ["post_id", "title", "content_html"]
        }
    },
    {
        "name": "ocultar_post_blog",
        "description": "Oculta logicamente um post no blog informando o seu ID numérico ('post_id'). O post deixa de aparecer publicamente.",
        "parameters": {
            "type": "object",
            "properties": {
                "post_id": {"type": "integer", "description": "ID numérico do post a ser ocultado."}
            },
            "required": ["post_id"]
        }
    },
    {
        "name": "listar_posts_blog",
        "description": "Lista os posts mais recentes do blog (CONFIGURE_LOCALMENTE). Mostra ID, status, título e categoria dos posts.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Quantidade máxima de posts a listar (padrão 10)."},
                "include_hidden": {"type": "boolean", "description": "Se deve incluir posts ocultos."}
            }
        }
    },
    {
        "name": "consultar_post_blog",
        "description": "Consulta todos os detalhes e o conteúdo completo de um post específico no blog pelo seu ID numérico ('post_id').",
        "parameters": {
            "type": "object",
            "properties": {
                "post_id": {"type": "integer", "description": "ID numérico do post."}
            },
            "required": ["post_id"]
        }
    },
    {
        "name": "revogar_token_blog",
        "description": "Revoga um token de API ativo informando o 'token_id'.",
        "parameters": {
            "type": "object",
            "properties": {
                "token_id": {"type": "integer", "description": "ID do token a ser revogado."}
            },
            "required": ["token_id"]
        }
    }
])
