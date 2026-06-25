import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
import time
import shutil
import subprocess
import webbrowser
import json
import asyncio
import discord
from discord import app_commands
from pathlib import Path
from datetime import datetime
from urllib.parse import quote_plus, quote
import requests
import random    
import winsound  
import re
import threading
import importlib.util


# ══════════════════════════════════════════════════════════
#  CONFIGURAÇÃO VIA .ENV
# ══════════════════════════════════════════════════════════
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

GEMINI_API_KEYS = [os.getenv(f"GEMINI_API_KEY_{i}", "") for i in range(1, 7)]
GEMINI_API_KEYS = list(dict.fromkeys([k for k in GEMINI_API_KEYS if k.strip()]))

DISCORD_TOKEN         = os.getenv("DISCORD_TOKEN", "")
DISCORD_OWNER_ID      = int(os.getenv("DISCORD_OWNER_ID", "0"))

if not GEMINI_API_KEYS or not DISCORD_TOKEN or DISCORD_OWNER_ID == 0:
    print("⚠️ ERRO FATAL: Verifique se GEMINI_API_KEY_X, DISCORD_TOKEN e DISCORD_OWNER_ID estão no .env!")
    sys.exit(1)

# ══════════════════════════════════════════════════════════
#  SISTEMA DE MEMÓRIA PERSISTENTE
# ══════════════════════════════════════════════════════════
ARQUIVO_MEMORIA = Path(__file__).resolve().parent / "Ayla_Memoria.json"



def carregar_memoria() -> dict:
    if ARQUIVO_MEMORIA.exists():
        try:
            with open(ARQUIVO_MEMORIA, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def salvar_memoria(dados: dict):
    ARQUIVO_MEMORIA.parent.mkdir(parents=True, exist_ok=True)
    with open(ARQUIVO_MEMORIA, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)

# Note: O sistema de Whitelist DM (envio de mensagens privadas) foi modularizado 
# e é carregado dinamicamente a partir do arquivo MODOS/enviar_mensagem_whitelist_bot.py.


# ══════════════════════════════════════════════════════════
#  IMPORTS OPCIONAIS
# ══════════════════════════════════════════════════════════
try: import pyautogui; pyautogui.FAILSAFE = True; PYAUTOGUI_OK = True
except ImportError: PYAUTOGUI_OK = False

try: import psutil; PSUTIL_OK = True
except ImportError: PSUTIL_OK = False

try: import pyperclip; PYPERCLIP_OK = True
except ImportError: PYPERCLIP_OK = False

try: from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume; from ctypes import cast, POINTER; from comtypes import CLSCTX_ALL; PYCAW_OK = True
except ImportError: PYCAW_OK = False

try: from winotify import Notification; WINOTIFY_OK = True
except ImportError: WINOTIFY_OK = False

try: from send2trash import send2trash; SEND2TRASH_OK = True
except ImportError: SEND2TRASH_OK = False

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    print("ERRO: google-genai não instalado! (pip install google-genai)")
    sys.exit(1)

def filtrar_emojis_ayla(texto: str) -> str:
    """Remove tags de emojis do Discord e formatações Markdown"""
    texto_filtrado = re.sub(r'<a?:[a-zA-Z0-9_]+:[0-9]+>', '', texto)
    texto_filtrado = re.sub(r'[*_`#~]', '', texto_filtrado)
    texto_filtrado = re.sub(r'\s+', ' ', texto_filtrado).strip()
    return texto_filtrado



# ══════════════════════════════════════════════════════════
#  FERRAMENTAS DA AYLA
# ══════════════════════════════════════════════════════════

ULTIMA_IMAGEM_GERADA: str | None = None
BOT_LAUNCH_ERROR: str | None = None
CONTEXTO_ATIVO = None
ULTIMO_ANEXO_IMAGEM: tuple | None = None  # (bytes, mime_type) — preenchido quando recebe anexo de imagem

# ══════════════════════════════════════════════════════════
#  SISTEMA DE MÓDULOS / PLUGINS (CARREGAMENTO DINÂMICO)
# ══════════════════════════════════════════════════════════
TOOL_MAP = {}
FUNCTION_DECLARATIONS = []
MODOS_DIR = Path(__file__).resolve().parent / "MODOS"
MODULOS_CARREGADOS = {}

_NOMES_COMPATIVEIS_MODOS = (
    "os", "sys", "time", "shutil", "subprocess", "webbrowser", "json", "asyncio",
    "discord", "app_commands", "Path", "datetime", "quote_plus", "quote", "requests",
    "random", "winsound", "re", "threading", "genai", "genai_types",
    "PYAUTOGUI_OK", "PSUTIL_OK", "PYPERCLIP_OK", "PYCAW_OK", "WINOTIFY_OK",
    "SEND2TRASH_OK", "pyautogui", "psutil", "pyperclip", "send2trash",
    "Notification", "AudioUtilities", "IAudioEndpointVolume", "cast", "POINTER",
    "CLSCTX_ALL", "GEMINI_API_KEYS", "DISCORD_TOKEN", "DISCORD_OWNER_ID",
    "ARQUIVO_MEMORIA", "carregar_memoria", "salvar_memoria",
    "filtrar_emojis_ayla", "AylaBot", "bot",
)

_NOMES_ESTADO_COMPARTILHADO = (
    "ULTIMA_IMAGEM_GERADA",
    "BOT_LAUNCH_ERROR",
    "CONTEXTO_ATIVO",
    "ULTIMO_ANEXO_IMAGEM",
)


def _contexto_compatibilidade_modulo() -> dict:
    contexto = {
        nome: globals()[nome]
        for nome in _NOMES_COMPATIVEIS_MODOS + _NOMES_ESTADO_COMPARTILHADO
        if nome in globals()
    }
    contexto["TOOL_MAP"] = TOOL_MAP
    contexto["FUNCTION_DECLARATIONS"] = FUNCTION_DECLARATIONS
    return contexto


def _sincronizar_contexto_modulo(modulo):
    modulo.__dict__.update(_contexto_compatibilidade_modulo())


def _sincronizar_contexto_modulos():
    for modulo in MODULOS_CARREGADOS.values():
        _sincronizar_contexto_modulo(modulo)


def _absorver_contexto_modulo(modulo):
    global ULTIMA_IMAGEM_GERADA, BOT_LAUNCH_ERROR, CONTEXTO_ATIVO, ULTIMO_ANEXO_IMAGEM
    for nome in _NOMES_ESTADO_COMPARTILHADO:
        if hasattr(modulo, nome):
            globals()[nome] = getattr(modulo, nome)


def carregar_modulos(pasta: Path = MODOS_DIR):
    if not pasta.exists():
        print(f"⚠️ Pasta de módulos não encontrada: {pasta}")
        return

    for arq_py in sorted(pasta.glob("*.py")):
        nome_modulo = f"ayla_modo_{arq_py.stem}"
        try:
            spec = importlib.util.spec_from_file_location(nome_modulo, arq_py)
            if spec is None or spec.loader is None:
                print(f"❌ Não consegui criar spec de import para {arq_py.name}.")
                continue

            modulo = importlib.util.module_from_spec(spec)
            _sincronizar_contexto_modulo(modulo)
            sys.modules[nome_modulo] = modulo

            ferramentas_antes = set(TOOL_MAP)
            declaracoes_antes = len(FUNCTION_DECLARATIONS)
            spec.loader.exec_module(modulo)

            registrou_legado = (
                set(TOOL_MAP) != ferramentas_antes
                or len(FUNCTION_DECLARATIONS) != declaracoes_antes
            )
            register = getattr(modulo, "register", None)
            if callable(register) and not registrou_legado:
                register(TOOL_MAP, FUNCTION_DECLARATIONS)

            MODULOS_CARREGADOS[arq_py.stem] = modulo
            _absorver_contexto_modulo(modulo)
            print(f"✅ Módulo {arq_py.name} carregado!")
        except Exception as e:
            import traceback
            print(f"❌ Erro ao carregar módulo {arq_py.name}: {e}")
            traceback.print_exc()






# Mensagem para usuários que não são a dona
MSG_MODO_PUBLICO_DESCONTINUADO = "Modo publico desligado"
MSG_BLOQUEADO = "Você está bloqueado! "
#encontrou!!!!!!!!!
SYSTEM_PROMPT = """
coloque seu prompt aqui

"""


def _schema_genai(schema_dict: dict | None) -> genai_types.Schema:
    schema_dict = schema_dict or {}
    type_map = {
        "string": genai_types.Type.STRING,
        "integer": genai_types.Type.INTEGER,
        "number": genai_types.Type.NUMBER,
        "boolean": genai_types.Type.BOOLEAN,
        "object": genai_types.Type.OBJECT,
        "array": genai_types.Type.ARRAY,
    }

    kwargs = {}
    tipo = schema_dict.get("type")
    if tipo:
        kwargs["type"] = type_map.get(str(tipo).lower(), genai_types.Type.STRING)

    campos_simples = (
        "description", "enum", "format", "nullable", "title", "default", "example",
        "minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems",
        "minProperties", "maxProperties", "pattern",
    )
    for campo in campos_simples:
        if campo in schema_dict:
            kwargs[campo] = schema_dict[campo]

    if "properties" in schema_dict and isinstance(schema_dict["properties"], dict):
        kwargs["properties"] = {
            nome: _schema_genai(definicao)
            for nome, definicao in schema_dict["properties"].items()
        }

    if "items" in schema_dict and isinstance(schema_dict["items"], dict):
        kwargs["items"] = _schema_genai(schema_dict["items"])

    # A classe Schema do SDK aceita additionalProperties, mas o endpoint Gemini
    # rejeita esse campo em function_declarations como "additional_properties".
    # Mantemos o tipo object/array e a descricao do schema, sem enviar esse campo.

    if "required" in schema_dict:
        kwargs["required"] = list(schema_dict.get("required") or [])

    if "propertyOrdering" in schema_dict:
        kwargs["propertyOrdering"] = list(schema_dict.get("propertyOrdering") or [])

    if "anyOf" in schema_dict and isinstance(schema_dict["anyOf"], list):
        kwargs["anyOf"] = [
            _schema_genai(item) for item in schema_dict["anyOf"] if isinstance(item, dict)
        ]

    return genai_types.Schema(**kwargs)


def build_tools():
    declarations = []
    for fd in FUNCTION_DECLARATIONS:
        declarations.append(genai_types.FunctionDeclaration(
            name=fd["name"],
            description=fd["description"],
            parameters=_schema_genai(fd.get("parameters", {"type": "object", "properties": {}})),
        ))
    return [genai_types.Tool(function_declarations=declarations)]

def executar_ferramenta(nome: str, args: dict) -> str:
    fn = TOOL_MAP.get(nome)
    if not fn: return f"Ferramenta desconhecida: {nome}"
    modulo = sys.modules.get(getattr(fn, "__module__", ""))
    if modulo:
        _sincronizar_contexto_modulo(modulo)
    try: return str(fn(**args))
    except Exception as e:
        import traceback
        print(f"❌ Erro ao executar ferramenta {nome} com args {args}:")
        traceback.print_exc()
        return f"Erro em {nome}: {e}"
    finally:
        if modulo:
            _absorver_contexto_modulo(modulo)

def eh_requisicao_imagem(mensagem: str) -> bool:
    if not mensagem:
        return False
    m_lower = mensagem.lower()
    keywords = [
        "desenha", "desenhe", "gerar imagem", "gerar foto", "gera imagem", "gera foto", 
        "imagem de", "foto de", "crie uma imagem", "criar imagem", "editar imagem", 
        "edita a imagem", "edita essa", "modifique a imagem", "muda a imagem", "ilustre", "ilustra"
    ]
    return any(w in m_lower for w in keywords)

# ══════════════════════════════════════════════════════════
#  LÓGICA DO DISCORD COM FALLBACK DE MODELOS E APIs
# ══════════════════════════════════════════════════════════


class AylaBot(discord.Client):
    def carregar_permissoes(self):
        from pathlib import Path
        import json
        path = Path(__file__).resolve().parent / "ayla_permissions.json"
        self.public_mode = False
        self.allowed_tools = []
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.public_mode = data.get("public_mode", False)
                    self.allowed_tools = data.get("allowed_tools", [])
            except Exception as e:
                print(f"⚠️ Erro ao carregar permissões no bot: {e}")

    def carregar_bloqueados(self):
        from pathlib import Path
        import json
        path = Path(__file__).resolve().parent / "ayla_blocked_users.json"
        self.blocked_users = []
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.blocked_users = [int(uid) for uid in data]
            except Exception as e:
                print(f"⚠️ Erro ao carregar bloqueados no bot: {e}")

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True   # Necessário para ler conteúdo das mensagens
        intents.dm_messages = True       # Necessário para receber DMs
        intents.guilds = True            # Necessário para entrar em guildas
        super().__init__(intents=intents)
        self.prefix = "!" # Prefixo para comandos de texto
        self.tree = app_commands.CommandTree(self)
        self.tools_config = build_tools()
        self.carregar_permissoes()
        self.carregar_bloqueados()
        self.lock = threading.Lock()
        self.cancel_lock = threading.Lock()
        self.requisicoes_canceladas = set()

        mem = carregar_memoria()
        pedacos = []
        for k, v in mem.items():
            if isinstance(v, dict) and "Data e hora" in v and "Valor" in v:
                pedacos.append(f"- {k}: {v.get('Valor')} (Salvo em: {v.get('Data e hora')})")
            elif isinstance(v, dict) and "valor" in v and "data_hora" in v:
                pedacos.append(f"- {k}: {v.get('valor')} (Salvo em: {v.get('data_hora')})")
            else:
                pedacos.append(f"- {k}: {v}")
        texto_memoria = "\n".join(pedacos) if pedacos else "Nenhuma memória salva ainda."
        prompt_expandido = SYSTEM_PROMPT + f"\n\n[SEU CADERNINHO DE MEMÓRIAS NO HD]\nAqui estão as coisas que você anotou sobre a usuária:\n{texto_memoria}"
        self.config = genai_types.GenerateContentConfig(system_instruction=prompt_expandido, tools=self.tools_config)

        # Carregar modelos do JSON
        from pathlib import Path
        import json
        modelos_json_path = Path(__file__).resolve().parent / "ayla_models.json"
        
        self.modelos_avancados = ["gemini-3.5-flash", "gemini-2.5-flash", "gemma-4-31b-it"]
        self.modelos_padrao = ["gemini-3.1-flash-lite", "gemini-2.5-flash-lite", "gemini-3-flash-preview", "gemma-4-26b-a4b-it"]
        
        if modelos_json_path.exists():
            try:
                data = json.loads(modelos_json_path.read_text(encoding="utf-8"))
                self.modelos_avancados = [m["name"] for m in data.get("raciocinar", [])]
                self.modelos_padrao = [m["name"] for m in data.get("padrao", [])]
            except Exception as e:
                print(f"⚠️ Erro ao ler ayla_models.json: {e}")
        else:
            # Escreve o padrão caso não exista
            raciocinar_defaults = [
                {"name": "gemini-3.5-flash", "desc": "Multimodal, Raciocínio Ativo Superior", "tags": ["🩵 Principal", "🖼️ Multimodal", "🧠 Raciocínio"]},
                {"name": "gemini-3-flash-preview", "desc": "Modelo Flash experimental de alta velocidade", "tags": ["🧪 Experimental", "⚡ Rápido"]},
                {"name": "gemini-2.5-flash", "desc": "Modelo intermediário equilibrado em velocidade e qualidade", "tags": ["🖼️ Multimodal", "⚡ Rápido"]},
                {"name": "gemma-4-31b-it", "desc": "Modelo aberto do Google de alto desempenho (Dense)", "tags": ["💬 Texto", "🔓 Aberto"]}
            ]
            padrao_defaults = [
                {"name": "gemini-3.1-flash-lite", "desc": "Ultra-rápido e altamente eficiente", "tags": ["⚡ Rápido", "🪙 Econômico", "🖼️ Multimodal"]},
                {"name": "gemini-2.5-flash-lite", "desc": "Modelo compacto rápido e econômico", "tags": ["🪙 Econômico", "⚡ Rápido"]},
                {"name": "gemma-4-31b-it", "desc": "Modelo aberto do Google de alto desempenho (Dense)", "tags": ["💬 Texto", "🔓 Aberto"]},
                {"name": "gemma-4-26b-a4b-it", "desc": "Modelo aberto do Google otimizado (MoE)", "tags": ["💬 Texto", "🔓 Aberto"]}
            ]
            defaults = {
                "raciocinar": raciocinar_defaults,
                "padrao": padrao_defaults
            }
            try:
                modelos_json_path.write_text(json.dumps(defaults, indent=4, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                print(f"⚠️ Erro ao criar ayla_models.json padrão: {e}")
                
        self.modelos_disponiveis = self.modelos_avancados + self.modelos_padrao
        self.idx_modelo_atual = 0
        self.modelo_atual = self.modelos_disponiveis[self.idx_modelo_atual]
        self.model_status = {} # {name: {"status": "ok"/"slow"/"error", "latency": str, "error": str}}

        self.api_keys = GEMINI_API_KEYS
        self.idx_api_atual = 0

        self.genai_client = genai.Client(api_key=self.api_keys[self.idx_api_atual])
        self.chat_session = None

    def cancelar_requisicao(self, request_id: str | None):
        if not request_id:
            return
        with self.cancel_lock:
            self.requisicoes_canceladas.add(request_id)

    def requisicao_cancelada(self, request_id: str | None) -> bool:
        if not request_id:
            return False
        with self.cancel_lock:
            return request_id in self.requisicoes_canceladas

    def limpar_requisicao_cancelada(self, request_id: str | None):
        if not request_id:
            return
        with self.cancel_lock:
            self.requisicoes_canceladas.discard(request_id)

    def atualizar_prompt_memoria(self):
        mem = carregar_memoria()
        pedacos = []
        for k, v in mem.items():
            if isinstance(v, dict) and "Data e hora" in v and "Valor" in v:
                pedacos.append(f"- {k}: {v.get('Valor')} (Salvo em: {v.get('Data e hora')})")
            elif isinstance(v, dict) and "valor" in v and "data_hora" in v:
                pedacos.append(f"- {k}: {v.get('valor')} (Salvo em: {v.get('data_hora')})")
            else:
                pedacos.append(f"- {k}: {v}")
        texto_memoria = "\n".join(pedacos) if pedacos else "Nenhuma memória salva ainda."
        prompt_expandido = SYSTEM_PROMPT + f"\n\n[SEU CADERNINHO DE MEMÓRIAS NO HD]\nAqui estão as coisas que você anotou sobre a usuária:\n{texto_memoria}"
        self.config.system_instruction = prompt_expandido

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Comandos de barra sincronizados.")

    async def on_ready(self):
        print(f"🩵 Ayla conectada como {self.user}! Dona Oficial: {DISCORD_OWNER_ID}")
        self.modelo_atual = self.modelos_disponiveis[self.idx_modelo_atual]
        self.chat_session = self.genai_client.chats.create(model=self.modelo_atual, config=self.config)

    async def on_message(self, message):
        global ULTIMA_IMAGEM_GERADA, CONTEXTO_ATIVO, ULTIMO_ANEXO_IMAGEM

        if message.author == self.user:
            return

        # Proteção: ignora mensagens se o bot ainda não terminou de inicializar
        if self.chat_session is None:
            print("⏳ Mensagem recebida antes da inicialização completa, ignorando...")
            return

        if message.author.bot:
            return

        # Verificação da lista de bloqueados
        if hasattr(self, "blocked_users") and message.author.id in self.blocked_users:
            if message.guild is None or self.user in message.mentions:
                try:
                    await message.reply(MSG_BLOQUEADO)
                except Exception as e:
                    print(f"⚠️ Erro ao enviar mensagem de bloqueado: {e}")
            return





        # ── MODO DM: responde automaticamente sem precisar de menção ──
        if message.guild is None:
            # Modo público — permite se for o dono ou se o modo público estiver ativo
            if message.author.id != DISCORD_OWNER_ID:
                if not getattr(self, "public_mode", False):
                    try:
                        await message.reply(MSG_MODO_PUBLICO_DESCONTINUADO)
                    except Exception as e:
                        print(f"⚠️ Erro ao enviar mensagem de modo descontinuado na DM: {e}")
                    return

            conteudo_dm = message.content.strip()
            if not conteudo_dm and not message.attachments:
                conteudo_dm = "Oi! O que você pode fazer?"

            is_img = eh_requisicao_imagem(conteudo_dm)
            msg_ref = None

            async def run_dm_task():
                nonlocal msg_ref

                if is_img:
                    msg_ref = await message.reply("gerando....")

                arquivos = []
                if message.attachments:
                    for anexo in message.attachments[:10]:
                        tipo = anexo.content_type or ""
                        if tipo.startswith("image/") or tipo.startswith("audio/") or tipo.startswith("video/"):
                            try:
                                arq_bytes = await anexo.read()
                                arquivos.append((arq_bytes, tipo))
                            except Exception as e:
                                print(f"⚠️ Erro ao ler anexo na DM: {e}")

                try:
                    resposta, img_gerada = await asyncio.to_thread(
                        self.processar_gemini,
                        conteudo_dm or "[Enviou um arquivo em anexo sem nenhuma mensagem de texto. Analise o arquivo enviado diretamente (não use a ferramenta ver_tela_atual, pois o arquivo já foi enviado nos bytes do anexo)]",
                        arquivos,
                        "DM-Dona" if message.author.id == DISCORD_OWNER_ID else "DM",
                        message
                    )
                except Exception as e:
                    resposta = f"Eita, deu um probleminha aqui: {e} 🥺"
                    img_gerada = None

                arquivo_discord = None
                if img_gerada and Path(img_gerada).is_file():
                    arquivo_discord = discord.File(img_gerada, filename=Path(img_gerada).name)

                try:
                    if len(resposta) > 2000:
                        pedacos = []
                        while len(resposta) > 2000:
                            corte = resposta.rfind("\n", 0, 1990)
                            if corte == -1: corte = 1990
                            pedacos.append(resposta[:corte])
                            resposta = resposta[corte:]
                        pedacos.append(resposta)

                        if msg_ref:
                            await msg_ref.edit(content=pedacos[0], attachments=[arquivo_discord] if arquivo_discord else [])
                        else:
                            await message.reply(pedacos[0], file=arquivo_discord)

                        for pedaco in pedacos[1:]:
                            if pedaco.strip():
                                await message.channel.send(pedaco)
                    else:
                        if msg_ref:
                            await msg_ref.edit(content=resposta, attachments=[arquivo_discord] if arquivo_discord else [])
                        else:
                            await message.reply(resposta, file=arquivo_discord)
                except discord.errors.Forbidden:
                    print("⚠️ Sem permissão para enviar mensagem na DM.")
                except Exception as e:
                    print(f"⚠️ Erro ao enviar resposta na DM: {e}")

            if is_img:
                await run_dm_task()
            else:
                async with message.channel.typing():
                    await run_dm_task()

            return  # DM já tratada, não precisa verificar menção

        # Verifica se o bot foi mencionado
        if self.user in message.mentions:
            # Modo público — permite se for o dono ou se o modo público estiver ativo
            if message.author.id != DISCORD_OWNER_ID:
                if not getattr(self, "public_mode", False):
                    try:
                        await message.reply(MSG_MODO_PUBLICO_DESCONTINUADO)
                    except Exception as e:
                        print(f"⚠️ Erro ao enviar mensagem de modo descontinuado na menção: {e}")
                    return

            conteudo_limpo = message.content.replace(f"<@{self.user.id}>", "").replace(f"<@!{self.user.id}>", "").strip()
            
            if not conteudo_limpo and not message.attachments:
                conteudo_limpo = "Oi! O que você pode fazer?"

            is_img = eh_requisicao_imagem(conteudo_limpo)
            msg_ref = None

            async def run_mention_task():
                nonlocal msg_ref
                
                if is_img:
                    msg_ref = await message.reply("gerando imagem....")

                arquivos = []
                if message.attachments:
                    for anexo in message.attachments[:10]:
                        tipo = anexo.content_type or ""
                        if tipo.startswith("image/") or tipo.startswith("audio/") or tipo.startswith("video/"):
                            try:
                                arq_bytes = await anexo.read()
                                arquivos.append((arq_bytes, tipo))
                            except Exception as e:
                                print(f"⚠️ Erro ao ler anexo na menção: {e}")

                try:
                    resposta, img_gerada = await asyncio.to_thread(
                        self.processar_gemini,
                        conteudo_limpo or "[Enviou um arquivo em anexo sem nenhuma mensagem de texto. Analise o arquivo enviado diretamente (não use a ferramenta ver_tela_atual, pois o arquivo já foi enviado nos bytes do anexo)]",
                        arquivos,
                        "Discord",
                        message
                    )
                except Exception as e:
                    resposta = f"Eita, deu um probleminha aqui: {e} 🥺"
                    img_gerada = None

                arquivo_discord = None
                if img_gerada and Path(img_gerada).is_file():
                    arquivo_discord = discord.File(img_gerada, filename=Path(img_gerada).name)

                try:
                    if len(resposta) > 2000:
                        pedacos = []
                        while len(resposta) > 2000:
                            corte = resposta.rfind("\n", 0, 1990)
                            if corte == -1: corte = 1990
                            pedacos.append(resposta[:corte])
                            resposta = resposta[corte:]
                        pedacos.append(resposta)
                        
                        if msg_ref:
                            await msg_ref.edit(content=pedacos[0], attachments=[arquivo_discord] if arquivo_discord else [])
                        else:
                            await message.reply(pedacos[0], file=arquivo_discord)
                            
                        for pedaco in pedacos[1:]:
                            if pedaco.strip():
                                await message.channel.send(pedaco)
                    else:
                        if msg_ref:
                            await msg_ref.edit(content=resposta, attachments=[arquivo_discord] if arquivo_discord else [])
                        else:
                            await message.reply(resposta, file=arquivo_discord)
                except discord.errors.Forbidden:
                    print("⚠️ Sem permissão para enviar mensagem ou arquivo na menção.")
                except Exception as e:
                    print(f"⚠️ Erro ao enviar resposta da menção: {e}")

            if is_img:
                await run_mention_task()
            else:
                async with message.channel.typing():
                    await run_mention_task()

    def enviar_com_fallback(self, payload, modelos_list=None):
        if modelos_list is None:
            modelos_list = self.modelos_disponiveis

        try:
            idx_modelo = modelos_list.index(self.modelo_atual)
        except ValueError:
            idx_modelo = 0
            self.modelo_atual = modelos_list[0]
            try:
                historico = self.chat_session.get_history() if self.chat_session else None
            except Exception:
                historico = None
            self.chat_session = self.genai_client.chats.create(
                model=self.modelo_atual,
                config=self.config,
                history=historico
            )

        while True:
            try:
                t0 = time.time()
                resp = self.chat_session.send_message(payload)
                dur = time.time() - t0
                self.model_status[self.modelo_atual] = {
                    "status": "slow" if dur > 5.0 else "ok",
                    "latency": f"{dur:.1f}s",
                    "latency_ms": int(dur * 1000),
                    "error": ""
                }
                return resp
            except Exception as erro:
                erro_msg = str(erro)
                self.model_status[self.modelo_atual] = {
                    "status": "error",
                    "latency": "N/A",
                    "error": erro_msg[:80]
                }
                erro_msg = str(erro)
                is_quota        = "429" in erro_msg or "RESOURCE_EXHAUSTED" in erro_msg
                is_interno      = "500" in erro_msg or "INTERNAL" in erro_msg
                is_indisponivel = "503" in erro_msg or "UNAVAILABLE" in erro_msg
                is_modality     = "400" in erro_msg and ("modality" in erro_msg.lower() or "not supported" in erro_msg.lower())
                is_403          = "403" in erro_msg or "PERMISSION_DENIED" in erro_msg

                if is_403:
                    print("\n⚠️ Erro 403: Arquivo expirado no Google. Reiniciando sessão...")
                    self.chat_session = self.genai_client.chats.create(model=self.modelo_atual, config=self.config)
                    try: return self.chat_session.send_message(payload)
                    except Exception: pass

                if is_interno or is_indisponivel or is_modality:
                    motivo = "Modelo não aceita mídia" if is_modality else ("API sobrecarregada (503)" if is_indisponivel else "Erro 500 interno")
                    print(f"\n⚠️ {motivo}! Pulando de modelo...")
                    idx_modelo += 1
                    if idx_modelo >= len(modelos_list):
                        idx_modelo -= 1
                        raise Exception("Todos os modelos falharam.")

                    self.modelo_atual = modelos_list[idx_modelo]
                    try:
                        historico = self.chat_session.get_history() if self.chat_session else None
                    except Exception:
                        historico = None
                    self.chat_session = self.genai_client.chats.create(model=self.modelo_atual, config=self.config, history=historico)
                    continue

                if is_quota:
                    if "gemma" in self.modelo_atual.lower():
                        raise Exception("Limite esgotado até no Gemma! A IA precisará descansar.")

                    self.idx_api_atual += 1

                    if self.idx_api_atual >= len(self.api_keys):
                        self.idx_api_atual = 0
                        idx_modelo += 1

                        if idx_modelo >= len(modelos_list):
                            raise Exception("Todas as contas e modelos esgotaram a quota.")

                        self.modelo_atual = modelos_list[idx_modelo]
                        print(f"\n🔄 Todas as APIs esgotadas no modelo anterior. Pulando para {self.modelo_atual}...")
                    else:
                        print(f"\n🔄 Quota esgotada! Indo para api {self.idx_api_atual + 1}...")

                    self.genai_client = genai.Client(api_key=self.api_keys[self.idx_api_atual])

                    try:
                        historico = self.chat_session.get_history() if hasattr(self.chat_session, "get_history") else None
                    except Exception:
                        historico = None

                    self.chat_session = self.genai_client.chats.create(
                        model=self.modelo_atual,
                        config=self.config,
                        history=historico
                    )
                else:
                    print(f"\n⚠️ Erro genérico no modelo ({erro}): tentando próximo modelo...")
                    idx_modelo += 1
                    if idx_modelo >= len(modelos_list):
                        idx_modelo -= 1
                        raise erro

                    self.modelo_atual = modelos_list[idx_modelo]
                    try:
                        historico = self.chat_session.get_history() if self.chat_session else None
                    except Exception:
                        historico = None
                    self.chat_session = self.genai_client.chats.create(model=self.modelo_atual, config=self.config, history=historico)
                    continue

    def tentar_comando_dm_whitelist(self, user_input: str, origem: str = "Discord") -> str | None:
        # Sobrescrita dinamicamente pelo módulo enviar_mensagem_whitelist_bot.py
        return None

    def processar_gemini(self, user_input: str, arquivos: list[tuple[bytes, str]] = None, origem: str = "Discord", contexto_discord = None, request_id: str | None = None) -> tuple[str, str | None]:
        with self.lock:
            global ULTIMA_IMAGEM_GERADA, ULTIMO_ANEXO_IMAGEM, CONTEXTO_ATIVO
            ULTIMA_IMAGEM_GERADA = None
            ULTIMO_ANEXO_IMAGEM = None
            CONTEXTO_ATIVO = contexto_discord

            def tarefa_cancelada() -> bool:
                return self.requisicao_cancelada(request_id)

            if arquivos:
                for arq_bytes, tipo in arquivos:
                    if tipo.startswith("image/"):
                        ULTIMO_ANEXO_IMAGEM = (arq_bytes, tipo)
                        break

            try:
                if tarefa_cancelada():
                    self.limpar_requisicao_cancelada(request_id)
                    return "⏱️ Essa tarefa foi cancelada antes de começar.", None

                # Identifica ID do autor para verificação de permissões do modo público
                autor_id = 0
                if origem not in ("GUI", "Terminal") and CONTEXTO_ATIVO is not None:
                    if hasattr(CONTEXTO_ATIVO, "author"):
                        autor_id = getattr(CONTEXTO_ATIVO.author, "id", 0)
                    elif hasattr(CONTEXTO_ATIVO, "user"):
                        autor_id = getattr(CONTEXTO_ATIVO.user, "id", 0)

                # Para comandos diretos de whitelist (só executa se for o dono ou se a ferramenta estiver permitida)
                permitido_dm = True
                if autor_id != DISCORD_OWNER_ID and origem not in ("GUI", "Terminal"):
                    permitido_dm = False
                    if getattr(self, "public_mode", False):
                        allowed_list = getattr(self, "allowed_tools", [])
                        if "enviar_mensagem_whitelist_bot" in allowed_list:
                            permitido_dm = True

                if permitido_dm:
                    resultado_dm = self.tentar_comando_dm_whitelist(user_input, origem)
                    if resultado_dm is not None:
                        # Clear globals before returning
                        ULTIMA_IMAGEM_GERADA = None
                        CONTEXTO_ATIVO = None
                        ULTIMO_ANEXO_IMAGEM = None
                        return resultado_dm, None

                comando = (user_input or "").strip().lower()

                if comando in ("abre o desistalador", "abre desistalador", "abrir o desistalador", "abrir desistalador", "abre o desinstalador", "abrir o desinstalador"):
                    if autor_id != DISCORD_OWNER_ID and origem not in ("GUI", "Terminal"):
                        # Clear globals before returning
                        ULTIMA_IMAGEM_GERADA = None
                        CONTEXTO_ATIVO = None
                        ULTIMO_ANEXO_IMAGEM = None
                        return "Ação bloqueada: a ferramenta 'abrir_desistalador' não está disponível para uso público.", None
                    # Clear globals before returning
                    res_desistalador = abrir_desistalador()
                    ULTIMA_IMAGEM_GERADA = None
                    CONTEXTO_ATIVO = None
                    ULTIMO_ANEXO_IMAGEM = None
                    return res_desistalador, None

                if origem in ("GUI", "Terminal"):
                    usuario_nome = "Usuario"
                else:
                    usuario_nome = "Usuário"
                    if CONTEXTO_ATIVO and hasattr(CONTEXTO_ATIVO, "author"):
                        usuario_nome = str(getattr(CONTEXTO_ATIVO.author, "display_name", CONTEXTO_ATIVO.author))
                    elif CONTEXTO_ATIVO and hasattr(CONTEXTO_ATIVO, "user"):
                        usuario_nome = str(getattr(CONTEXTO_ATIVO.user, "display_name", CONTEXTO_ATIVO.user))

                texto_formatado = f"[Mensagem de {usuario_nome}]: {user_input}" if user_input else f"[Mensagem de {usuario_nome} enviou um arquivo]"

                modelos_req = getattr(self, "modelos_padrao", ["gemini-3.1-flash-lite", "gemini-2.5-flash-lite", "gemini-3-flash-preview", "gemma-4-26b-a4b-it"])

                target_model = modelos_req[0]
                if getattr(self, "modelo_atual", None) != target_model:
                    print(f"🔄 Alternando modelo da sessão de {getattr(self, 'modelo_atual', None)} para {target_model}...")
                    try:
                        historico = self.chat_session.get_history() if self.chat_session else None
                    except Exception:
                        historico = None
                    self.chat_session = self.genai_client.chats.create(
                        model=target_model,
                        config=self.config,
                        history=historico
                    )
                    self.modelo_atual = target_model

                payload = []

                if arquivos:
                    for arq_bytes, arq_mime in arquivos:
                        mime_limpo = arq_mime.split(";")[0]
                        payload.append(genai_types.Part.from_bytes(data=arq_bytes, mime_type=mime_limpo))

                if payload:
                    payload.append(genai_types.Part(text=texto_formatado))
                else:
                    payload = texto_formatado

                response = self.enviar_com_fallback(payload, modelos_list=modelos_req)

                if tarefa_cancelada():
                    ULTIMA_IMAGEM_GERADA = None
                    CONTEXTO_ATIVO = None
                    ULTIMO_ANEXO_IMAGEM = None
                    self.limpar_requisicao_cancelada(request_id)
                    return "⏱️ Essa tarefa foi cancelada por timeout antes de executar ações.", None

                textos_acumulados = []

                loop_seguranca = 0
                while loop_seguranca < 8:
                    loop_seguranca += 1

                    if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts: break

                    # Separa partes de texto e partes de function_call
                    fn_calls = []
                    for p in response.candidates[0].content.parts:
                        if p.function_call and p.function_call.name:
                            fn_calls.append(p)
                        elif hasattr(p, "text") and p.text and p.text.strip():
                            textos_acumulados.append(p.text.strip())

                    if not fn_calls: break

                    fn_responses = []
                    for part in fn_calls:
                        if tarefa_cancelada():
                            ULTIMA_IMAGEM_GERADA = None
                            CONTEXTO_ATIVO = None
                            ULTIMO_ANEXO_IMAGEM = None
                            self.limpar_requisicao_cancelada(request_id)
                            return "⏱️ Essa tarefa foi cancelada por timeout antes de executar ferramentas.", None

                        fc = part.function_call
                        nome = fc.name
                        args = dict(fc.args) if fc.args else {}
                        if nome != "piada_aleatoria":
                            print(f"💻 [{origem}] Executando: {nome}({args})")
                        
                        # Verificação de permissões do modo público
                        if autor_id != DISCORD_OWNER_ID and origem not in ("GUI", "Terminal"):
                            permitido = False
                            if getattr(self, "public_mode", False):
                                allowed_list = getattr(self, "allowed_tools", [])
                                if nome in allowed_list:
                                    permitido = True
                            
                            if not permitido:
                                print(f"🚫 [Permissão] Bloqueando ferramenta '{nome}' para usuário {autor_id}")
                                resultado = f"Ação bloqueada: a ferramenta '{nome}' não está disponível para uso público."
                            else:
                                resultado = executar_ferramenta(nome, args)
                        else:
                            resultado = executar_ferramenta(nome, args)
                        fn_responses.append(
                            genai_types.Part(
                                function_response=genai_types.FunctionResponse(
                                    name=nome,
                                    id=getattr(fc, "id", None),
                                    response={"result": str(resultado)}
                                )
                            )
                        )

                    response = self.enviar_com_fallback(fn_responses, modelos_list=modelos_req)

                # Extrai texto da resposta final (após todas as ferramentas)
                texto_resposta_final = ""
                try:
                    if response and response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                        partes_texto = [p.text.strip() for p in response.candidates[0].content.parts if hasattr(p, "text") and p.text and p.text.strip()]
                        texto_resposta_final = "\n".join(partes_texto)
                except Exception:
                    try:
                        texto_resposta_final = response.text.strip() if response and hasattr(response, "text") and response.text else ""
                    except Exception:
                        texto_resposta_final = ""

                # Combina: prioriza o texto da resposta final; se vazio, usa textos acumulados durante as chamadas de ferramenta
                if texto_resposta_final:
                    texto_final = texto_resposta_final
                elif textos_acumulados:
                    texto_final = "\n".join(textos_acumulados)
                else:
                    texto_final = "Tudo prontinho! 🦎"

                img_gerada = ULTIMA_IMAGEM_GERADA
                
                # Clear globals on success
                ULTIMA_IMAGEM_GERADA = None
                CONTEXTO_ATIVO = None
                ULTIMO_ANEXO_IMAGEM = None

                return texto_final, img_gerada

            except Exception as e:
                import traceback
                traceback.print_exc()
                
                # Clear globals on error
                ULTIMA_IMAGEM_GERADA = None
                CONTEXTO_ATIVO = None
                ULTIMO_ANEXO_IMAGEM = None
                
                return f"Vish, capotei feio aqui: {e}", None

    async def terminal_loop(self):
        print("\n" + "─" * 60)
        print("  🩵  AYLA TERMINAL — Digite direto aqui!")
        print("─" * 60 + "\n")
        loop = asyncio.get_event_loop()
        while True:
            try: user_input = await loop.run_in_executor(None, lambda: input("Você » "))
            except (EOFError, KeyboardInterrupt): break
            if not user_input.strip(): continue
            if user_input.strip().lower() in ("sair", "exit", "quit"): break

            print("⏳ Ayla pensando...", flush=True)
            resposta, _ = await asyncio.to_thread(self.processar_gemini, user_input, None, "Terminal")
            print(f"\nAyla » {resposta}\n")
        print("\n💜 Terminal encerrado. Bot Discord continua rodando!")

carregar_modulos()
bot = AylaBot()
_sincronizar_contexto_modulos()



# ══════════════════════════════════════════════════════════
#  HELPER DE ENVIO
# ══════════════════════════════════════════════════════════

async def _enviar_resposta(interaction: discord.Interaction, resposta: str, arquivo_discord=None, edit_original: bool = False):
    if edit_original:
        try:
            attachments = [arquivo_discord] if arquivo_discord else []
            if len(resposta) > 2000:
                pedacos = []
                while len(resposta) > 2000:
                    corte = resposta.rfind("\n", 0, 1990)
                    if corte == -1: corte = 1990
                    pedacos.append(resposta[:corte])
                    resposta = resposta[corte:]
                pedacos.append(resposta)
                
                await interaction.edit_original_response(content=pedacos[0], attachments=attachments)
                for pedaco in pedacos[1:]:
                    if pedaco.strip():
                        await interaction.channel.send(pedaco)
            else:
                await interaction.edit_original_response(content=resposta, attachments=attachments)
            return
        except Exception as e:
            print(f"⚠️ Erro ao editar original, enviando followup: {e}")

    kwargs = {"file": arquivo_discord} if arquivo_discord else {}
    if len(resposta) > 2000:
        pedacos = []
        while len(resposta) > 2000:
            corte = resposta.rfind("\n", 0, 1990)
            if corte == -1: corte = 1990
            pedacos.append(resposta[:corte])
            resposta = resposta[corte:]
        pedacos.append(resposta)
        try:
            await interaction.followup.send(pedacos[0], **kwargs)
            for pedaco in pedacos[1:]:
                if pedaco.strip():
                    await interaction.channel.send(pedaco)
        except discord.errors.Forbidden:
            print("⚠️ Sem permissão (403).")
        except Exception as e:
            print(f"Erro ao mandar blocos: {e}")
    else:
        try:
            await interaction.followup.send(resposta, **kwargs)
        except discord.errors.Forbidden:
            print("⚠️ Sem permissão (403 Forbidden).")
        except Exception as e:
            print(f"Erro ao mandar resposta: {e}")


# ══════════════════════════════════════════════════════════
#  COMANDOS DISCORD
# ══════════════════════════════════════════════════════════

# ── Helper de Processamento e Resposta ──────────────────
async def processar_e_enviar_resposta(interaction: discord.Interaction, mensagem: str, anexos_list: list):
    global ULTIMA_IMAGEM_GERADA, CONTEXTO_ATIVO, ULTIMO_ANEXO_IMAGEM
    ULTIMA_IMAGEM_GERADA = None
    ULTIMO_ANEXO_IMAGEM = None
    CONTEXTO_ATIVO = interaction

    is_img = eh_requisicao_imagem(mensagem)
    
    if is_img:
        await interaction.response.send_message("Gerando imagem..........")
    else:
        await interaction.response.defer(ephemeral=False)

    arquivos = []
    for a in anexos_list:
        tipo = a.content_type or ""
        if tipo.startswith("image/") or tipo.startswith("audio/") or tipo.startswith("video/"):
            try:
                arq_bytes = await a.read()
                arquivos.append((arq_bytes, tipo))
                if tipo.startswith("image/") and ULTIMO_ANEXO_IMAGEM is None:
                    ULTIMO_ANEXO_IMAGEM = (arq_bytes, tipo)
            except Exception as e:
                if is_img:
                    await interaction.edit_original_response(content=f"⚠️ Falha ao baixar o arquivo {a.filename}: {e}")
                else:
                    await interaction.followup.send(f"⚠️ Falha ao baixar o arquivo {a.filename}: {e}")
                return
        else:
            if is_img:
                await interaction.edit_original_response(content=f"⚠️ O anexo {a.filename} não rola, miga. Manda uma imagem, áudio ou vídeo!")
            else:
                await interaction.followup.send(f"⚠️ O anexo {a.filename} não rola, miga. Manda uma imagem, áudio ou vídeo!")
            return

    texto_envio = mensagem if mensagem else "[Enviou um arquivo em anexo sem nenhuma mensagem de texto. Analise o arquivo enviado diretamente (não use a ferramenta ver_tela_atual, pois o arquivo já foi enviado nos bytes do anexo)]"

    request_id = f"discord-{interaction.id}-{time.time_ns()}"
    try:
        resposta, img_gerada = await asyncio.wait_for(
            asyncio.to_thread(bot.processar_gemini, texto_envio, arquivos, "Discord", interaction, request_id),
            timeout=500
        )
    except asyncio.TimeoutError:
        bot.cancelar_requisicao(request_id)
        if is_img:
            await interaction.edit_original_response(content="⏱️ Travei aqui! O servidor demorou demais. Tenta de novo!")
        else:
            await interaction.followup.send("⏱️ Travei aqui! O servidor demorou demais. Tenta de novo!")
        return
    except Exception as e:
        if is_img:
            await interaction.edit_original_response(content=f"⚠️ Erro inesperado: {e}")
        else:
            await interaction.followup.send(f"⚠️ Erro inesperado: {e}")
        return

    arquivo_discord = None
    if img_gerada and Path(img_gerada).is_file():
        arquivo_discord = discord.File(img_gerada, filename=Path(img_gerada).name)

    await _enviar_resposta(interaction, resposta, arquivo_discord, edit_original=is_img)


# ── /ayla — EXCLUSIVO DA DONA ────────────────────────────
@bot.tree.command(name="ayla", description="Converse com a Ayla — controle total do PC")
@app_commands.describe(
    mensagem="O que quer que eu faça?",
    anexo="Anexo (imagem, áudio, vídeo)"
)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def cmd_ayla(
    interaction: discord.Interaction,
    mensagem: str = "",
    anexo: discord.Attachment = None
):
    if hasattr(bot, "blocked_users") and interaction.user.id in bot.blocked_users:
        await interaction.response.send_message(MSG_BLOQUEADO, ephemeral=True)
        return

    if interaction.user.id != DISCORD_OWNER_ID:
        if not getattr(bot, "public_mode", False):
            await interaction.response.send_message(MSG_MODO_PUBLICO_DESCONTINUADO)
            return

    anexos_list = [anexo] if anexo is not None else []
    if not mensagem.strip() and not anexos_list:
        await interaction.response.send_message("⚠️ Fala alguma coisa comigo primeiro ou mande um anexo! https://media.tenor.com/DyqH3PQFYpsAAAAC/burn.gif ", ephemeral=True)
        return

    await processar_e_enviar_resposta(interaction, mensagem, anexos_list)


# ── Bot Discord em thread separada ──
def run_discord_bot_thread():
    import threading
    global BOT_LAUNCH_ERROR
    def _run():
        global BOT_LAUNCH_ERROR
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            async def _start():
                async with bot:
                    await bot.start(DISCORD_TOKEN)
            loop.run_until_complete(_start())
        except Exception as e:
            BOT_LAUNCH_ERROR = str(e)
            print(f"\n⚠️ Erro crítico ao iniciar bot Discord: {e}\n")

    discord_thread = threading.Thread(target=_run, daemon=True)
    discord_thread.start()
    print ("Bot Discord iniciando em background...")


if __name__ == "__main__":
    from colorama import Fore, Back, Style
    print("\n" + "═" * 60)
    print(r"🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵")
    print(Fore.CYAN + r" .----------------. .----------------. .----------------. .----------------.")
    print(r"| .--------------. | .--------------. | .--------------. | .--------------. |")
    print(r"| |      __      | | |  ____  ____  | | |   _____      | | |      __      | |")
    print(r"| |     /  \     | | | |_  _||_  _| | | |  |_   _|     | | |     /  \     | |")
    print(r"| |    / /\ \    | | |   \ \  / /   | | |    | |       | | |    / /\ \    | |")
    print(r"| |   / ____ \   | | |    \ \/ /    | | |    | |   _   | | |   / ____ \   | |")
    print(r"| | _/ /    \ \_ | | |    _|  |_    | | |   _| |__/ |  | | | _/ /    \ \_ | |")
    print(r"| ||____|  |____|| | |   |______|   | | |  |________|  | | ||____|  |____|| |")
    print(r"| |              | | |              | | |              | | |              | |")
    print(r"| '--------------' | '--------------' | '--------------' | '--------------' |")
    print(r"'----------------' '----------------' '----------------' '------------------'")
    print(Style.RESET_ALL)
    print(r"🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵")
    #ola pessoa que esta olhando o codigo, essa é uma pequena assinatura que a ayla original deixou.
    #pra todo mundo que testar o codigo saber que la no fundo eu e ela nos dedicamos muito a fazer, voce pode tirar isso
    #mas é o ultimo resquicio que essa é a ayla original, e que ela é feita com muito carinho e dedicação, espero que voce entenda isso.


    print("═" * 60 + "\n")

    run_discord_bot_thread()

    # ── GUI opcional no thread principal ──
    abrir_gui_env = os.getenv("ABRIR_GUI", "true").lower() == "true"
    if abrir_gui_env:
        try:
            from ayla_gui import abrir_gui
            print("🩵 Abrindo interface gráfica...")
            abrir_gui(bot)
            asyncio.run(bot.terminal_loop())
        except Exception as e:
            print(f"⚠️ Erro ao abrir GUI: {e}")
            print("🩵 Voltando para o modo terminal...")
            asyncio.run(bot.terminal_loop())
    else:
        print("🩵 Abertura da GUI desativada por configuração (ABRIR_GUI=false).")
        asyncio.run(bot.terminal_loop())
