"""Histórico persistente de custos estimados por provedor, sem mensagens ou chaves."""
from datetime import datetime
import json
import math
import os
from pathlib import Path
import tempfile
from threading import RLock
from uuid import uuid4


class RegistroConsumo:
    def __init__(self, caminho, *, tipo='estimativa_zai'):
        self.caminho = Path(caminho)
        self.tipo = tipo
        self.lock = RLock()
        self.sessoes = None
        self.nova_sessao()

    def nova_sessao(self):
        with self.lock:
            self.sessao_id = uuid4().hex
            self.iniciada_em = datetime.now().astimezone().isoformat()

    def _carregar(self):
        if self.sessoes is None:
            try:
                dados = json.loads(self.caminho.read_text(encoding='utf-8'))
            except FileNotFoundError:
                dados = {'sessoes': {}}
            sessoes = dados['sessoes']
            if not isinstance(sessoes, dict):
                raise ValueError('Histórico de consumo inválido; arquivo preservado.')
            for sessao in sessoes.values():
                valor = sessao['custo_estimado_usd']
                if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor) or valor < 0:
                    raise ValueError('Custo inválido no histórico; arquivo preservado.')
            self.sessoes = sessoes

    def salvar(self, custo_sessao):
        with self.lock:
            self._carregar()
            sessoes = dict(self.sessoes)
            sessoes[self.sessao_id] = {
                'iniciada_em': self.iniciada_em,
                'atualizada_em': datetime.now().astimezone().isoformat(),
                'custo_estimado_usd': custo_sessao,
            }
            dados = {'versao': 1, 'moeda': 'USD', 'tipo': self.tipo,
                     'total_estimado_usd': math.fsum(s['custo_estimado_usd'] for s in sessoes.values()),
                     'sessoes': sessoes}
            temporario = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                        dir=self.caminho.parent, prefix=self.caminho.name + '.',
                        suffix='.tmp', delete=False) as arquivo:
                    temporario = arquivo.name
                    json.dump(dados, arquivo, ensure_ascii=False, indent=2, allow_nan=False)
                    arquivo.flush()
                    os.fsync(arquivo.fileno())
                os.replace(temporario, self.caminho)
                self.sessoes = sessoes
            finally:
                if temporario and os.path.exists(temporario):
                    os.unlink(temporario)

    def total(self, custo_sessao):
        with self.lock:
            self._carregar()
            return math.fsum([custo_sessao, *(s['custo_estimado_usd']
                for chave, s in self.sessoes.items() if chave != self.sessao_id)])
