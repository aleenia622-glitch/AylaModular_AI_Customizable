"""Relevância da memória: texto por palavras e semântica com abstinência.

Funções puras; não acessam arquivos, rede nem dados fora do escopo recebido.
As pontuações são sinais de ordenação, nunca probabilidades de acerto.
"""
from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
import math
import re
from statistics import median
import unicodedata

# Pisos conservadores; o corte também considera o ruído da própria consulta.
MIN_SEMANTIC = 0.64
MIN_SEMANTIC_ONLY = 0.68
MIN_SEMANTIC_SHORT = 0.70
_GENERIC_TAGS = {"gerais", "pessoal", "preferencias", "projetos", "regras", "momentos"}
_QUERY_FILLER = {"lembra", "lembrar", "lembre", "lembranca", "memoria", "memorias",
                 "sabe", "saber", "sobre", "qual", "quais", "quem", "quando", "onde"}


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or "").casefold())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", texto))


def _plural(token):
    if len(token) >= 4 and token.endswith(("oes", "aes")):
        return token[:-3] + "ao"
    if len(token) >= 5 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def _palavras(texto, ignoradas):
    return [_plural(t) for t in normalizar(texto).split() if len(t) >= 2 and t not in ignoradas]


def texto_embedding_memoria(chave, registro):
    """Título legível e conteúdo; categorias genéricas e IDs não descrevem o fato."""
    titulo = " ".join(t for t in normalizar(chave).split() if not t.isdigit())
    valor = str(registro.get("Valor", "")).strip()
    return f"{titulo}\n{valor}" if titulo else valor


def _erro_leve(a, b):
    # Palavras curtas/números não podem produzir acertos por aproximação.
    if min(len(a), len(b)) < 5 or a.isdigit() or b.isdigit() or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diffs = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        return (len(diffs) == 1 or (len(diffs) == 2 and diffs[1] == diffs[0] + 1
                and a[diffs[0]] == b[diffs[1]] and a[diffs[1]] == b[diffs[0]]))
    curto, longo = (a, b) if len(a) < len(b) else (b, a)
    i = next((i for i, (x, y) in enumerate(zip(curto, longo)) if x != y), len(curto))
    return curto[i:] == longo[i + 1:]


class BuscaMemorias:
    """Calcula sinais léxicos uma vez e combina somente evidências relevantes."""

    def __init__(self, consulta, documentos, ignoradas=()):
        self.consulta = normalizar(consulta)
        ignoradas = {normalizar(p) for p in ignoradas}
        self.tokens = set(_palavras(consulta, ignoradas | _QUERY_FILLER))
        self.docs = {}
        df = Counter()
        for chave, reg in documentos.items():
            titulo = _palavras(chave, ignoradas)
            valor = _palavras(reg.get("Valor", ""), ignoradas)
            tags = _palavras(" ".join(t for t in reg.get("tags", [])
                                    if normalizar(t) not in _GENERIC_TAGS), ignoradas)
            tf = Counter(valor)
            for t in titulo:
                tf[t] += 0.8
            for t in tags:
                tf[t] += 0.3
            self.docs[chave] = (tf, max(1, len(valor) + len(titulo)), normalizar(reg.get("Valor", "")),
                                normalizar(chave))
            df.update(tf.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5))
                    for t in self.tokens}
        self.peso_total = sum(self.idf.values()) or 1.0
        self.media_tamanho = sum(d[1] for d in self.docs.values()) / max(1, n)
        self.lexicos = {chave: self._lexico(chave) for chave in self.docs}

    def _lexico(self, chave):
        tf, tamanho, valor, titulo = self.docs[chave]
        exatas = self.tokens.intersection(tf)
        aproximadas = {}
        for token in self.tokens - exatas:
            matches = [t for t in tf if _erro_leve(token, t)]
            if matches:
                aproximadas[token] = max(matches, key=lambda t: SequenceMatcher(None, token, t).ratio())
        cobertura = (sum(self.idf[t] for t in exatas)
                     + 0.65 * sum(self.idf[t] for t in aproximadas)) / self.peso_total
        # Um termo incidental numa pergunta com vários assuntos não basta.
        minimo = 0.22 if len(self.tokens) > 8 else (0.40 if len(self.tokens) > 3 else 0.55)
        aceito = bool(exatas or aproximadas) and cobertura >= minimo
        bm25 = 0.0
        for token in exatas | aproximadas.keys():
            freq = tf[token if token in exatas else aproximadas[token]]
            peso = 1.0 if token in exatas else 0.65
            bm25 += peso * self.idf[token] * freq * 2.2 / (
                freq + 1.2 * (0.25 + 0.75 * tamanho / self.media_tamanho))
        frase = bool(self.tokens and self.consulta and (
            f" {self.consulta} " in f" {valor} " or f" {self.consulta} " in f" {titulo} "))
        score = 5.0 * cobertura + 1.5 * bm25 / (bm25 + 2.0) + (0.6 if frase else 0)
        return {"aceito": aceito, "pontuacao": score if aceito else 0.0,
                "cobertura": round(cobertura, 4), "termos": sorted(exatas),
                "aproximacoes": aproximadas, "frase": frase}

    def combinar(self, semanticas, diagnostico=None):
        # NaN/inf, documentos externos e valores inválidos jamais influenciam o corte.
        scores = {}
        for chave, score in semanticas.items():
            if chave not in self.docs:
                continue
            try:
                score = float(score)
            except (ValueError, TypeError):
                continue
            if math.isfinite(score) and -1 <= score <= 1:
                scores[chave] = score
        base = MIN_SEMANTIC
        if len(scores) >= 8:
            centro = median(scores.values())
            mad = median(abs(s - centro) for s in scores.values())
            base = max(base, min(0.84, centro + max(0.05, 2.5 * mad)))
        curto = len(self.tokens) <= 1
        corte_semantico = max(base, MIN_SEMANTIC_SHORT if curto else MIN_SEMANTIC_ONLY)
        resultados = {}
        for chave, lex in self.lexicos.items():
            sem = scores.get(chave)
            sem_aceita = bool(self.tokens and sem is not None and sem >= (
                base if lex["aceito"] else corte_semantico))
            if not lex["aceito"] and not sem_aceita:
                continue
            motivos = []
            if lex["aceito"]:
                if lex["termos"]:
                    motivos.append("palavras correspondentes")
                if lex["aproximacoes"]:
                    motivos.append("plural ou erro de digitação")
                if lex["frase"]:
                    motivos.append("frase exata")
            if sem_aceita:
                motivos.append("similaridade semântica acima do corte")
            # Só a margem acima do ruído soma pontos; cosseno bruto não é confiança.
            bonus = 2.5 * max(0.0, (sem - base) / max(0.01, 1 - base)) if sem_aceita else 0.0
            resultados[chave] = {
                "pontuacao": lex["pontuacao"] + bonus,
                "evidencias": {"motivos": motivos, "termos": lex["termos"],
                               "aproximacoes": lex["aproximacoes"], "cobertura": lex["cobertura"],
                               "lexica": round(lex["pontuacao"], 4),
                               "semantica": round(sem, 4) if sem is not None else None,
                               "corte_semantico": round(base if lex["aceito"] else corte_semantico, 4)}}
        if diagnostico is not None:
            diagnostico.update(candidatas=len(self.docs), relevantes=len(resultados),
                               descartadas=len(self.docs) - len(resultados),
                               corte_semantico=round(corte_semantico, 4),
                               termos_consulta=sorted(self.tokens))
        return resultados
