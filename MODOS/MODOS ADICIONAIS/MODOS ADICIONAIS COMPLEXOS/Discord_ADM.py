"""Administra membros, cargos, canais, mensagens e servidores do Discord."""
import importlib
import json
from functools import partial
from pathlib import Path
import sys

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path: sys.path.insert(0,str(_DIR))
_OPERACOES = {'discord_adm_guild_info': ('servidor', 'discord_adm_guild_info'), 'discord_adm_get_audit_logs': ('servidor', 'discord_adm_get_audit_logs'), 'discord_adm_edit_guild': ('servidor', 'discord_adm_edit_guild'), 'discord_adm_ban_member': ('membros', 'discord_adm_ban_member'), 'discord_adm_unban_member': ('membros', 'discord_adm_unban_member'), 'discord_adm_list_bans': ('membros', 'discord_adm_list_bans'), 'discord_adm_kick_member': ('membros', 'discord_adm_kick_member'), 'discord_adm_timeout_member': ('membros', 'discord_adm_timeout_member'), 'discord_adm_edit_member': ('membros', 'discord_adm_edit_member'), 'discord_adm_prune_members': ('membros', 'discord_adm_prune_members'), 'discord_adm_create_role': ('cargos', 'discord_adm_create_role'), 'discord_adm_edit_role': ('cargos', 'discord_adm_edit_role'), 'discord_adm_delete_role': ('cargos', 'discord_adm_delete_role'), 'discord_adm_manage_member_roles': ('cargos', 'discord_adm_manage_member_roles'), 'discord_adm_list_channels': ('canais', 'discord_adm_list_channels'), 'discord_adm_get_channel_info': ('canais', 'discord_adm_get_channel_info'), 'discord_adm_create_channel': ('canais', 'discord_adm_create_channel'), 'discord_adm_edit_channel': ('canais', 'discord_adm_edit_channel'), 'discord_adm_delete_channel': ('canais', 'discord_adm_delete_channel'), 'discord_adm_purge_messages': ('mensagens', 'discord_adm_purge_messages'), 'discord_adm_set_channel_permissions': ('canais', 'discord_adm_set_channel_permissions'), 'discord_adm_manage_thread': ('canais', 'discord_adm_manage_thread'), 'discord_adm_list_members': ('membros', 'discord_adm_list_members'), 'discord_adm_read_channel_messages': ('mensagens', 'discord_adm_read_channel_messages'), 'discord_adm_manage_emojis_stickers': ('servidor', 'discord_adm_manage_emojis_stickers'), 'discord_adm_add_emoji': ('servidor', 'discord_adm_add_emoji'), 'discord_adm_add_sticker': ('servidor', 'discord_adm_add_sticker'), 'discord_adm_manage_invites': ('servidor', 'discord_adm_manage_invites'), 'discord_adm_manage_webhooks': ('servidor', 'discord_adm_manage_webhooks'), 'discord_adm_manage_scheduled_events': ('servidor', 'discord_adm_manage_scheduled_events'), 'discord_adm_manage_voice': ('servidor', 'discord_adm_manage_voice'), 'discord_adm_manage_templates_integrations': ('servidor', 'discord_adm_manage_templates_integrations')}

def _executar(grupo, funcao, **kwargs):
    modulo = importlib.import_module(f'discord_adm.{grupo}')
    return getattr(modulo,funcao)(**kwargs)

def register(tool_map, function_declarations):
    declarations = json.loads((_DIR/'discord_adm'/'declaracoes.json').read_text(encoding='utf-8'))
    for declaration in declarations:
        group, function = _OPERACOES[declaration['name']]
        tool_map[declaration['name']] = partial(_executar,group,function)
        function_declarations.append(declaration)
