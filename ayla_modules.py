"""Catálogo compartilhado; seleção de ferramentas exclusiva de cada interação."""
from __future__ import annotations
import ast
from collections.abc import MutableMapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
import copy
import importlib.util
from pathlib import Path
import sys
import threading
import uuid

ACTIVE_REGISTRY = ContextVar('ayla_module_registry', default=None)


@dataclass
class Registry:
    tools: dict = field(default_factory=dict)
    declarations: list = field(default_factory=list)
    modules: dict = field(default_factory=dict)
    by_module: dict = field(default_factory=dict)
    complex: set = field(default_factory=set)
    prepared_declarations: list | None = None
    prepared_tools: list | None = None


class MapView(MutableMapping):
    def __init__(self, manager, attr): self.manager, self.attr = manager, attr
    def data(self): return getattr(self.manager.registry(), self.attr)
    def __getitem__(self, key): return self.data()[key]
    def __setitem__(self, key, val): self.data()[key] = val
    def __delitem__(self, key): del self.data()[key]
    def __iter__(self): return iter(self.data().copy())
    def __len__(self): return len(self.data())
    def copy(self): return self.data().copy()


class DeclarationView(Sequence):
    def __init__(self, manager): self.manager = manager
    def __getitem__(self, key): return self.manager.registry().declarations[key]
    def __len__(self): return len(self.manager.registry().declarations)

    def prepare_tools(self, build):
        registry = self.manager.registry()
        # Comparação também detecta edições diretas/legadas de declarações.
        if (getattr(registry, 'prepared_tools', None) is None or
                registry.prepared_declarations != registry.declarations):
            registry.prepared_tools = build()
            registry.prepared_declarations = copy.deepcopy(registry.declarations)
        # Cada configuração recebe sua própria estrutura mutável.
        return copy.deepcopy(registry.prepared_tools)


class ModuleManager:
    def __init__(self, base, context_factory, on_change=None):
        self.base = Path(base)
        self.context_factory = context_factory
        self.on_change = on_change or (lambda:None)
        self.lock = threading.RLock()
        self.catalog = {}
        self.tool_index = {}
        self.essential = set()
        self.continuous = set()
        self.cache = {}
        self.errors = {}
        self.default = Registry()
        self.tool_view = MapView(self, 'tools')
        self.declaration_view = DeclarationView(self)
        self.module_view = MapView(self, 'modules')

    def registry(self):
        return ACTIVE_REGISTRY.get() or self.default

    def discover(self):
        """Atualiza catálogo sem destruir instâncias usadas por tarefas em curso."""
        with self.lock:
            catalog, index, essential, continuous = {}, {}, set(), set()
            self.errors.clear()
            folders = [(self.base/'MODOS ESSENCIAIS', 'essencial'),
                       (self.base/'MODOS ADICIONAIS', 'adicional'),
                       (self.base/'MODOS ADICIONAIS CONTINUOS', 'continuo'),
                       (self.base/'MODOS ADICIONAIS CONTÍNUOS', 'continuo'),
                       (self.base/'MODOS ADICIONAIS'/'MODOS ADICIONAIS COMPLEXOS', 'complexo')]
            for folder, kind in folders:
                for path in sorted(folder.glob('*.py')):
                    name = path.stem.lower()
                    try:
                        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
                        doc = (ast.get_docstring(tree) or name).strip().splitlines()[0][:180]
                        names = set()
                        for node in ast.walk(tree):
                            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id in {'TOOL_MAP','tool_map'}:
                                try:
                                    value = ast.literal_eval(node.slice)
                                    if isinstance(value,str): names.add(value)
                                except (ValueError,TypeError): pass
                        catalog[name] = {'caminho':path,'descricao':doc,'tipo':kind,'continuo':kind=='continuo','ferramentas':sorted(names)}
                        index.update({tool:name for tool in names})
                        if kind=='essencial': essential.add(name)
                        if kind=='continuo': continuous.add(name)
                    except Exception as exc:
                        self.errors[name] = str(exc)
            self.catalog.clear(); self.catalog.update(catalog)
            self.tool_index.clear(); self.tool_index.update(index)
            self.essential.clear(); self.essential.update(essential)
            self.continuous.clear(); self.continuous.update(continuous)
            # Serviços contínuos conservam a instância; demais serão atualizados
            # nas próximas ativações, sem mudar referências de pedidos em andamento.
            self.cache = {k:v for k,v in self.cache.items() if k in continuous}
            self.default = self.new_registry()

    def _load(self, name):
        with self.lock:
            if name in self.cache: return self.cache[name]
            info = self.catalog[name]
            path = info['caminho']
            identifier = f'ayla_modo_{name}_{uuid.uuid4().hex}'
            spec = importlib.util.spec_from_file_location(identifier,path)
            module = importlib.util.module_from_spec(spec)
            tools, declarations = {}, []
            module.__dict__.update(self.context_factory())
            module.TOOL_MAP, module.FUNCTION_DECLARATIONS = tools, declarations
            sys.modules[identifier] = module
            try:
                # Leia o fonte atual mesmo em edições com mesmo tamanho/mtime.
                exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
                if not tools and callable(getattr(module,'register',None)):
                    module.register(tools,declarations)
                for declaration in declarations:
                    if declaration['name'] not in tools:
                        raise ValueError(f"Declaração sem implementação: {declaration['name']}")
                if not declarations:
                    raise ValueError('Módulo não registrou ferramentas.')
                # Uso posterior consulta a seleção corrente; não sobrescreve
                # funções e imports próprios com globals de outros módulos.
                module.TOOL_MAP = self.tool_view
                module.FUNCTION_DECLARATIONS = self.declaration_view
                result = (module,tools,copy.deepcopy(declarations))
                self.cache[name] = result
                info['ferramentas'] = [d['name'] for d in declarations]
                self.tool_index.update({d['name']:name for d in declarations})
                self.errors.pop(name,None)
                return result
            except Exception as exc:
                self.errors[name] = str(exc)
                raise
            finally:
                # Referências de funções mantêm o namespace vivo; dispensa
                # registro permanente para cada versão recarregada.
                sys.modules.pop(identifier,None)

    def _expose(self, registry, name, only=None):
        module, tools, declarations = self._load(name)
        selected = [d for d in declarations if only is None or d['name']==only]
        if only and not selected: raise ValueError(f'Ferramenta não encontrada: {only}')
        registry.modules[name] = module
        if only is None:
            # Aliases legados continuam executáveis sem duplicar schemas.
            registry.tools.update(tools)
            registry.by_module.setdefault(name,set()).update(tools)
        known = {d['name'] for d in registry.declarations}
        for d in selected:
            registry.tools[d['name']] = tools[d['name']]
            if d['name'] not in known:
                registry.declarations.append(copy.deepcopy(d))
                known.add(d['name'])
            registry.by_module.setdefault(name,set()).add(d['name'])
        return selected

    def reload(self):
        """Atualiza a seleção corrente sem alterar registros de outras tarefas."""
        with self.lock:
            current = self.registry()
            selected = {name: set(names) for name, names in current.by_module.items()}
            complex_names = set(current.complex)
            self.discover()
            if self.errors:
                raise RuntimeError(f'Falha ao atualizar catálogo: {self.errors}')
            refreshed = self.new_registry(set(current.modules) & self.continuous)
            if self.errors:
                raise RuntimeError(f'Falha ao carregar módulos: {self.errors}')
            for name in current.modules:
                if name not in self.catalog or name in self.essential or name in self.continuous:
                    continue
                if name in complex_names:
                    module, _, _ = self._load(name)
                    refreshed.modules[name] = module
                    refreshed.complex.add(name)
                    for tool in sorted(selected.get(name, ())):
                        self._expose(refreshed, name, tool)
                else:
                    self._expose(refreshed, name)
            current.tools = refreshed.tools
            current.declarations = refreshed.declarations
            current.modules = refreshed.modules
            current.by_module = refreshed.by_module
            current.complex = refreshed.complex
            if ACTIVE_REGISTRY.get() is None:
                self.default = current
            self.on_change()

    def new_registry(self, retained=()):
        reg = Registry()
        for name in sorted(self.essential | (set(retained)&self.continuous)):
            try: self._expose(reg,name)
            except Exception as exc: print(f'❌ Módulo indisponível {name}: {exc}')
        self._meta(reg)
        return reg

    def _meta(self, reg):
        # Resumos orientam a escolha inicial; schemas completos só são expostos
        # quando o módulo ou a ferramenta é ativado.
        choices = '\n'.join(
            f"{name}: {info['descricao']}"
            for name, info in sorted(self.catalog.items())
            if name not in self.essential
        )
        metas = [
            ('ativar_modulo', self.activate, 'Ativa um módulo pelo nome. Disponíveis:\n'+choices,
             {'nome_modulo':{'type':'string'}}, ['nome_modulo']),
            ('ativar_ferramenta', self.activate_tool, 'Após ativar um módulo complexo, expõe somente os parâmetros da ferramenta escolhida.',
             {'nome_modulo':{'type':'string'},'nome_ferramenta':{'type':'string'}}, ['nome_modulo','nome_ferramenta']),
            ('desativar_modulo', self.deactivate, 'Retira um modo do contexto; serviços contínuos são encerrados quando possuem rotina de parada.',
             {'nome_modulo':{'type':'string'}}, ['nome_modulo'])]
        for name,fn,description,props,required in metas:
            reg.tools[name] = fn
            reg.declarations.append({'name':name,'description':description,'parameters':{'type':'object','properties':props,'required':required}})

    def resolve(self, name):
        name = str(name).strip().removesuffix('.py').lower()
        if name in self.catalog: return name
        norm = name.replace(' ', '_')
        if norm in self.catalog: return norm
        matches = [n for n in self.catalog if (name and (name in n or n in name)) or (norm and (norm in n or n in norm))]
        matches = list(dict.fromkeys(matches))
        if len(matches)==1: return matches[0]
        raise ValueError('Informe um nome de módulo válido e sem ambiguidade.')

    def activate(self, nome_modulo):
        try:
            name = self.resolve(nome_modulo)
            reg = self.registry()
            if self.catalog[name]['tipo']=='complexo':
                module,_,decls = self._load(name)
                reg.modules[name] = module
                reg.complex.add(name)
                short = '\n'.join(f"• {d['name']}: {d.get('description','').splitlines()[0][:130]}" for d in decls)
                return f'Módulo {name} selecionado. Use ativar_ferramenta com um dos nomes abaixo; apenas ela receberá declaração completa.\n{short}'
            decls = self._expose(reg,name)
            self._retain(name,True)
            self.on_change()
            return f'Módulo {name} ativo. Ferramentas: '+', '.join(d['name'] for d in decls)
        except Exception as exc: return f'Erro ao ativar módulo: {exc}'

    def activate_tool(self, nome_modulo, nome_ferramenta):
        try:
            name = self.resolve(nome_modulo)
            reg = self.registry()
            if name not in reg.complex:
                return 'Erro: ative primeiro o módulo complexo com ativar_modulo.'
            decls = self._expose(reg,name,str(nome_ferramenta).strip())
            self.on_change()
            import json
            return json.dumps(decls[0],ensure_ascii=False)
        except Exception as exc: return f'Erro ao ativar ferramenta: {exc}'

    def _retain(self,name,active):
        from ayla_runtime import CURRENT_WORKER
        worker = CURRENT_WORKER.get()
        if worker and name in self.continuous:
            worker._conversation_store.select_continuous(worker._conversation_key,name,active)

    def deactivate(self, nome_modulo):
        try:
            name = self.resolve(nome_modulo)
            if name in self.essential: return 'Erro: modo essencial não pode ser desativado.'
            reg = self.registry()
            module = reg.modules.get(name)
            if module and name in self.continuous:
                stop = getattr(module,'shutdown',None)
                if callable(stop): stop()
            names = reg.by_module.pop(name,set())
            for tool in names: reg.tools.pop(tool,None)
            reg.declarations[:] = [d for d in reg.declarations if d['name'] not in names]
            reg.modules.pop(name,None); reg.complex.discard(name)
            self._retain(name,False)
            self.on_change()
            return f'Módulo {name} desativado.'
        except Exception as exc: return f'Erro ao desativar: {exc}'

    def available_function(self, name):
        reg = self.registry()
        if name in reg.tools: return reg.tools[name]
        module = self.tool_index.get(name)
        if module and self.catalog[module]['tipo']!='complexo':
            self.activate(module)
            return reg.tools.get(name)
        return None

    def status(self):
        with self.lock:
            return [{'nome':n,'tipo':i['tipo'],'status':'indisponivel' if n in self.errors else ('carregado' if n in self.cache else 'sob demanda'),
                     'erro':self.errors.get(n,''),'ferramentas':len(i['ferramentas'])} for n,i in sorted(self.catalog.items())]
