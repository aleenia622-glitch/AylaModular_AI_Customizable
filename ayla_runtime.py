"""Histórico global e registros de interação para respostas simultâneas."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
import copy
import threading
import time
import uuid

CURRENT_WORKER = ContextVar('ayla_worker', default=None)


def conversation_key(origin, context, owner_id):
    """Usa uma única conversa compartilhada em todas as interfaces da Ayla."""
    return 'global'


@dataclass
class Conversation:
    turns: dict = field(default_factory=dict)
    # Turnos removidos da janela recente só são apagados após resumo válido.
    archive: dict = field(default_factory=dict)
    context_summary: str = ""
    compacting: bool = False
    summary_error: str = ""
    sequence: int = 0
    continuous: set = field(default_factory=set)
    updated: float = field(default_factory=time.monotonic)


class ConversationStore:
    """Locks protegem apenas snapshots/commits, nunca rede ou ferramentas.

    Pedidos simultâneos usam o último histórico concluído. Resultados são
    incorporados na ordem de entrada, mesmo quando terminam fora de ordem.
    """
    def __init__(self, max_turns=6, max_sessions=100):
        self.lock = threading.RLock()
        self.sessions = {}
        self.max_turns = max_turns
        self.max_sessions = max_sessions
        self.pending = set()

    def begin(self, key):
        with self.lock:
            session = self.sessions.setdefault(key, Conversation())
            session.sequence += 1
            session.updated = time.monotonic()
            sequence = session.sequence
            self.pending.add((key, sequence))
            history = []
            for _, turn in sorted({**session.archive, **session.turns}.items()):
                history.extend(copy.deepcopy(turn))
            self._prune()
            return sequence, history, set(session.continuous)

    def finish(self, key, sequence, turn):
        with self.lock:
            session = self.sessions[key]
            session.turns[sequence] = copy.deepcopy(turn)
            for old in sorted(session.turns)[:-self.max_turns]:
                session.archive[old] = session.turns.pop(old)
            session.updated = time.monotonic()
            self.pending.discard((key, sequence))

    def abandon(self, key, sequence):
        with self.lock:
            self.pending.discard((key, sequence))

    def compact_context(self, key, summarize, max_chars=32000, target_chars=16000):
        """Compacta todo o snapshot; falhas e turnos concorrentes são preservados."""
        def snapshot(session):
            return session.context_summary, [copy.deepcopy(m)
                for _, turn in sorted({**session.archive, **session.turns}.items())
                for m in turn]

        with self.lock:
            session = self.sessions[key]
            previous, history = snapshot(session)
            if session.compacting or len(previous) + sum(len(m.text or '') for m in history) < max_chars:
                return previous, history
            earliest = min((seq for k, seq in self.pending if k == key), default=float('inf'))
            candidates = [(seq, copy.deepcopy(turn)) for seq, turn in
                          sorted({**session.archive, **session.turns}.items()) if seq < earliest]
            if not candidates:
                return previous, history
            session.compacting = True
        try:
            updated = summarize(previous, candidates)
            if not isinstance(updated, str) or not updated.strip() or len(updated) > target_chars:
                raise ValueError('Compactação vazia ou acima do orçamento.')
            with self.lock:
                session.context_summary = updated.strip()
                for seq, _ in candidates:
                    session.archive.pop(seq, None)
                    session.turns.pop(seq, None)
                session.summary_error = ''
        except Exception as exc:
            with self.lock:
                session.summary_error = type(exc).__name__
            print(f'⚠️ Compactação indisponível ({type(exc).__name__}); contexto integral preservado.')
        finally:
            with self.lock:
                session.compacting = False
        with self.lock:
            return snapshot(session)


    def select_continuous(self, key, name, active):
        with self.lock:
            session = self.sessions.setdefault(key, Conversation())
            if active:
                session.continuous.add(name)
            else:
                session.continuous.discard(name)

    def _prune(self):
        active = {key for key, _ in self.pending}
        for key in sorted(self.sessions, key=lambda k:self.sessions[k].updated):
            if len(self.sessions) <= self.max_sessions:
                break
            if key not in active and not self.sessions[key].compacting:
                del self.sessions[key]

    def summary(self):
        with self.lock:
            characters = sum(
                len(getattr(message, 'text', '') or '')
                for session in self.sessions.values()
                for turn in [*session.archive.values(), *session.turns.values()]
                for message in turn
            )
            characters += sum(len(s.context_summary) for s in self.sessions.values())
            return {'sessoes':len(self.sessions), 'interacoes_ativas':len(self.pending),
                    'resumos':sum(bool(s.context_summary) for s in self.sessions.values()),
                    'turnos_aguardando_resumo':sum(len(s.archive) for s in self.sessions.values()),
                    'turnos':sum(len(s.turns) for s in self.sessions.values()),
                    'tokens_estimados':characters//4}

    def save_to_file(self, path) -> bool:
        """Persiste os turnos recentes da conversa ativa em disco."""
        import json
        import os
        from pathlib import Path
        path = Path(path)
        with self.lock:
            data = {}
            for key, session in self.sessions.items():
                data[key] = {
                    "context_summary": session.context_summary,
                    "sequence": session.sequence,
                    "archive": {
                        str(seq): [
                            {"role": getattr(m, "role", "user"), "text": getattr(m, "text", "") or ""}
                            for m in turn if getattr(m, "text", None)
                        ]
                        for seq, turn in session.archive.items()
                    },
                    "turns": {
                        str(seq): [
                            {"role": getattr(m, "role", "user"), "text": getattr(m, "text", "") or ""}
                            for m in turn if getattr(m, "text", None)
                        ]
                        for seq, turn in session.turns.items()
                    },
                }
        try:
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, path)
            return True
        except Exception as exc:
            print(f"⚠️ Erro ao salvar conversa ativa: {exc}")
            return False

    def load_from_file(self, path) -> bool:
        """Carrega os turnos recentes da conversa ativa persistidos em disco."""
        import json
        from pathlib import Path
        path = Path(path)
        if not path.is_file():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return False
            from zai_provider import ZaiMessage
            with self.lock:
                for key, sdata in data.items():
                    session = self.sessions.setdefault(key, Conversation())
                    session.context_summary = sdata.get("context_summary", "")
                    session.sequence = int(sdata.get("sequence", 0))
                    for seq_str, turn_data in sdata.get("archive", {}).items():
                        session.archive[int(seq_str)] = [
                            ZaiMessage(role=m.get("role", "user"), text=m.get("text", ""))
                            for m in turn_data if m.get("role") in {"system", "user", "assistant"}
                        ]
                    for seq_str, turn_data in sdata.get("turns", {}).items():
                        session.turns[int(seq_str)] = [
                            ZaiMessage(role=m.get("role", "user"), text=m.get("text", ""))
                            for m in turn_data if m.get("role") in {"system", "user", "assistant"}
                        ]
            return True
        except Exception as exc:
            print(f"⚠️ Erro ao restaurar conversa ativa: {exc}")
            return False


def new_task_id():
    return uuid.uuid4().hex
