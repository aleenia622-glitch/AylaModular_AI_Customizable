import os
import sys
import json
import time
import requests
import webbrowser
import threading
import runpy
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv


if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = Path(__file__).parent.resolve()
load_dotenv(dotenv_path=BASE_DIR / ".env")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
if "#" in DISCORD_TOKEN:
    DISCORD_TOKEN = DISCORD_TOKEN.split("#")[0].strip()

DISCORD_OWNER_ID = os.getenv("DISCORD_OWNER_ID", "CONFIGURE_LOCALMENTE")
HISTORY_FILE = BASE_DIR / "ayla_interaction_history.jsonl"

PORT = 8888

# CACHES EM MEMÓRIA PARA RESOLVER USUÁRIOS E CANAIS DA DISCORD API
RESOLVED_USERS = {}
RESOLVED_CHANNELS = {}
RESOLVED_GUILDS = {}

_HISTORY_CACHE = {"mtime": 0, "channels": {}, "messages": {}}
_EXECUTOR = ThreadPoolExecutor(max_workers=10)


def fetch_discord_api(endpoint, method="GET", body=None):
    url = f"https://discord.com/api/v10{endpoint}"
    headers = {
        "Authorization": f"Bot {DISCORD_TOKEN}",
        "User-Agent": "AylaControlCenter/1.0"
    }
    if body is not None or method == "POST":
        headers["Content-Type"] = "application/json"

    try:
        if method == "GET":
            res = requests.get(url, headers=headers, timeout=3)
        elif method == "POST":
            res = requests.post(url, headers=headers, json=body, timeout=3)
        elif method == "DELETE":
            res = requests.delete(url, headers=headers, timeout=3)
        else:
            return None, 400
        
        if res.status_code == 204:
            return {}, 204

        try:
            data = res.json()
        except Exception:
            data = {}
        return data, res.status_code
    except Exception as e:
        return {"error": str(e)}, 500


def resolve_guild_name(guild_id):
    if not guild_id:
        return None
    if guild_id in RESOLVED_GUILDS:
        return RESOLVED_GUILDS[guild_id]
    
    g_data, status = fetch_discord_api(f"/guilds/{guild_id}")
    if status == 200 and isinstance(g_data, dict) and "name" in g_data:
        RESOLVED_GUILDS[guild_id] = g_data["name"]
        return g_data["name"]
    
    RESOLVED_GUILDS[guild_id] = f"Servidor {guild_id}"
    return RESOLVED_GUILDS[guild_id]


def resolve_channel_info(channel_id):
    if not channel_id or channel_id == "None":
        return {"name": "Sistema / Local", "guild_name": None}
    
    if channel_id in RESOLVED_CHANNELS:
        return RESOLVED_CHANNELS[channel_id]
    
    c_data, status = fetch_discord_api(f"/channels/{channel_id}")
    if status == 200 and isinstance(c_data, dict):
        c_name = c_data.get("name")
        c_type = c_data.get("type")
        guild_id = c_data.get("guild_id")
        guild_name = resolve_guild_name(guild_id) if guild_id else None
        
        display_name = f"#{c_name}" if c_name else f"Canal #{channel_id}"
        if c_type == 1:
            display_name = f"DM Privada ({channel_id})"
            
        info = {
            "id": channel_id,
            "name": display_name,
            "guild_id": guild_id,
            "guild_name": guild_name
        }
        RESOLVED_CHANNELS[channel_id] = info
        return info
    
    info = {"id": channel_id, "name": f"Canal #{channel_id}", "guild_name": None}
    RESOLVED_CHANNELS[channel_id] = info
    return info


def resolve_user_info(user_id):
    if not user_id or user_id == "None":
        return {
            "id": "0",
            "username": "sistema",
            "display_name": "Sistema",
            "avatar": "https://cdn.discordapp.com/embed/avatars/0.png"
        }
        
    if user_id == str(DISCORD_OWNER_ID):
        return {
            "id": user_id,
            "username": "Usuario",
            "display_name": "Usuario (Criadora)",
            "avatar": "https://cdn.discordapp.com/embed/avatars/1.png"
        }
        
    if user_id in RESOLVED_USERS:
        return RESOLVED_USERS[user_id]
        
    u_data, status = fetch_discord_api(f"/users/{user_id}")
    if status == 200 and isinstance(u_data, dict) and "id" in u_data:
        avatar_hash = u_data.get("avatar")
        avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png?size=128" if avatar_hash else "https://cdn.discordapp.com/embed/avatars/0.png"
        
        info = {
            "id": user_id,
            "username": u_data.get("username"),
            "global_name": u_data.get("global_name"),
            "display_name": u_data.get("global_name") or u_data.get("username"),
            "avatar": avatar_url
        }
        RESOLVED_USERS[user_id] = info
        return info
        
    info = {
        "id": user_id,
        "username": f"user_{user_id}",
        "display_name": f"Usuário ({user_id})",
        "avatar": "https://cdn.discordapp.com/embed/avatars/0.png"
    }
    RESOLVED_USERS[user_id] = info
    return info


def get_parsed_history():
    if not HISTORY_FILE.exists():
        return {}, {}
    
    current_mtime = os.path.getmtime(HISTORY_FILE)
    if _HISTORY_CACHE["mtime"] == current_mtime and _HISTORY_CACHE["channels"]:
        return _HISTORY_CACHE["channels"], _HISTORY_CACHE["messages"]
    
    channels = {}
    messages_by_key = {}
    
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            for line_idx, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    origem = item.get("origem", "Geral")
                    ch_id = str(item.get("channel_id") or "None")
                    user_id = str(item.get("user_id") or "None")
                    
                    if origem == "DM-Dona":
                        key = "DM-Dona"
                        category = "DM_DONA"
                    elif origem == "DM":
                        key = f"DM_{user_id}"
                        category = "DM"
                    elif ch_id != "None":
                        key = f"CH_{ch_id}"
                        category = "GUILD"
                    else:
                        key = f"MODE_{origem}"
                        category = "SYSTEM"
                    
                    if key not in channels:
                        channels[key] = {
                            "key": key,
                            "label": f"Conversa {key}",
                            "category": category,
                            "origem": origem,
                            "channel_id": ch_id,
                            "user_id": user_id,
                            "count": 0,
                            "last_timestamp": item.get("timestamp")
                        }
                        messages_by_key[key] = []
                    
                    channels[key]["count"] += 1
                    channels[key]["last_timestamp"] = item.get("timestamp")
                    
                    msg_obj = {
                        "id": line_idx,
                        "timestamp": item.get("timestamp"),
                        "origem": origem,
                        "user_id": user_id,
                        "channel_id": ch_id,
                        "input": item.get("input_resumo", ""),
                        "output": item.get("output_resumo", "")
                    }
                    messages_by_key[key].append(msg_obj)
                except Exception:
                    pass

        for key, c_info in channels.items():
            if c_info["category"] == "DM_DONA":
                c_info["label"] = "💖 DM com Usuario (Criadora)"
                c_info["sub_label"] = "Mensagens Diretas Privadas"
                c_info["avatar"] = "https://cdn.discordapp.com/embed/avatars/1.png"
            elif c_info["category"] == "DM":
                u_cached = RESOLVED_USERS.get(c_info["user_id"])
                disp = u_cached["display_name"] if u_cached else f"DM ({c_info['user_id']})"
                c_info["label"] = f"📬 {disp}"
                c_info["sub_label"] = f"ID: {c_info['user_id']}"
                c_info["avatar"] = u_cached["avatar"] if u_cached else None
            elif c_info["category"] == "GUILD":
                ch_cached = RESOLVED_CHANNELS.get(c_info["channel_id"])
                disp = ch_cached["name"] if ch_cached else f"Canal #{c_info['channel_id']}"
                guild_str = f"[{ch_cached['guild_name']}] " if ch_cached and ch_cached.get("guild_name") else ""
                c_info["label"] = f"💬 {guild_str}{disp}"
                c_info["sub_label"] = f"ID: {c_info['channel_id']}"
                c_info["avatar"] = None
            else:
                c_info["label"] = f"🤖 Modo {c_info['origem']}"
                c_info["sub_label"] = "Sistema Interno"
                c_info["avatar"] = None

        _HISTORY_CACHE["mtime"] = current_mtime
        _HISTORY_CACHE["channels"] = channels
        _HISTORY_CACHE["messages"] = messages_by_key
    except Exception as e:
        print("Erro ao ler histórico:", e)
        
# ══════════════════════════════════════════════════════════
#  MÓDULO DE RAG HÍBRIDO (MEMÓRIAS DA AYLA)
# ══════════════════════════════════════════════════════════
ARQUIVO_MEMORIA = BASE_DIR / "Ayla_Memoria.json"

from ayla_cerebro import (
    carregar_memoria, buscar_memorias_estruturadas,
    montar_contexto_memoria_relevante,
)

class AylaRequestHandler(BaseHTTPRequestHandler):
    def handle(self):
        try:
            super().handle()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # O navegador pode fechar/cancelar a conexão durante uma resposta.
            self.close_connection = True

    def log_message(self, format, *args):
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html_content, status=200):
        body = html_content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            html_file = BASE_DIR / "ayla_control_center.html"
            if html_file.exists():
                with open(html_file, "r", encoding="utf-8") as f:
                    self.send_html(f.read())
            else:
                self.send_html("<h1>Ayla Control Center API está online!</h1>")
            return

        if path in ["/ayla_mapa_mental.html", "/mapa", "/mapa_mental"]:
            html_file = BASE_DIR / "ayla_mapa_mental.html"
            gerador = BASE_DIR / "build_mapa_mental.py"
            fontes = (ARQUIVO_MEMORIA, gerador)
            if gerador.exists() and (not html_file.exists() or any(
                fonte.exists() and fonte.stat().st_mtime_ns > html_file.stat().st_mtime_ns
                for fonte in fontes
            )):
                runpy.run_path(str(gerador), run_name="__main__")
            if html_file.exists():
                with open(html_file, "r", encoding="utf-8") as f:
                    self.send_html(f.read())
            else:
                self.send_html("<h1>Arquivo ayla_mapa_mental.html não encontrado!</h1>", 404)
            return

        if path == "/api/me":
            data, status = fetch_discord_api("/users/@me")
            if status == 200:
                data["owner_id"] = DISCORD_OWNER_ID
            self.send_json(data, status)

        elif path == "/api/guilds":
            guilds, status = fetch_discord_api("/users/@me/guilds")
            if status != 200:
                self.send_json({"error": "Erro ao buscar servidores", "details": guilds}, status)
                return

            guilds_detalhadas = []
            for g in guilds:
                g_id = g["id"]
                detail, _ = fetch_discord_api(f"/guilds/{g_id}?with_counts=true")
                if not isinstance(detail, dict) or "id" not in detail:
                    detail = g
                
                icon_hash = detail.get("icon")
                icon_url = f"https://cdn.discordapp.com/icons/{g_id}/{icon_hash}.png?size=128" if icon_hash else None
                
                perms = int(detail.get("permissions", 0))
                is_admin = bool(perms & 0x8) or (str(detail.get("owner_id")) == str(detail.get("id")))

                guilds_detalhadas.append({
                    "id": g_id,
                    "name": detail.get("name"),
                    "icon": icon_url,
                    "owner_id": detail.get("owner_id"),
                    "approximate_member_count": detail.get("approximate_member_count", detail.get("member_count", "N/A")),
                    "approximate_presence_count": detail.get("approximate_presence_count", "N/A"),
                    "permissions": detail.get("permissions", "0"),
                    "is_admin": is_admin,
                    "description": detail.get("description")
                })
            self.send_json(guilds_detalhadas, 200)

        elif path.startswith("/api/guilds/") and path.endswith("/members"):
            parts = path.split("/")
            guild_id = parts[3]
            members, status = fetch_discord_api(f"/guilds/{guild_id}/members?limit=1000")
            if status != 200:
                self.send_json({"error": "Não foi possível buscar membros", "details": members}, status)
                return
            
            formatados = []
            for m in members:
                user = m.get("user", {})
                if not user:
                    continue
                
                u_id = user.get("id")
                avatar_hash = user.get("avatar") or m.get("avatar")
                avatar_url = f"https://cdn.discordapp.com/avatars/{u_id}/{avatar_hash}.png?size=128" if avatar_hash else "https://cdn.discordapp.com/embed/avatars/0.png"
                
                roles = m.get("roles", [])
                
                formatados.append({
                    "id": u_id,
                    "username": user.get("username"),
                    "global_name": user.get("global_name"),
                    "display_name": m.get("nick") or user.get("global_name") or user.get("username"),
                    "bot": user.get("bot", False),
                    "avatar": avatar_url,
                    "joined_at": m.get("joined_at"),
                    "roles_count": len(roles)
                })
            self.send_json(formatados, 200)

        elif path.startswith("/api/guilds/") and path.endswith("/channels"):
            parts = path.split("/")
            guild_id = parts[3]
            channels, status = fetch_discord_api(f"/guilds/{guild_id}/channels")
            if status != 200:
                self.send_json({"error": "Erro ao buscar canais", "details": channels}, status)
                return
            
            canais_filtrados = []
            for c in channels:
                if c.get("type") in [0, 2, 5]:
                    canais_filtrados.append({
                        "id": c.get("id"),
                        "name": c.get("name"),
                        "type": c.get("type"),
                        "parent_id": c.get("parent_id")
                    })
            self.send_json(canais_filtrados, 200)

        elif path == "/api/all_members":
            guilds, status = fetch_discord_api("/users/@me/guilds")
            if status != 200:
                self.send_json([], 200)
                return

            todos = {}
            for g in guilds:
                g_id = g["id"]
                g_name = g["name"]
                members, m_status = fetch_discord_api(f"/guilds/{g_id}/members?limit=1000")
                if m_status == 200 and isinstance(members, list):
                    for m in members:
                        user = m.get("user", {})
                        if not user:
                            continue
                        u_id = user.get("id")
                        avatar_hash = user.get("avatar") or m.get("avatar")
                        avatar_url = f"https://cdn.discordapp.com/avatars/{u_id}/{avatar_hash}.png?size=128" if avatar_hash else "https://cdn.discordapp.com/embed/avatars/0.png"
                        
                        RESOLVED_USERS[u_id] = {
                            "id": u_id,
                            "username": user.get("username"),
                            "global_name": user.get("global_name"),
                            "display_name": m.get("nick") or user.get("global_name") or user.get("username"),
                            "avatar": avatar_url
                        }

                        if u_id not in todos:
                            todos[u_id] = {
                                "id": u_id,
                                "username": user.get("username"),
                                "global_name": user.get("global_name"),
                                "display_name": m.get("nick") or user.get("global_name") or user.get("username"),
                                "bot": user.get("bot", False),
                                "avatar": avatar_url,
                                "guilds": [{"id": g_id, "name": g_name}]
                            }
                        else:
                            todos[u_id]["guilds"].append({"id": g_id, "name": g_name})

            self.send_json(list(todos.values()), 200)

        # -------------------------------------------------------------
        # HISTÓRICO DE INTERAÇÕES (COM LIMITE DE 100 E CONSULTA AVANÇADA)
        # -------------------------------------------------------------
        elif path == "/api/history/channels":
            channels_map, _ = get_parsed_history()
            channels_list = list(channels_map.values())
            channels_list.sort(key=lambda x: str(x.get("last_timestamp", "")), reverse=True)
            self.send_json(channels_list, 200)

        elif path == "/api/history/messages":
            key = params.get("key", [""])[0]
            limit_param = params.get("limit", ["100"])[0]
            load_all = limit_param.lower() == "all"
            limit = 100 if not load_all else 10000
            
            if not key:
                self.send_json({"error": "Chave não fornecida"}, 400)
                return
            
            _, messages_map = get_parsed_history()
            all_msgs = messages_map.get(key, [])
            total_msgs = len(all_msgs)
            
            # Pega apenas as últimas `limit` mensagens (padrão 100)
            msgs_slice = all_msgs if load_all else all_msgs[-limit:]
            
            if msgs_slice and msgs_slice[0]["channel_id"] and msgs_slice[0]["channel_id"] != "None":
                resolve_channel_info(msgs_slice[0]["channel_id"])

            msgs_enriquecidas = []
            user_ids_unicos = list(set([m["user_id"] for m in msgs_slice if m["user_id"]]))
            list(_EXECUTOR.map(resolve_user_info, user_ids_unicos))

            for m in msgs_slice:
                u_info = resolve_user_info(m["user_id"])
                ch_info = resolve_channel_info(m["channel_id"])
                
                m_copy = dict(m)
                m_copy["user_info"] = u_info
                m_copy["channel_info"] = ch_info
                msgs_enriquecidas.append(m_copy)
                
            self.send_json({
                "messages": msgs_enriquecidas,
                "total": total_msgs,
                "loaded_count": len(msgs_enriquecidas),
                "is_limited": total_msgs > len(msgs_enriquecidas)
            }, 200)

        elif path == "/api/history/search":
            q_text = params.get("q", [""])[0].lower()
            q_user = params.get("user_id", [""])[0]
            q_channel = params.get("channel_id", [""])[0]
            q_key = params.get("key", [""])[0]
            limit = int(params.get("limit", ["50"])[0])

            channels_map, messages_map = get_parsed_history()
            resultados = []
            
            for k, msg_list in messages_map.items():
                if q_key and k != q_key:
                    continue
                for m in msg_list:
                    if q_user and m["user_id"] != q_user:
                        continue
                    if q_channel and m["channel_id"] != q_channel:
                        continue
                    if q_text:
                        match_in = q_text in m["input"].lower()
                        match_out = q_text in m["output"].lower()
                        if not match_in and not match_out:
                            continue
                            
                    m_copy = dict(m)
                    m_copy["channel_key"] = k
                    resultados.append(m_copy)

            # Ordena os resultados da busca do mais recente para o mais antigo
            resultados.sort(key=lambda x: str(x.get("timestamp", "")), reverse=True)
            resultados_finais = resultados[:limit]

            user_ids_unicos = list(set([m["user_id"] for m in resultados_finais if m["user_id"]]))
            channel_ids_unicos = list(set([m["channel_id"] for m in resultados_finais if m["channel_id"] and m["channel_id"] != "None"]))
            
            list(_EXECUTOR.map(resolve_user_info, user_ids_unicos))
            list(_EXECUTOR.map(resolve_channel_info, channel_ids_unicos))

            for m in resultados_finais:
                m["user_info"] = resolve_user_info(m["user_id"])
                m["channel_info"] = resolve_channel_info(m["channel_id"])

            self.send_json({
                "query": {"text": q_text, "user_id": q_user, "channel_id": q_channel},
                "total_found": len(resultados),
                "returned_count": len(resultados_finais),
                "results": resultados_finais
            }, 200)

        elif path == "/api/rag/test":
            q_text = params.get("q", [""])[0]
            limit = int(params.get("limit", ["6"])[0])
            inc_arq = params.get("arquivadas", ["false"])[0].lower() in ["true", "1"]
            
            t0 = time.time()
            res = buscar_memorias_estruturadas(consulta=q_text, limite=limit, incluir_arquivadas=inc_arq)
            ctx = montar_contexto_memoria_relevante(consulta=q_text, limite=limit) if q_text else ""
            elapsed = round((time.time() - t0) * 1000, 2)
            
            mem_all = carregar_memoria()
            
            self.send_json({
                "query": q_text,
                "total_found": len(res),
                "total_db": len(mem_all),
                "elapsed_ms": elapsed,
                "formatted_context": ctx,
                "results": res
            }, 200)

        else:
            self.send_json({"error": "Endpoint não encontrado"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            payload = {}

        if path == "/api/rag/test":
            q_text = payload.get("query", payload.get("q", ""))
            limit = int(payload.get("limite", payload.get("limit", 6)))
            inc_arq = bool(payload.get("incluir_arquivadas", False))
            
            t0 = time.time()
            res = buscar_memorias_estruturadas(consulta=q_text, limite=limit, incluir_arquivadas=inc_arq)
            ctx = montar_contexto_memoria_relevante(consulta=q_text, limite=limit) if q_text else ""
            elapsed = round((time.time() - t0) * 1000, 2)
            
            mem_all = carregar_memoria()
            
            self.send_json({
                "query": q_text,
                "total_found": len(res),
                "total_db": len(mem_all),
                "elapsed_ms": elapsed,
                "formatted_context": ctx,
                "results": res
            }, 200)

        elif path == "/api/invite/create":
            channel_id = payload.get("channel_id")
            max_age = int(payload.get("max_age", 86400))
            max_uses = int(payload.get("max_uses", 0))
            
            if not channel_id:
                self.send_json({"error": "ID do canal não fornecido"}, 400)
                return
                
            invite_data, status = fetch_discord_api(
                f"/channels/{channel_id}/invites",
                method="POST",
                body={"max_age": max_age, "max_uses": max_uses, "unique": True}
            )
            
            if status in [200, 201]:
                code = invite_data.get("code")
                self.send_json({
                    "success": True,
                    "code": code,
                    "url": f"https://discord.gg/{code}",
                    "channel_id": channel_id,
                    "guild": invite_data.get("guild", {}).get("name")
                }, 200)
            else:
                self.send_json({"error": "Sem permissão para criar convite neste canal", "details": invite_data}, status)

        elif path == "/api/dm/send":
            user_id = payload.get("user_id")
            message = payload.get("message")
            
            if not user_id or not message:
                self.send_json({"error": "Usuário ou mensagem inválida"}, 400)
                return

            dm_channel, status = fetch_discord_api("/users/@me/channels", method="POST", body={"recipient_id": user_id})
            if status not in [200, 201]:
                self.send_json({"error": "Não foi possível abrir canal de DM com o usuário", "details": dm_channel}, status)
                return
                
            ch_id = dm_channel.get("id")
            msg_res, msg_status = fetch_discord_api(f"/channels/{ch_id}/messages", method="POST", body={"content": message})
            if msg_status in [200, 201]:
                self.send_json({"success": True, "message_id": msg_res.get("id"), "recipient_id": user_id}, 200)
            else:
                self.send_json({"error": "Erro ao enviar mensagem (usuário pode ter DMs fechadas)", "details": msg_res}, msg_status)

        elif path.startswith("/api/guilds/") and path.endswith("/leave"):
            parts = path.split("/")
            guild_id = parts[3]
            res, status = fetch_discord_api(f"/users/@me/guilds/{guild_id}", method="DELETE")
            if status in [204, 200]:
                self.send_json({"success": True, "message": "Ayla saiu do servidor com sucesso"}, 200)
            else:
                self.send_json({"error": "Erro ao sair do servidor", "details": res}, status)

        else:
            self.send_json({"error": "Endpoint POST não encontrado"}, 404)


def modo_teste_rag_cli():
    mem_all = carregar_memoria()
    total_mem = len(mem_all)
    
    print("\n" + "═" * 72)
    print("  🧠 TESTE INTERATIVO DO RAG HÍBRIDO DA AYLA (MEMÓRIAS) 🐾")
    print("═" * 72)
    print(f"  📂 Banco de Memórias: Ayla_Memoria.json | Total de memórias: {total_mem}")
    print("  💡 Digite qualquer mensagem/pergunta para testar a busca de memórias.")
    print("  ⚙️  Comandos: 'arquivadas' (alterna busca), 'limite N', 'sair' ou 'q'")
    print("═" * 72 + "\n")
    
    limite = 6
    incluir_arquivadas = False

    while True:
        try:
            prompt_input = input("🧠 Digite a mensagem para teste > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Saindo do Teste de RAG Híbrido...")
            break
            
        if not prompt_input:
            continue
            
        cmd_lower = prompt_input.lower()
        if cmd_lower in ["sair", "exit", "q", "voltar"]:
            print("👋 Encerrando modo de teste RAG.")
            break
            
        if cmd_lower == "arquivadas":
            incluir_arquivadas = not incluir_arquivadas
            status = "INCLUINDO" if incluir_arquivadas else "IGNORANDO"
            print(f"⚙️  Modo alterado: {status} memórias arquivadas.\n")
            continue
            
        if cmd_lower.startswith("limite "):
            try:
                limite = max(1, min(50, int(cmd_lower.split(" ")[1])))
                print(f"⚙️  Limite de resultados alterado para: {limite}\n")
            except ValueError:
                print("❌ Valor numérico de limite inválido.\n")
            continue
            
        t0 = time.time()
        resultados = buscar_memorias_estruturadas(
            consulta=prompt_input,
            limite=limite,
            incluir_arquivadas=incluir_arquivadas
        )
        contexto_formatado = montar_contexto_memoria_relevante(consulta=prompt_input, limite=limite)
        elapsed_ms = round((time.time() - t0) * 1000, 2)
        
        print("\n" + "─" * 72)
        print(f"🔍 PROCURANDO MEMÓRIAS PARA: \"{prompt_input}\"")
        print(f"⏱️ Tempo: {elapsed_ms}ms | Encontradas: {len(resultados)} de {total_mem} memórias")
        print("─" * 72)
        
        if not resultados:
            print("❌ Nenhuma memória atingiu a pontuação mínima de relevância (score >= 0.35).")
        else:
            for idx, item in enumerate(resultados, 1):
                reg = item["registro"]
                chave = item["chave"]
                score = item["pontuacao"]
                tipo = reg.get("tipo", "outro")
                imp = reg.get("importancia", 3)
                escopo = reg.get("escopo", "privada")
                tags = reg.get("tags", [])
                if isinstance(tags, str):
                    tags = [tags]
                valor = reg.get("Valor", "")
                
                print(f" {idx}. 🔑 CHAVE: {chave}")
                print(f"    📊 Score RAG: {score:.3f} | Tipo: {tipo} | Importância: {imp}/5 | Escopo: {escopo}")
                print(f"    🏷️ Tags: [{', '.join(tags)}]")
                print(f"    💬 Conteúdo: {valor}")
                print("─" * 72)
                
        print("\n📦 CONTEXTO INJETADO NO PROMPT DA Z.AI:")
        print("┌" + "─" * 70 + "┐")
        if contexto_formatado:
            for line in contexto_formatado.splitlines():
                # Trunca visualmente linhas muito longas no box CLI
                disp_line = line if len(line) <= 68 else line[:65] + "..."
                print(f"│ {disp_line:<68} │")
        else:
            print(f"│ {'(Nenhuma memória anexada)':<68} │")
        print("└" + "─" * 70 + "┘\n")


def run_server():
    server = HTTPServer(("localhost", PORT), AylaRequestHandler)
    print(f"\n⚡ AYLA CONTROL HUB RODANDO EM: http://localhost:{PORT}")
    print(f"💡 Abra o seu navegador se não abrir automaticamente!\n")
    webbrowser.open(f"http://localhost:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    args = [a.lower() for a in sys.argv[1:]]
    
    if "--rag" in args or "-r" in args:
        modo_teste_rag_cli()
    elif "--web" in args or "-w" in args:
        if not DISCORD_TOKEN:
            print("❌ ERRO FATAL: DISCORD_TOKEN não encontrado no .env")
            sys.exit(1)
        run_server()
    elif "--both" in args or "-b" in args:
        if not DISCORD_TOKEN:
            print("❌ ERRO FATAL: DISCORD_TOKEN não encontrado no .env")
            sys.exit(1)
        t = threading.Thread(target=run_server, daemon=True)
        t.start()
        time.sleep(1)
        modo_teste_rag_cli()
    else:
        print("\n" + "═" * 60)
        print("   AYLA DISCORD CONTROL HUB & RAG TEST CENTER 🐾")
        print("═" * 60)
        print("  [1] Iniciar Hub Web (Servidor Discord no Navegador)")
        print("  [2] Testar RAG Híbrido (CLI - Digitar mensagem e ver memórias)")
        print("  [3] Iniciar Ambos (Servidor Web + CLI de Teste)")
        print("  [4] Sair")
        print("═" * 60)
        opcao = input("Escolha uma opção [1-4] (Padrão: 2): ").strip()
        
        if opcao == "1":
            if not DISCORD_TOKEN:
                print("❌ ERRO FATAL: DISCORD_TOKEN não encontrado no .env")
                sys.exit(1)
            run_server()
        elif opcao == "3":
            if not DISCORD_TOKEN:
                print("❌ ERRO FATAL: DISCORD_TOKEN não encontrado no .env")
                sys.exit(1)
            t = threading.Thread(target=run_server, daemon=True)
            t.start()
            time.sleep(1)
            modo_teste_rag_cli()
        elif opcao == "4":
            sys.exit(0)
        else:
            modo_teste_rag_cli()
