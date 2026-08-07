import sys
import io
import time
import threading
from pathlib import Path
import requests
from voicevox_core.blocking import Onnxruntime, OpenJtalk, Synthesizer, VoiceModelFile


# Garante que a entrada e a saída do terminal usem UTF-8 para evitar erros de codificação
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stdin.reconfigure(encoding='utf-8')
except AttributeError:
    pass

# Importa bibliotecas para embelezar o terminal
try:
    from rich.console import Console
    from rich.prompt import Prompt, IntPrompt
    from rich.status import Status
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# Importa o mixer do Pygame para reprodução de áudio
try:
    import pygame
    HAS_PLAYBACK = True
except ImportError:
    HAS_PLAYBACK = False


import re

def portuguese_to_katakana(text):
    """
    Converte texto em Português Brasileiro diretamente para Katakana.

    Usa um scanner caractere-por-caractere que processa cada palavra individualmente,
    aplicando regras de pronúncia do português brasileiro e emitindo Katakana diretamente.

    Regras implementadas:
    - Redução de vogais finais brasileiras (o→u, e→i)
    - Redução de vogais pretônicas (o→u, e→i antes da tônica)
    - Palatalização brasileira (ti→chi, di→ji, te final→chi, de final→ji)
    - R forte no início de palavra e após n/l/s (→ ハ行)
    - R fraco entre vogais (→ ラ行)
    - S entre vogais vira Z (→ ザ行)
    - S antes de consoante sonora vira Z
    - L antes de consoante/final → ウ
    - Dígrafos: nh→ニャ行, lh→リャ行, ch→シャ行, rr→ハ行, ss→サ行, sc→サ行
    - Vogais nasais: ão→アン, ãe→アイン, etc.
    - Ditongo 'ou' simplificado para 'o' (brasileiro)
    - Palavras monossilábicas átonas (de→ジ, se→シ, que→キ, etc.)
    - Pontuação japonesa para pausas naturais
    """
    text = text.lower()

    # Divide em tokens: palavras, pontuação, espaços
    tokens = re.findall(r"[a-záàâãéêíóôõúüç]+|[^\sa-záàâãéêíóôõúüç]+|\s+", text)

    punct_map = str.maketrans({
        ',': '、', '.': '。', '?': '？', '!': '！',
        ';': '、', ':': '、', '(': '（', ')': '）',
        '"': '「', "'": '」',
    })

    # Palavras monossilábicas átonas comuns → conversão direta
    # Essas palavras em fala natural são reduzidas e palatalizadas
    MONO = {
        'de': 'ジ', 'do': 'ド', 'da': 'ダ', 'dos': 'ドス', 'das': 'ダス',
        'se': 'シ', 'te': 'テ', 'me': 'ミ', 'lhe': 'リ',
        'que': 'キ', 'e': 'イ', 'o': 'オ', 'a': 'ア', 'os': 'ウス', 'as': 'アス',
        'em': 'エン', 'um': 'ウン', 'uns': 'ウンス', 'uma': 'ウマ', 'umas': 'ウマス',
        'por': 'ポ-', 'com': 'コン', 'sem': 'セン', 'mas': 'マス',
        'ou': 'オ', 'ao': 'アウ', 'aos': 'アウス', 'na': 'ナ', 'no': 'ノ',
        'nas': 'ナス', 'nos': 'ヌス', 'nem': 'ネン', 'já': 'ジャ',
        'são': 'サン', 'não': 'ナン', 'tão': 'タン', 'mão': 'マン',
        'pão': 'パン', 'eu': 'エウ', 'tu': 'トゥ', 'ele': 'エリ',
        'ela': 'エラ', 'nós': 'ノス', 'ayla': 'アイラ', 'shy': 'シャイ',
        'aura': 'アウラ', 'voce': 'ゔぉせ',
    }

    parts = []
    for token in tokens:
        if token.isspace():
            continue  # Japonês não usa espaços entre palavras
        elif re.match(r'[a-záàâãéêíóôõúüç]', token):
            # Verifica se é uma palavra monossilábica conhecida
            if token in MONO:
                parts.append(MONO[token])
            else:
                parts.append(_pt_word_to_katakana(token))
        else:
            parts.append(token.translate(punct_map))

    return ''.join(parts)


def _pt_word_to_katakana(word):
    """Converte uma única palavra portuguesa diretamente para Katakana."""

    # === Fase 0: Detectar vogal final acentuada ANTES de normalizar ===
    # Vogais acentuadas (é, ó, ê, etc.) indicam sílaba tônica.
    # Se a última vogal da palavra é acentuada, NÃO reduzimos ela.
    # Ex: "café" (é acentuado) → カフェ, não カフィ
    #     "avó" (ó acentuado) → アボ, não アブ
    stressed_ending = False
    _stressed_vowels = set('áéíóúâêô')
    _check = word.rstrip('s')  # Remove 's' do plural para checar ("japonês" → "japonê")
    if _check and _check[-1] in _stressed_vowels:
        stressed_ending = True

    # === Fase 1: Normalizar acentos (preserva ã/õ para tratamento nasal) ===
    accent_map = {
        'à': 'a', 'â': 'a', 'á': 'a',
        'é': 'e', 'ê': 'e',
        'í': 'i',
        'ó': 'o', 'ô': 'o',
        'ú': 'u', 'ü': 'u',
    }
    word = ''.join(accent_map.get(c, c) for c in word)

    # === Fase 2: Pré-processar padrões nasais (ordem: mais longo primeiro) ===
    # Usa 'ss' (não 's') em ção/ções para evitar vozeamento inter-vocálico
    word = word.replace('ções', 'ssoins')
    word = word.replace('ção', 'ssan')
    word = word.replace('ão', 'an')
    word = word.replace('ãe', 'ain')
    word = word.replace('ãi', 'ain')
    word = word.replace('ã', 'an')
    word = word.replace('ões', 'oins')
    word = word.replace('õe', 'oin')
    word = word.replace('õ', 'on')

    # Terminações nasais (m final de palavra → n para som nasal ン)
    word = re.sub(r'em$', 'en', word)
    word = re.sub(r'am$', 'an', word)
    word = re.sub(r'im$', 'in', word)
    word = re.sub(r'om$', 'on', word)
    word = re.sub(r'um$', 'un', word)

    # ç → ss (sempre som de /s/, 'ss' previne vozeamento inter-vocálico)
    word = word.replace('ç', 'ss')

    # === Fase 2.5: Simplificações de ditongos brasileiros ===
    # 'ou' → 'ö' (marcador: 'o' que não pode ser reduzido a 'u')
    # Em brasileiro, 'ou' sempre soa como /o/: sou→/so/, outro→/otru/
    word = word.replace('ou', 'ö')
    # 'ei' antes de consoante → 'ë' (marcador: 'e' que não pode ser reduzido a 'i')
    # Em fala casual: primeiro→/primeru/, dinheiro→/dʒiɲeru/
    word = re.sub(r'ei(?=[^aeiouöë])', 'ë', word)

    # === Fase 3: Scanner caractere-por-caractere com saída Katakana direta ===
    VOWELS = set('aeiouöë')  # ö e ë são vogais marcadas
    n = len(word)
    result = []
    i = 0

    def at(pos):
        return word[pos] if 0 <= pos < n else ''

    def starts(s):
        return word[i:i+len(s)] == s

    def is_v(c):
        return c in VOWELS

    def final_v(v, pos):
        """Aplica redução de vogais finais do português brasileiro."""
        # Marcadores de ditongo simplificado: ö=ou→o, ë=ei→e (NÃO reduzir)
        if v == 'ö': return 'o'
        if v == 'ë': return 'e'
        # Não reduz se a vogal final era acentuada na palavra original
        if stressed_ending:
            return v
        rest = word[pos+1:]
        # Vogal final ou seguida apenas de 's' (plural)
        if not rest or rest == 's':
            if v == 'o': return 'u'
            if v == 'e': return 'i'
        return v

    # Tabela Katakana: (chave_consoante, vogal) → katakana
    CV = {
        # Básicos
        ('k','a'): 'カ', ('k','i'): 'キ', ('k','u'): 'ク', ('k','e'): 'ケ', ('k','o'): 'コ',
        ('s','a'): 'サ', ('s','i'): 'シ', ('s','u'): 'ス', ('s','e'): 'セ', ('s','o'): 'ソ',
        ('t','a'): 'タ', ('t','i'): 'チ', ('t','u'): 'トゥ', ('t','e'): 'テ', ('t','o'): 'ト',
        ('n','a'): 'ナ', ('n','i'): 'ニ', ('n','u'): 'ヌ', ('n','e'): 'ネ', ('n','o'): 'ノ',
        ('h','a'): 'ハ', ('h','i'): 'ヒ', ('h','u'): 'フ', ('h','e'): 'ヘ', ('h','o'): 'ホ',
        ('m','a'): 'マ', ('m','i'): 'ミ', ('m','u'): 'ム', ('m','e'): 'メ', ('m','o'): 'モ',
        ('y','a'): 'ヤ', ('y','u'): 'ユ', ('y','o'): 'ヨ',
        ('r','a'): 'ラ', ('r','i'): 'リ', ('r','u'): 'ル', ('r','e'): 'レ', ('r','o'): 'ロ',
        ('w','a'): 'ワ', ('w','i'): 'ウィ', ('w','u'): 'ウ', ('w','e'): 'ウェ', ('w','o'): 'ウォ',

        # Sonoros
        ('g','a'): 'ガ', ('g','i'): 'ギ', ('g','u'): 'グ', ('g','e'): 'ゲ', ('g','o'): 'ゴ',
        ('z','a'): 'ザ', ('z','i'): 'ジ', ('z','u'): 'ズ', ('z','e'): 'ゼ', ('z','o'): 'ゾ',
        ('d','a'): 'ダ', ('d','i'): 'ジ', ('d','u'): 'ドゥ', ('d','e'): 'デ', ('d','o'): 'ド',
        ('b','a'): 'バ', ('b','i'): 'ビ', ('b','u'): 'ブ', ('b','e'): 'ベ', ('b','o'): 'ボ',
        ('p','a'): 'パ', ('p','i'): 'ピ', ('p','u'): 'プ', ('p','e'): 'ペ', ('p','o'): 'ポ',

        # Sons estrangeiros / Especiais
        ('f','a'): 'ファ', ('f','i'): 'フィ', ('f','u'): 'フ', ('f','e'): 'フェ', ('f','o'): 'フォ',
        ('v','a'): 'ヴァ', ('v','i'): 'ヴィ', ('v','u'): 'ヴ', ('v','e'): 'ヴェ', ('v','o'): 'ヴォ', 

        # Compostos
        ('sh','a'): 'シャ', ('sh','i'): 'シ', ('sh','u'): 'シュ', ('sh','e'): 'シェ', ('sh','o'): 'ショ',
        ('ch','a'): 'チャ', ('ch','i'): 'チ', ('ch','u'): 'チュ', ('ch','e'): 'チェ', ('ch','o'): 'チョ',
        ('j','a'): 'ジャ', ('j','i'): 'ジ', ('j','u'): 'ジュ', ('j','e'): 'ジェ', ('j','o'): 'ジョ',
        ('ny','a'): 'ニャ', ('ny','i'): 'ニ', ('ny','u'): 'ニュ', ('ny','e'): 'ニェ', ('ny','o'): 'ニョ',
        ('ry','a'): 'リャ', ('ry','i'): 'リ', ('ry','u'): 'リュ', ('ry','e'): 'リェ', ('ry','o'): 'リョ',
        ('ly','a'): 'リャ', ('ly','i'): 'リ', ('ly','u'): 'リュ', ('ly','e'): 'リェ', ('ly','o'): 'リョ',

        ('ts','u'): 'ツ',
    }

    C_DEFAULT = {
        'k': 'ク', 's': 'ス', 't': 'ト', 'n': 'ン', 'h': 'フ', 'm': 'ム', 'y': 'イ', 'r': '-',
        'w': 'ウ', 'g': 'グ', 'z': 'ズ', 'd': 'ド', 'b': 'ブ', 'p': 'プ', 'f': 'フ', 'v': 'ヴ', 
        'sh': 'シュ', 'ch': 'チ', 'j': 'ジ', 'ny': 'ニ', 'ry': 'リ', 'ly': 'リ', 'ts': 'ツ',
    }

    V_KANA = {'a': 'ア', 'i': 'イ', 'u': 'ウ', 'e': 'エ', 'o': 'オ', 'ö': 'オ', 'ë': 'エ'}

    def emit_cv(ck, v):
        """Emite katakana para consoante + vogal."""
        kana = CV.get((ck, v))
        if kana:
            result.append(kana)
        else:
            # Fallback: emite consoante padrão + vogal separada
            result.append(C_DEFAULT.get(ck, '') + V_KANA.get(v, ''))

    def process_consonant(ck, chars_consumed):
        """Processa uma consoante: verifica se uma vogal segue, emite kana."""
        nonlocal i
        pos = i + chars_consumed
        nv = at(pos)
        if is_v(nv):
            v = final_v(nv, pos)
            emit_cv(ck, v)
            i = pos + 1
        else:
            result.append(C_DEFAULT.get(ck, ''))
            i = pos

    # === Loop principal de escaneamento ===
    while i < n:
        c = at(i)
        c1 = at(i+1)
        c2 = at(i+2)

        # -- Dígrafos (verificar padrões mais longos primeiro) --

        if starts('nh'):
            process_consonant('ny', 2)
            continue
        if starts('lh'):
            process_consonant('ly', 2)
            continue
        if starts('ch'):
            process_consonant('sh', 2)
            continue
        if starts('rr'):
            process_consonant('h', 2)
            continue
        if starts('ss'):
            process_consonant('s', 2)
            continue

        # sc antes de e/i → サ行 (o dígrafo 'sc' funciona como /s/ único)
        if starts('sc') and at(i+2) in 'eië':
            process_consonant('s', 2)
            continue

        # xc antes de e/i → サ行 (o dígrafo 'xc' funciona como /s/)
        # Ex: excelente → エセレンチ, exceção → エセサン
        if starts('xc') and at(i+2) in 'eië':
            process_consonant('s', 2)
            continue

        # qu + e/i (u mudo)
        if starts('qu') and c2 in 'eië':
            v = final_v(c2, i+2)
            emit_cv('k', v)
            i += 3
            continue
        # qu + a/o (som de kw)
        if starts('qu') and is_v(c2):
            result.append('ク')
            v = final_v(c2, i+2)
            result.append(V_KANA.get(v, ''))
            i += 3
            continue

        # gu + e/i (u mudo)
        if starts('gu') and c2 in 'eië':
            v = final_v(c2, i+2)
            emit_cv('g', v)
            i += 3
            continue

        # -- Consoantes individuais --

        # h → ハ行 (japonês pronuncia o H, diferente do português onde é mudo)
        # Ex: humana → フマナ, hotel → ホテウ, hora → ホラ
        if c == 'h':
            process_consonant('h', 1)
            continue

        # x → depende do contexto (3 pronúncias diferentes!)
        if c == 'x':
            # 1) Após 'e' e antes de vogal → ザ行 (som de /z/)
            #    Ex: exame → エザミ, exemplo → エゼンプル
            if i > 0 and at(i-1) == 'e' and is_v(c1):
                process_consonant('z', 1)
            # 2) Antes de consoante ou no final → サ行 (som de /s/)
            #    Ex: expressivo → エスプレシブ, explicar → エスプリカル, extra → エストラ
            elif not is_v(c1):
                process_consonant('s', 1)
            # 3) Entre vogais ou após consoante → シャ행 (som de /ʃ/)
            #    Ex: caixa → カイシャ, abacaxi → アバカシ
            else:
                process_consonant('sh', 1)
            continue

        # j → ジャ行
        if c == 'j':
            process_consonant('j', 1)
            continue

        # v → ヴァ行 (Voicevox suporta o som de V nativamente, não precisa virar B)
        if c == 'v':
            process_consonant('v', 1)
            continue

        # r (depende do contexto)
        if c == 'r':
            if is_v(c1):
                # R forte (como H): início de palavra ou depois de n/l/s
                if i == 0 or at(i-1) in 'nls':
                    process_consonant('h', 1)
                else:
                    # R fraco (tap/flap): entre vogais ou dentro da palavra
                    process_consonant('r', 1)
            else:
                # R antes de consoante ou no final → ル
                result.append('ー')
                i += 1
            continue

        # l (depende do contexto)
        if c == 'l':
            if is_v(c1):
                # L antes de vogal → ラ行
                process_consonant('r', 1)
            else:
                # L antes de consoante ou no final → ウ (brasileiro)
                result.append('ウ')
                i += 1
            continue

        # s (depende do contexto)
        if c == 's':
            if i > 0 and is_v(at(i-1)) and is_v(c1):
                # S entre vogais → ザ行 (som de Z)
                process_consonant('z', 1)
            elif c1 in 'bdgjlmnrvz':
                # S antes de consoante sonora → ザ行 (som de Z)
                # Ex: mesmo → メズム, desde → デズジ, asma → アズマ
                process_consonant('z', 1)
            else:
                # S em outras posições → サ行
                process_consonant('s', 1)
            continue

        # g (depende do contexto)
        if c == 'g':
            if c1 in 'eië':
                # ge/gi → ジェ/ジ
                process_consonant('j', 1)
            else:
                process_consonant('g', 1)
            continue

        # c (depende do contexto)
        if c == 'c':
            if c1 in 'eië':
                # ce/ci → セ/シ
                process_consonant('s', 1)
            else:
                # ca/co/cu → カ/コ/ク
                process_consonant('k', 1)
            continue

        # n ou m (depende do contexto)
        if c in 'nm':
            if is_v(c1):
                process_consonant(c, 1)
            else:
                result.append('ン')
                i += 1
            continue

        if is_v(c):
            result.append(V_KANA[final_v(c, i)])
            i += 1
            continue

        if c in C_DEFAULT:
            process_consonant(c, 1)
            continue

        # Fallback para evitar loop infinito se houver caractere inesperado
        i += 1

    return ''.join(result)


# === Sistema Otimizado e Thread-safe para a Ayla ===
_synthesizer = None
_core_lock = threading.Lock()
_tts_lock = threading.Lock()
_loaded_vvm_files = set()

def get_synthesizer():
    """Retorna a instância global e única do Synthesizer (lazy-loaded)."""
    global _synthesizer
    if _synthesizer is None:
        with _core_lock:
            if _synthesizer is None:
                base_dir = Path(__file__).parent / "voicevox_core"
                onnx_dll = base_dir / "onnxruntime" / "lib" / "voicevox_onnxruntime.dll"
                dict_dir = base_dir / "dict" / "open_jtalk_dic_utf_8-1.11"
                c_api_lib = base_dir / "c_api" / "lib"

                # Adiciona pastas de DLLs no Windows
                import os
                if hasattr(os, "add_dll_directory"):
                    if onnx_dll.parent.exists():
                        os.add_dll_directory(str(onnx_dll.parent.resolve()))
                    if c_api_lib.exists():
                        os.add_dll_directory(str(c_api_lib.resolve()))

                onnxruntime = Onnxruntime.load_once(filename=str(onnx_dll.resolve()))
                open_jtalk = OpenJtalk(str(dict_dir.resolve()))
                _synthesizer = Synthesizer(onnxruntime, open_jtalk)
    return _synthesizer

_loaded_style_ids = set()

def load_model_for_style(synthesizer, style_id: int):
    """Encontra e carrega o arquivo .vvm que contém o style_id especificado."""
    if style_id in _loaded_style_ids:
        return

    models_dir = Path(__file__).parent / "voicevox_core" / "models" / "vvms"
    if not models_dir.exists():
        raise FileNotFoundError(f"Diretório de modelos não encontrado: {models_dir}")

    for file_path in models_dir.glob("*.vvm"):
        resolved_path = str(file_path.resolve())
        if resolved_path in _loaded_vvm_files:
            continue
        
        try:
            model = VoiceModelFile.open(resolved_path)
            style_ids = [s.id for m in model.metas for s in m.styles]
            if style_id in style_ids:
                synthesizer.load_voice_model(model)
                _loaded_vvm_files.add(resolved_path)
                for sid in style_ids:
                    _loaded_style_ids.add(sid)
                return
        except Exception:
            continue

    raise ValueError(f"Estilo com ID {style_id} não foi encontrado em nenhum modelo (.vvm)")

def gerar_audio_voicevox_bytes(texto: str, style_id: int) -> bytes | None:
    """
    Gera áudio WAV usando Voicevox a partir de texto em Português.
    Garante que a inicialização do Voicevox Core seja feita sob demanda (lazy)
    e com bloqueios para segurança de concorrência.
    Retorna os bytes do arquivo WAV gerado ou None se houver erro.
    """
    try:
        katakana_text = portuguese_to_katakana(texto)
        synthesizer = get_synthesizer()
        with _tts_lock:
            if style_id not in _loaded_style_ids:
                load_model_for_style(synthesizer, style_id)
            wav_bytes = synthesizer.tts(katakana_text, style_id)
            return wav_bytes
    except Exception as e:
        print(f"❌ Erro em gerar_audio_voicevox_bytes (style_id={style_id}): {e}", file=sys.stderr)
        return None



def main():
    if HAS_RICH:
        console = Console()
        console.print("[bold cyan]=== VOICEVOX: Conversor de Voz (Português para Katakana) ===[/bold cyan]\n")
    else:
        print("=== VOICEVOX: Conversor de Voz (Português para Katakana) ===\n")

    # Solicita o texto e o speaker_id
    try:
        while True:
            if HAS_RICH:
                text = Prompt.ask("\nDigite o texto em português (ou 'sair' para encerrar)")
            else:
                text = input("\nDigite o texto em português (ou 'sair' para encerrar): ")

            if text.lower().strip() == 'sair':
                break

            if not text.strip():
                continue

            # Escolha do Speaker ID
            if HAS_RICH:
                speaker_id = IntPrompt.ask("Digite o ID do Estilo/Voz (ex: 3 para Zundamon Sweet, 1 para Zundamon Normal)", default=3)
            else:
                speaker_id_str = input("Digite o ID do Estilo/Voz [default 3]: ")
                speaker_id = int(speaker_id_str) if speaker_id_str.strip() else 3

            # Traduz para Katakana
            katakana_text = portuguese_to_katakana(text)
            if HAS_RICH:
                console.print(f"[bold blue]Original:[/] {text}")
                console.print(f"[bold green]Katakana (Pronúncia):[/] {katakana_text}")
                status = Status("[yellow]Gerando áudio...[/yellow]")
                status.start()
            else:
                print(f"Original: {text}")
                print(f"Katakana (Pronúncia): {katakana_text}")
                print("Gerando áudio...")

            # Carrega o modelo se necessário e gera o áudio
            try:
                wav_bytes = gerar_audio_voicevox_bytes(text, speaker_id)

                if wav_bytes is None:
                    if HAS_RICH:
                        status.stop()
                    print("❌ Falha ao gerar áudio.")
                    continue

                if HAS_RICH:
                    status.stop()
                    console.print("[green]✔ Áudio gerado com sucesso![/green]")
                else:
                    print("✔ Áudio gerado com sucesso!")

                # Salva em arquivo
                output_path = Path(__file__).parent / "saida.wav"
                output_path.write_bytes(wav_bytes)
                if HAS_RICH:
                    console.print(f"[dim]Áudio salvo em: {output_path}[/dim]")
                else:
                    print(f"Áudio salvo em: {output_path}")

                # Tenta reproduzir se pygame estiver disponível
                if HAS_PLAYBACK:
                    if HAS_RICH:
                        console.print("[yellow]Reproduzindo áudio...[/yellow]")
                    else:
                        print("Reproduzindo áudio...")
                    
                    pygame.mixer.init()
                    pygame.mixer.music.load(io.BytesIO(wav_bytes))
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy():
                        time.sleep(0.1)
                    pygame.mixer.quit()
                else:
                    if HAS_RICH:
                        console.print("[yellow]Pygame não instalado. Não foi possível reproduzir o áudio automaticamente.[/yellow]")
                    else:
                        print("Pygame não instalado. Não foi possível reproduzir o áudio automaticamente.")

            except Exception as e:
                if HAS_RICH:
                    if 'status' in locals():
                        status.stop()
                    console.print(f"[red]❌ Erro ao gerar/reproduzir áudio: {e}[/red]")
                else:
                    print(f"❌ Erro ao gerar/reproduzir áudio: {e}")

    except KeyboardInterrupt:
        print("\nSaindo...")

if __name__ == "__main__":
    main()
