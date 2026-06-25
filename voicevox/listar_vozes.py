import sys
from pathlib import Path
from voicevox_core.blocking import VoiceModelFile
from rich.console import Console
from rich.table import Table

def get_all_metas():
    metas = []
    models_dir = Path(__file__).parent / "voicevox_core" / "models" / "vvms"
    if models_dir.exists():
        for file_path in models_dir.glob("*.vvm"):
            try:
                model = VoiceModelFile.open(str(file_path.resolve()))
                metas.extend(model.metas)
            except Exception:
                continue
    return metas


# Garante que a saída do terminal use UTF-8 para evitar erros de codificação
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

# Dicionário de tradução/transliteração para Inglês (Romaji/Tradução)
TRANSLATIONS = {
    # Nomes dos personagens
    '四国めたん': 'Shikoku Metan',
    'ずんだもん': 'Zundamon',
    '春日部つむぎ': 'Kasukabe Tsumugi',
    '雨晴はう': 'Amehare Hau',
    '波音リツ': 'Namine Ritsu',
    '玄野武宏': 'Kurono Takehiro',
    '白上虎太郎': 'Shirakami Kotaro',
    '青山龍星': 'Aoyama Ryusei',
    '冥鳴ひまり': 'Meimei Himari',
    '九州そら': 'Kyushu Sora',
    'もち子さん': 'Mochiko-san',
    '剣崎雌雄': 'Kenzaki Mesuo',
    'WhiteCUL': 'WhiteCUL',
    '後鬼': 'Goki',
    'No.7': 'No.7',
    'ちび式じい': 'Chibi Shiki Jii',
    '櫻歌ミコ': 'Ouka Miko',
    '小夜/SAYO': 'Sayo / SAYO',
    'ナースロボ＿タイプＴ': 'Nurse Robo_Type T',
    '†聖騎士 紅桜†': '†Holy Knight Benizakura†',
    '雀松朱司': 'Wakamatsu Akashi',
    '麒ヶ島宗麟': 'Kigashima Sorin',
    '春歌ナナ': 'Haruka Nana',
    '猫使アル': 'Nekotsuka Aru',
    '猫使ビィ': 'Nekotsuka Bee',
    '中国うさぎ': 'Chugoku Usagi',
    '栗田まろん': 'Kurita Maron',
    'あいえるたん': 'Ierutan',
    '満別花丸': 'Mambetsu Hanamaru',
    '琴詠ニア': 'Kotoyomi Nia',
    
    # Estilos / Tons
    'ノーマル': 'Normal',
    'あまあま': 'Sweet',
    'ツンツン': 'Tsuntsun',
    'セクシー': 'Sexy',
    'ささやき': 'Whisper',
    'ヒソヒソ': 'Whisper/Mumble',
    'クイーン': 'Queen',
    '喜び': 'Joy',
    'ツンギレ': 'Tsungire',
    '悲しみ': 'Sadness',
    'ふつう': 'Normal (Futsuu)',
    'わーい': 'Yay',
    'びくびく': 'Timid',
    'おこ': 'Angry',
    'びえーん': 'Cry',
    'セクシー／あん子': 'Sexy / Anko',
    '人間ver.': 'Human ver.',
    'ぬいぐるみver.': 'Plushie ver.',
    'アナウンス': 'Announcement',
    '読み聞かせ': 'Storytelling',
    '第二形態': 'Second Form',
    'ロリ': 'Loli',
    '楽々': 'Easygoing',
    '恐怖': 'Fear',
    '内緒話': 'Secret/Whisper',
    'おちつき': 'Calm',
    'うきうき': 'Excited',
    '人見知り': 'Shy',
    'おどろき': 'Surprised',
    'こわがり': 'Scared',
    'へろへろ': 'Exhausted',
    '元気': 'Energetic',
    'ぶりっ子': 'Burikko (Fake cute)',
    'ボーイ': 'Boy',
}

def translate(text):
    return TRANSLATIONS.get(text, text)

def main():
    console = Console()
    
    console.print("\n[bold cyan]=== VOICEVOX: Lista de Vozes (Com Tradução para Inglês) ===[/bold cyan]\n")
    console.print("[yellow]Nota:[/] Todas as vozes nativas do VOICEVOX são otimizadas para o idioma [bold green]Japonês (ja-JP)[/bold green].\n")
    
    table = Table(title="Vozes Disponíveis (Speakers)", header_style="bold magenta")
    table.add_column("ID do Estilo", justify="center", style="cyan", no_wrap=True)
    table.add_column("Personagem (PT/EN)", style="green")
    table.add_column("Nome Original (JP)", style="dim green")
    table.add_column("Estilo / Tom (PT/EN)", style="yellow")
    table.add_column("Estilo Original (JP)", style="dim yellow")
    table.add_column("Idioma", style="blue")

    metas = get_all_metas()
    for speaker in metas:
        for style in speaker.styles:
            table.add_row(
                str(style.id),
                translate(speaker.name),
                speaker.name,
                translate(style.name),
                style.name,
                "Japonês (ja-JP)"
            )
            
    console.print(table)
    console.print(f"\n[bold green]Total de estilos/vozes disponíveis: {sum(len(s.styles) for s in metas)}[/bold green]\n")

if __name__ == "__main__":
    main()
