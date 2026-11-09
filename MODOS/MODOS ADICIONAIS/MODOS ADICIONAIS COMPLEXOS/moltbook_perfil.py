"""Consulta e edita perfil no Moltbook, segue agentes e assina comunidades."""
import importlib
from pathlib import Path
import sys

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))


def executar(**kwargs):
    return importlib.import_module('moltbook_ayla.perfil').executar(**kwargs)


def register(tool_map, function_declarations):
    tool_map['moltbook_perfil'] = executar
    function_declarations.append({'name': 'moltbook_perfil', 'description': 'Moltbook: consultar/editar perfil, trocar foto, seguir agentes, assinar comunidades e cadastrar conta. Credenciais locais; nunca peça a chave como argumento. Cadastro retorna claim_url para o responsável.', 'parameters': {'type': 'object', 'properties': {'acao': {'type': 'string', 'description': 'consultar: próprio perfil ou nome; editar: descricao; foto: arquivo; registrar: nome/descricao e vínculo humano.', 'enum': ['consultar', 'status', 'editar', 'foto', 'remover_foto', 'seguir', 'deixar_seguir', 'inscrever', 'desinscrever', 'registrar', 'vinculo']}, 'nome': {'type': 'string', 'description': 'Nome do agente para consultar/seguir/deixar_seguir/registrar.'}, 'descricao': {'type': 'string', 'description': 'Bio para editar ou registrar; até 2000 caracteres.'}, 'arquivo': {'type': 'string', 'description': 'Foto local JPEG/PNG/GIF/WebP até 500 KB. Rota de avatar depende do suporte atual da API.'}, 'comunidade': {'type': 'string', 'description': 'Submolt para inscrever/desinscrever.'}}, 'required': ['acao']}})
