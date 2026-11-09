"""Cria modpacks Minecraft Forge/Fabric com mods e dependências do Modrinth."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    'ayla_minecraft_modpack', Path(__file__).parent / 'minecraft_modpack' / 'backend.py')
_backend = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_backend)


def register(tool_map, function_declarations):
    tool_map['pesquisar_mods_minecraft'] = _backend.pesquisar_mods_minecraft
    tool_map['criar_modpack_minecraft'] = _backend.criar_modpack_minecraft
    function_declarations.extend(_backend.declarations())
