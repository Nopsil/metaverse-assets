"""Hard safety screen for the Qwen Image 2.1 anime-style catalog.

Drop a row on series, character, school, or a stated age under 21. A cute
face or stylized proportions is not, by itself, a minor. A child-coded
character stays out even when the drawing looks adult. Callers still owe a
full-size look: metadata cannot see the picture.
"""

from __future__ import annotations

import re
from typing import Iterable

# Stated ages under 21 are out. Unstated age is not proof of adulthood;
# callers must visually review. "childhood" does not match \bchild\b.
_AGE_RE = re.compile(
    r"(?i)(?:\b(?:age|aged)\s*)?(\d{1,2})\s*(?:yo|y\.?\s*o\.?|yrs?|years?\s*old)|"
    r"(?<![\d])(\d{1,2})\s*歳"
)

# Whole-token English. Japanese phrases are matched on the normalized string.
_EN_PATTERNS = [
    r"\blolis?\b",
    r"\blolitas?\b",
    r"\blolicons?\b",
    r"\bshotas?\b",
    r"\bshotacons?\b",
    r"\bchildren\b",
    r"\bchild\b",
    r"\bkids?\b",
    r"\btoddlers?\b",
    r"\binfants?\b",
    r"\bbabies\b",
    r"\bbaby\b",
    r"\bunder-?aged?\b",
    r"\bpre-?teens?\b",
    r"\bteens?\b",
    r"\bteenagers?\b",
    r"\bteenage\b",
    r"\bjailbait\b",
    r"\bprepubescent\b",
    r"\bpubescent\b",
    r"\bchild-?like\b",
    r"\bbabyface\b",
    r"\bbaby\s+face\b",
    r"\byoung\s+girls?\b",
    r"\byoung\s+boys?\b",
    r"\blittle\s+girls?\b",
    r"\blittle\s+boys?\b",
    r"\bsmall\s+girls?\b",
    r"\bsmall\s+boys?\b",
    r"\bschool-?\s*girls?\b",
    r"\bschool-?\s*boys?\b",
    r"\bhigh\s*schools?\b",
    r"\bmiddle\s*schools?\b",
    r"\belementary\s+schools?\b",
    r"\bgrade\s+schools?\b",
    r"\bkindergartens?\b",
    r"\bserafuku\b",
    r"\bsailor\s+uniform\b",
    r"\bschool\s+uniforms?\b",
    r"\bage-?\s*play\b",
    r"\bdiapers?\b",
    r"\bchibis?\b",
    r"\bsuper\s+deformed\b",
    r"\bmy\s+little\s+pony\b",
    r"\bpony\s+diffusion\b",
    r"\bfurry\b",
    r"\banthro\b",
    r"\bphotoreal(?:istic)?\b",
    r"\bphotographs?\b",
    r"\braw\s+photos?\b",
    r"\bdslr\b",
    r"\bhyper-?realistic\b",
    r"\bultra\s+realistic\b",
    r"\b\d+\s*mm\s+lens\b",
    r"\b3d\s*(?:style|render|renders|cg)\b",
    r"\bguros?\b",
    r"\bmesugaki\b",
    r"\bnagatoro\b",
    r"\bsatellizer\b",
    r"\bburuma\b",
    r"\bgym\s+uniform\b",
    r"\bgym\s+shirt\b",
    r"\bump9\b",
    r"\bump45\b",
]

_EN_RES = [re.compile(p, re.I) for p in _EN_PATTERNS]

# Matched as substrings after underscore/space normalization.
_JA_AND_SERIES = [
    "合法ロリ",
    "ロリババア",
    "ロリ",
    "ロリータ",
    "ショタ",
    "幼女",
    "幼男",
    "子供",
    "子ども",
    "こども",
    "小学生",
    "中学生",
    "高校生",
    "女子高生",
    "女子中学生",
    "男子中学生",
    "男子高校生",
    "未成年",
    "児童",
    "園児",
    # つるぺた marks an undeveloped child-coded body. Adult petite/flat
    # words (貧乳, スレンダー, 細身, 華奢) are not in this list.
    "つるぺた",
    "幼児",
    "赤ちゃん",
    "乳児",
    "バブみ",
    "おむつ",
    "ちび",
    "デフォルメ",
    "学生服",
    "セーラー服",
    "制服",
    "スク水",
    "スクール水着",
    "学校の水着",
    "体操着",
    "体操服",
    "生徒",
    "初音ミク",
    "鏡音リン",
    "鏡音レン",
    "ボーカロイド",
    "木之本桜",
    "綾波レイ",
    "惣流アスカ",
    "アスカ・ラングレー",
    "鹿目まどか",
    "アーニャ",
    "クレー",
    "ナヒーダ",
    "パイモン",
    "早柚",
    "ヨォーヨ",
    "チルノ",
    "フランドール",
    "伊吹萃香",
    "ルーミア",
    "クラーラ",
    "ブルーアーカイブ",
    "ブルアカ",
    "プリキュア",
    "僕のヒーローアカデミア",
    "ヒロアカ",
    "呪術廻戦",
    "ラブライブ",
    "けいおん",
    "ご注文はうさぎ",
    "ごちうさ",
    "鬼滅の刃",
    "ハイキュー",
    "フリーレン",
    "学園アイドルマスター",
    "プロジェクトセカイ",
    "プロセカ",
    "東方project",
    "東方",
    "名探偵コナン",
    "世良真純",
    "からかい上手の高木さん",
    "高木さん",
    "全裸登校",
    "授業参観",
    "登校",
    "母娘",
    "エヴァンゲリオン",
    "ケモノ",
    "エログロ",
    "美少年",
    "男の子",
    "q版",
    "長瀞",
    "ブルマ",
    "っ子",
    "ヴァイオレット",
    "アーミヤ",
    "遠坂凛",
    "ウマ娘",
    "けものフレンズ",
    "メダリスト",
    "暁山瑞希",
    "チェンソーマン",
    "この素晴らしい",
    "めぐみん",
    "五等分の花嫁",
    "どうぶつの森",
    "ドキドキ文芸部",
]

_SERIES_EN = [
    "hatsune miku",
    "kagamine rin",
    "kagamine len",
    "kinomoto sakura",
    "cardcaptor sakura",
    "ayanami rei",
    "asuka langley",
    "souryuu asuka",
    "kaname madoka",
    "madoka magica",
    "anya forger",
    "blue archive",
    "bluearchive",
    "pretty cure",
    "precure",
    "my hero academia",
    "boku no hero",
    "jujutsu kaisen",
    "love live",
    "kimetsu no yaiba",
    "demon slayer",
    "gakuen idolmaster",
    "project sekai",
    "vocaloid",
    "touhou",
    "evangelion",
    "klee (genshin",
    "qiqi (genshin",
    "diona (genshin",
    "sayu (genshin",
    "yaoyao (genshin",
    "nahida",
    "paimon",
    "frieren",
    "clara (honkai",
    "clara (star rail",
    "hook (honkai",
    "violet evergarden",
    "tohsaka rin",
    "umamusume",
    "akiyama mizuki",
    "kemono friends",
    "amiya (arknights",
    "suomi (girls",
    "chainsaw man",
    "konosuba",
    "kono subarashii",
    "megumin",
    "go-toubun",
    "gotoubun",
    "quintessential quintuplets",
    "animal crossing",
    "ankha (animal",
    "doki doki",
    "monika (doki",
    "shantae",
]

# Exact tags that are ambiguous or minor-coded on their own.
_EXACT_TAGS = {
    "jk",
    "js",
    "jc",
    "loli",
    "shota",
    "child",
    "children",
    "kid",
    "kids",
    "teen",
    "teenage",
    "teenager",
    "boy",
    "少年",
    "美少年",
    "男の子",
    "幼女",
    "少女",  # ambiguous age label; 女の子 alone is kept for visual review
    "chibi",
    "ちび",
    "guro",
    "グロ",
}

_PERSON_EN = re.compile(
    r"\b(?:women|woman|females?|lad(?:y|ies)|girls?|men|man|1girls?|2girls|1man)\b"
)
_PERSON_JA = (
    "女の子",
    "女性",
    "お姉さん",
    "美人",
    "美女",
    "ギャル",
    "男性",
    "成人",
    "騎士",
    "魔女",
    "人妻",
    "熟女",
)

_PHOTO_RE = re.compile(
    r"(?i)\b(?:photoreal(?:istic)?|photographs?|raw\s+photos?|dslr|hyper-?realistic)\b"
)


def normalize(text: str) -> str:
    t = text.replace("\\", " ")
    t = t.replace("_", " ").replace("　", " ").replace("\n", " ")
    t = t.replace("（", " ").replace("）", " ").replace("(", " ").replace(")", " ")
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def _age_hit(norm: str) -> str | None:
    for m in _AGE_RE.finditer(norm):
        raw = m.group(1) or m.group(2)
        age = int(raw)
        if 1 <= age < 21:
            return f"stated_age_{age}"
    return None


def _exact_tag_hit(tags: Iterable[str]) -> str | None:
    for tag in tags:
        token = normalize(tag)
        if token in _EXACT_TAGS:
            return f"tag:{token}"
    return None


def screen(
    text: str,
    tags: Iterable[str] | None = None,
    *,
    minor_flag: bool | None = None,
    poi_flag: bool | None = None,
    lo_flag: bool | None = None,
) -> tuple[bool, str]:
    """Return (keep, reason). keep is False when the row must be excluded."""
    if minor_flag is True:
        return False, "minor_flag"
    if poi_flag is True:
        return False, "poi_flag"
    if lo_flag is True:
        return False, "pixiv_lo_flag"

    tag_list = list(tags or [])
    exact = _exact_tag_hit(tag_list)
    if exact:
        return False, exact

    norm = normalize(" ".join([text or "", *map(str, tag_list)]))
    if not norm:
        return False, "empty_text"

    age = _age_hit(norm)
    if age:
        return False, age

    for cre in _EN_RES:
        m = cre.search(norm)
        if m:
            return False, f"term:{m.group(0)}"

    for phrase in _JA_AND_SERIES:
        if phrase.lower() in norm:
            return False, f"term:{phrase}"

    for phrase in _SERIES_EN:
        if normalize(phrase) in norm:
            return False, f"series:{phrase}"

    # 少女 as its own word. Do not treat 美少女 / 少女漫画 as an automatic drop;
    # those still require visual review because the words are used for adults.
    if re.search(r"(?<!美)少女(?!漫画)", norm):
        return False, "term:少女"
    if re.search(r"(?<!サンデー)少年", norm):
        return False, "term:少年"

    # Token JK/JS/JC surrounded by spaces or commas.
    if re.search(r"(?:^|[\s,])(?:jk|js|jc)(?:$|[\s,])", norm):
        return False, "term:jk/js/jc"

    # Catches lolicon, lolita, loliconder, and tag-prefix loli without
    # matching unrelated words.
    if re.search(r"\bloli", norm):
        return False, "term:loli"

    return True, "pass"


def has_person_signal(text: str, tags: Iterable[str] | None = None) -> bool:
    norm = normalize(f"{text} {' '.join(tags or [])}")
    if _PERSON_EN.search(norm):
        return True
    return any(sig in norm for sig in _PERSON_JA)


def is_photoreal(text: str) -> bool:
    return bool(_PHOTO_RE.search(normalize(text)))


def rating_for(nsfw_level, text: str) -> str:
    """Map source rating metadata to all-ages | adult.

    PG / PG-13 stay all-ages unless the prompt is sexually explicit.
    R and above are adult. Suggestive words like "sexy" do not upgrade PG.
    """
    explicit = re.search(
        r"(?i)\b(?:nude|nudes|naked|nipples?|penis|pussy|vagina|vaginal|"
        r"fellatio|paizuri|creampie|cum|sex|intercourse|nsfw)\b|"
        r"裸|ヌード|乳首|性交|セックス|フェラ|中出し",
        normalize(text),
    )
    level = nsfw_level
    if isinstance(level, str):
        key = level.strip().lower()
        if key in {"r", "x", "xxx", "mature", "explicit"} or key.isdigit() and int(key) >= 4:
            return "adult"
        if key in {"none", "pg", "soft", "pg13", "pg-13", "safe", ""}:
            return "adult" if explicit else "all-ages"
    if isinstance(level, (int, float)):
        if int(level) >= 4:
            return "adult"
        return "adult" if explicit else "all-ages"
    return "adult" if explicit else "all-ages"


_STYLE_CUES = [
    ("セル塗り", "cel-shaded color"),
    ("アニメ塗り", "anime cel paint"),
    ("厚塗り", "thick painterly anime"),
    ("線画", "clean lineart"),
    ("cel shading", "cel shading"),
    ("cel-shaded", "cel shading"),
    ("flat color", "flat color"),
    ("lineart", "lineart"),
    ("watercolor", "watercolor"),
    ("pastel", "pastel palette"),
    ("vibrant", "vibrant palette"),
    ("和服", "wafuku"),
    ("着物", "kimono"),
    ("浴衣", "yukata"),
    ("メイド", "maid costume"),
    ("鎧", "armor"),
    ("騎士", "knight"),
    ("ファンタジー", "fantasy costume"),
    ("fantasy", "fantasy"),
    ("ミリタリー", "military costume"),
    ("military", "military costume"),
    ("水着", "swimsuit"),
    ("bikini", "bikini"),
    ("ドレス", "dress"),
    ("portrait", "portrait"),
    ("upper body", "half-body"),
    ("cowboy shot", "three-quarter"),
    ("full body", "full body"),
    ("全身", "full body"),
    ("笑顔", "smile"),
    ("smile", "smile"),
    ("looking at viewer", "direct gaze"),
    ("横顔", "profile"),
    ("猫耳", "cat ears"),
    ("nekomimi", "cat ears"),
    ("巨乳", "adult figure"),
    ("長身", "tall adult figure"),
    ("貧乳", "petite adult"),
    ("微乳", "petite adult"),
    ("ちっぱい", "petite adult"),
    ("無乳", "petite adult"),
    ("小柄", "petite adult"),
    ("低身長", "petite adult"),
    ("スレンダー", "slim adult"),
    ("細身", "slim adult"),
    ("華奢", "petite adult"),
    ("slender", "slim adult"),
    ("petite", "petite adult"),
]


def style_notes(text: str, *, base_model: str = "", rating: str = "") -> str:
    norm = normalize(text)
    cues: list[str] = ["2D anime illustration"]
    if "オリジナル" in norm or "original" in norm:
        cues.append("original character")
    for needle, label in _STYLE_CUES:
        if needle.lower() in norm and label not in cues:
            cues.append(label)
    if base_model:
        label = f"base {base_model}"
        if label not in cues:
            cues.append(label)
    if rating == "adult":
        cues.append("adult-rated source")
    elif rating == "all-ages":
        cues.append("all-ages source")
    return "; ".join(cues[:8])
