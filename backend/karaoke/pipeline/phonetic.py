"""Stage: the phonetic lyrics (docs/ARCHITECTURE.md, phase 6, "Letra fonética").

Lyrics in a script outside the Latin alphabet (Japanese, Chinese, Korean, Cyrillic, Greek, Devanagari, Thai and
others; not Arabic nor Hebrew, which leave the vowels out) get a second version, written for someone who reads
Portuguese, timed word by word with the original. It comes from:

1. the fans' romanization on LRCLIB, a Latin version of the same song, taken when it agrees with the original's
   reading (so a translation or another song stays out): the whole text pairs with the original's in order, letter
   by letter, cut at the original's lines and then at its words, and each word keeps the time of the original's
   characters it reads;
2. without it, the app's own reading, only for the scripts it reads reliably (AUTO: Korean, Chinese, Cyrillic and
   Greek, from 0.16.4), marked "auto" on the TV. From 0.17.0 it is only prepared ("pendente"): the queue asks the
   entry's owner and the host whether to use it (core/songs.py, answer_phonetic), and the TV shows the original
   until someone says yes;
3. the host's (core/songs.py, replace_phonetic), who corrects either or, when there is none, writes one.

Japanese, Thai, Devanagari and the rest never show a reading of the app's: fugashi with unidic-lite (Japanese, whose
kanji are read in more than one way), the rules here (Devanagari) and anyascii (the rest) only pair each romanized
word with the original's characters and measure the agreement. Without a romanization the song says so
(phonetic_source "nenhuma").

The spelling for Portuguese comes on top of the romanization (shi → xi, chi → tchi, ji → dji, …): an aid to sing,
not an exact transcription. The stage never fails the song: whatever goes wrong, the song plays with its original.
"""
from __future__ import annotations

import difflib
import itertools
import logging
import re
import unicodedata

from karaoke.core.storage import read_json, write_json
from karaoke.pipeline.lyrics import clean_name, names_of

log = logging.getLogger("karaoke.pipeline")

AGREEMENT = 0.8  # the fans' romanization is taken when it agrees this much with the original's reading
COVERAGE = 0.8  # and covers this share of the sung lines
MIXED = 0.1  # lyrics get a phonetic version when this share of their letters is outside the Latin alphabet
# Scripts the app reads well enough to show its own reading when the fans wrote none: the sound is in the letters
# (Hangul, Cyrillic, Greek) or in pypinyin's dictionary of words (Chinese). Not Japanese: a kanji has several readings,
# and a song often uses the rarer one (瞬間 sung toki, not shunkan).
AUTO = ("ko", "zh", "cyrillic", "greek")
PAUSE_S = 1.0  # a phonetic word read over a pause this long in the original's singing is cut at the pause

# --- which script ---------------------------------------------------------------------------------------------------

RANGES = {
    "kana": ((0x3040, 0x30FF), (0x31F0, 0x31FF)),
    "han": ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF)),
    "hangul": ((0x1100, 0x11FF), (0x3130, 0x318F), (0xAC00, 0xD7AF)),
    "cyrillic": ((0x0400, 0x052F),),
    "greek": ((0x0370, 0x03FF), (0x1F00, 0x1FFF)),
    "arabic": ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)),
    "hebrew": ((0x0590, 0x05FF),),
    "devanagari": ((0x0900, 0x097F),),
    "thai": ((0x0E00, 0x0E7F),),
}


def kind_of(char: str) -> str | None:
    """The script of one letter: "latin", one of RANGES, "other" for any other letter, None for the rest."""
    code = ord(char)
    for name, ranges in RANGES.items():
        if any(a <= code <= b for a, b in ranges):
            return name
    if char.isalpha():
        return "latin" if code < 0x0250 or 0x1E00 <= code <= 0x1EFF else "other"
    return None


def script_of(text: str, language: str | None = None) -> str | None:
    """The script the lyrics need a phonetic version for: "ja", "zh", "ko", "cyrillic", "greek", "devanagari",
    "thai" or "other"; None when less than MIXED of the letters are outside the Latin alphabet (a song in English
    with a Korean chorus, as APT., gets one), or the script is Arabic or Hebrew."""
    counts: dict[str, int] = {}
    for char in text:
        kind = kind_of(char)
        if kind:
            counts[kind] = counts.get(kind, 0) + 1
    total = sum(counts.values())
    if not total or total - counts.get("latin", 0) < MIXED * total:
        return None
    main = max((k for k in counts if k != "latin"), key=lambda k: counts[k])
    if main in ("kana", "han"):
        # kana only in Japanese; kanji alone are Chinese, unless the language says Japanese
        return "ja" if counts.get("kana") or language == "ja" else "zh"
    if main in ("arabic", "hebrew"):
        return None
    return {"hangul": "ko", "han": "zh"}.get(main, main)


# --- the readings ---------------------------------------------------------------------------------------------------
# A line becomes words: {"text": its characters, "a": start, "b": end (offsets in the line), "roman": the reading in
# Latin letters, "latin": already Latin (a word sung as written, kept as is)}.

LATIN_WORD = re.compile(r"[A-Za-zÀ-ÿ0-9'\u2019]+")


def latin_words(text: str, offset: int = 0) -> list[dict]:
    return [{"text": m[0], "a": offset + m.start(), "b": offset + m.end(), "roman": m[0].lower(), "latin": True}
            for m in LATIN_WORD.finditer(text)]


# Japanese ------------------------------------------------------------------------------------------------------------

KANA = {
    "あ": "a", "い": "i", "う": "u", "え": "e", "お": "o",
    "か": "ka", "き": "ki", "く": "ku", "け": "ke", "こ": "ko",
    "が": "ga", "ぎ": "gi", "ぐ": "gu", "げ": "ge", "ご": "go",
    "さ": "sa", "し": "shi", "す": "su", "せ": "se", "そ": "so",
    "ざ": "za", "じ": "ji", "ず": "zu", "ぜ": "ze", "ぞ": "zo",
    "た": "ta", "ち": "chi", "つ": "tsu", "て": "te", "と": "to",
    "だ": "da", "ぢ": "ji", "づ": "zu", "で": "de", "ど": "do",
    "な": "na", "に": "ni", "ぬ": "nu", "ね": "ne", "の": "no",
    "は": "ha", "ひ": "hi", "ふ": "fu", "へ": "he", "ほ": "ho",
    "ば": "ba", "び": "bi", "ぶ": "bu", "べ": "be", "ぼ": "bo",
    "ぱ": "pa", "ぴ": "pi", "ぷ": "pu", "ぺ": "pe", "ぽ": "po",
    "ま": "ma", "み": "mi", "む": "mu", "め": "me",
    "も": "mo", "や": "ya", "ゆ": "yu", "よ": "yo",
    "ら": "ra", "り": "ri", "る": "ru", "れ": "re", "ろ": "ro",
    "わ": "wa", "ゐ": "i", "ゑ": "e", "を": "o", "ん": "n",
    "ぁ": "a", "ぃ": "i", "ぅ": "u",
    "ぇ": "e", "ぉ": "o", "ゔ": "vu", "ゎ": "wa",
}
SMALL_Y = {"ゃ": "a", "ゅ": "u", "ょ": "o"}
SMALL_VOWEL = {"ぁ": "a", "ぃ": "i", "ぅ": "u", "ぇ": "e", "ぉ": "o"}


def hiragana(text: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text)


def kana_romaji(kana: str) -> str:
    """Kana in Hepburn: っ doubles the next consonant, ー repeats the vowel, きゃ is kya, ティ is ti."""
    kana = hiragana(kana)
    out: list[str] = []
    i = 0
    while i < len(kana):
        c, nxt = kana[i], kana[i + 1] if i + 1 < len(kana) else ""
        if c == "っ":
            following = kana_romaji(kana[i + 1:i + 3]) if nxt else ""
            out.append("t" if following.startswith("ch") else following[:1] if following[:1].isalpha() else "")
            i += 1
        elif c == "ー":
            last = next((ch for ch in reversed("".join(out)) if ch in "aeiou"), "")
            out.append(last)
            i += 1
        elif nxt in SMALL_Y and c in KANA and c not in SMALL_VOWEL:
            base = KANA[c]
            out.append((base[:-1] if base in ("shi", "chi", "ji") else base[:-1] + "y") + SMALL_Y[nxt])
            i += 2
        elif nxt in SMALL_VOWEL and c in KANA and c not in SMALL_VOWEL:
            out.append(KANA[c][:-1] + SMALL_VOWEL[nxt])  # loanword sounds: ティ ti, ファ fa
            i += 2
        else:
            out.append(KANA.get(c, c if c.isascii() else ""))
            i += 1
    return "".join(out)


_tagger = None


def tagger():
    global _tagger
    if _tagger is None:
        import fugashi

        _tagger = fugashi.Tagger()
    return _tagger


PUNCTUATION = re.compile(r"[\s\W_]+")


def _kana_of(node) -> str:
    f = node.feature
    if f.pos1 == "助詞" and getattr(f, "pron", None) not in (None, "*"):
        return f.pron  # a particle as it is said: は wa, へ e
    kana = getattr(f, "kana", None)
    return kana if kana not in (None, "*") else node.surface


INFLECTED = ("動詞", "形容詞", "助動詞")  # verbs, adjectives and the endings already on them


def _glues(node, head: str) -> bool:
    """Endings that a reader keeps with the word before (`head`, that word's part of speech): a suffix always; an
    auxiliary verb, the て or ば of a verb and a helping verb (いる of 待っている) only after a verb or adjective, so
    です stays apart from a noun and 行く from a particle."""
    f = node.feature
    if f.pos1 == "接尾辞":
        return True
    ending = f.pos1 == "助動詞" or (f.pos1 == "助詞" and f.pos2 == "接続助詞") or (
        f.pos1 == "動詞" and f.pos2 == "非自立可能")
    return ending and head in INFLECTED


def japanese_words(text: str) -> list[dict]:
    """The line's words, grouped as a reader groups them, with the dictionary's reading (only to pair them with a
    romanization)."""
    words: list[dict] = []
    cursor = 0
    for node in tagger()(text):
        surface = node.surface
        a = text.find(surface, cursor)
        if a < 0:
            continue
        b = cursor = a + len(surface)
        if not PUNCTUATION.sub("", surface):
            continue
        if not any(kind_of(c) in ("kana", "han") for c in surface):
            words.extend(latin_words(surface, a))
            continue
        kana = _kana_of(node)
        if words and not words[-1]["latin"] and words[-1]["b"] == a and _glues(node, words[-1]["head"]):
            words[-1].update(text=words[-1]["text"] + surface, b=b, kana=words[-1]["kana"] + kana)
            if node.feature.pos1 in INFLECTED:
                words[-1]["head"] = node.feature.pos1
        else:
            words.append({"text": surface, "a": a, "b": b, "kana": kana, "latin": False,
                          "particle_o": surface == "を", "head": node.feature.pos1})
    for i, word in enumerate(words):
        if word["latin"]:
            continue
        kana = word.pop("kana")
        word.pop("head", None)
        tail = ""
        if hiragana(kana).endswith("っ") and i + 1 < len(words):
            nxt = words[i + 1]
            following = nxt["roman"] if "roman" in nxt else kana_romaji(nxt.get("kana", ""))
            tail = "t" if following.startswith("ch") else following[:1]
            kana = kana[:-1]
        word["roman"] = kana_romaji(kana) + tail
    return words


# Chinese -------------------------------------------------------------------------------------------------------------

def chinese_words(text: str) -> list[dict]:
    """Each Han character is a word, read with pypinyin (in context: 银行 yinhang, 很行 xing); the rest as written."""
    from pypinyin import lazy_pinyin

    words: list[dict] = []
    for run in re.finditer(r"[㐀-䶿一-鿿豈-﫿]+|[^㐀-䶿一-鿿豈-﫿]+", text):
        if kind_of(run[0][0]) == "han":
            for k, reading in enumerate(lazy_pinyin(run[0], v_to_u=True)):
                a = run.start() + k
                words.append({"text": text[a], "a": a, "b": a + 1, "roman": reading, "latin": False})
        else:
            words.extend(latin_words(run[0], run.start()))
    return words


# Korean: Revised Romanization with the main sound changes (liaison, ㄹ as r or l, nasalization) -------------------

KO_INITIAL = ["g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h"]
KO_VOWEL = ["a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi",
            "yu", "eu", "ui", "i"]
KO_FINAL = ["", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l", "m", "p", "p", "t", "t",
            "ng", "t", "t", "k", "t", "p", "t"]
# The final consonant that moves to an empty initial (ㅇ) of the next syllable, by final index
KO_LIAISON = {1: "g", 2: "kk", 4: "n", 7: "d", 8: "r", 16: "m", 17: "b", 19: "s", 20: "ss", 22: "j", 23: "ch",
              24: "k", 25: "t", 26: "p"}
# A double final before an empty initial keeps its first sound and moves the second (없이 eopsi, 읽어 ilgeo); with ㅎ,
# the ㅎ goes silent (싫어 sireo, 않아 ana, 좋아 joa)
KO_SPLIT = {3: ("k", "s"), 5: ("n", "j"), 6: ("", "n"), 9: ("l", "g"), 10: ("l", "m"), 11: ("l", "b"), 12: ("l", "s"),
            13: ("l", "t"), 14: ("l", "p"), 15: ("", "r"), 18: ("p", "s"), 27: ("", "")}
# ㅎ, alone or in a double final, before ㄱ ㄷ ㅈ makes them aspirated (좋다 jota, 않고 anko)
KO_H_FINAL = {27: "", 6: "n", 15: "l"}
KO_ASPIRATED = {0: "k", 3: "t", 12: "ch"}


def korean_roman(word: str) -> str:
    syllables = []
    for char in word:
        code = ord(char) - 0xAC00
        if 0 <= code < 11172:
            syllables.append((code // 588, (code % 588) // 28, code % 28))
        else:
            syllables.append(char)
    out = []
    for i, syllable in enumerate(syllables):
        if isinstance(syllable, str):
            out.append(syllable.lower() if syllable.isascii() else "")
            continue
        initial, vowel, final = syllable
        prev = syllables[i - 1] if i and not isinstance(syllables[i - 1], str) else None
        nxt = syllables[i + 1] if i + 1 < len(syllables) and not isinstance(syllables[i + 1], str) else None
        head = KO_INITIAL[initial]
        if prev and prev[2] and initial == 11:  # the previous final moved here
            head = KO_SPLIT[prev[2]][1] if prev[2] in KO_SPLIT else KO_LIAISON.get(prev[2], "")
        elif prev and prev[2] in KO_H_FINAL and initial in KO_ASPIRATED:
            head = KO_ASPIRATED[initial]
        elif prev and initial == 18 and KO_FINAL[prev[2]] in ("k", "t", "p"):
            head = ""  # ㄱ ㄷ ㅂ before ㅎ: aspirated, the same letter (정숙해 jeongsukae)
        elif initial == 5 and prev and prev[2] == 8:
            head = "l"  # ㄹㄹ is ll
        elif initial == 5 and prev and prev[2] and prev[2] != 8:
            head = "n"  # ㄹ after another final is said n
        tail = KO_FINAL[final]
        if final and nxt and nxt[0] == 11 and final in KO_LIAISON:
            tail = ""
        elif final and nxt and nxt[0] == 11 and final in KO_SPLIT:
            tail = KO_SPLIT[final][0]
        elif final in KO_H_FINAL and nxt and nxt[0] in KO_ASPIRATED:
            tail = KO_H_FINAL[final]
        elif final == 27:
            tail = ""  # ㅎ at the end of a word is not heard
        elif final and nxt and nxt[0] in (2, 6):  # nasalization before ㄴ and ㅁ
            tail = {"k": "ng", "t": "n", "p": "m"}.get(tail, tail)
        out.append(head + KO_VOWEL[vowel] + tail)
    return "".join(out)


# Devanagari: the inherent a, dropped at the end of a word -----------------------------------------------------------

DEVA_CONSONANT = dict(zip("कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह",
                          ["k", "kh", "g", "gh", "n", "tch", "tchh", "dj", "djh", "nh", "t", "th", "d", "dh", "n",
                           "t", "th", "d", "dh", "n", "p", "f", "b", "bh", "m", "i", "r", "l", "v", "x", "x", "s",
                           "h"], strict=True))
DEVA_VOWEL = dict(zip("अआइईउऊऋएऐओऔ", ["a", "aa", "i", "ii", "u", "uu", "ri", "e", "ai", "o", "au"], strict=True))
DEVA_SIGN = dict(zip("ािीुूृेैोौ", ["aa", "i", "ii", "u", "uu", "ri", "e", "ai", "o", "au"], strict=True))


def devanagari_roman(word: str) -> str:
    out, i = [], 0
    while i < len(word):
        c = word[i]
        nxt = word[i + 1] if i + 1 < len(word) else ""
        if c in DEVA_CONSONANT:
            out.append(DEVA_CONSONANT[c])
            if nxt in DEVA_SIGN:
                out.append(DEVA_SIGN[nxt])
                i += 1
            elif nxt == "्":
                i += 1
            elif i + 1 < len(word) and (nxt in DEVA_CONSONANT or nxt in "ंँः"):
                out.append("a")
        elif c in DEVA_VOWEL:
            out.append(DEVA_VOWEL[c])
        elif c in "ंँ":
            out.append("n")
        elif c.isascii():
            out.append(c.lower())
        i += 1
    return "".join(out)


RU_VOWEL_BEFORE = re.compile(r"(^|[аеёиоуыэюяъьАЕЁИОУЫЭЮЯЪЬ])([еЕ])")


def cyrillic_roman(word: str, language: str | None = None) -> str:
    """Cyrillic as anyascii writes it; in Russian (and Belarusian), ё is said yo, and е at the start of a word or after
    a vowel ye (всё vsyo, есть yest)."""
    if language in ("ru", "be"):
        word = RU_VOWEL_BEFORE.sub(lambda m: m[1] + "ye", word).replace("ё", "yo").replace("Ё", "yo")
    return any_roman(word)


GREEK = dict(zip("αβγδεζηθικλμνξοπρσςτυφχψω", ["a", "v", "g", "d", "e", "z", "i", "th", "i", "k", "l", "m", "n", "ks",
                                                "o", "p", "r", "s", "s", "t", "i", "f", "kh", "ps", "o"], strict=True))
GREEK_PAIRS = {"ου": "u", "αι": "e", "ει": "i", "οι": "i", "υι": "i", "γγ": "ng", "τσ": "ts", "τζ": "dz"}
GREEK_STOPS = {"μπ": ("b", "mb"), "ντ": ("d", "nd"), "γκ": ("g", "ng")}  # at the start, inside
GREEK_VOICELESS = set("θκξπσςτφχψ")


def greek_roman(word: str) -> str:
    """Modern Greek as it is said: ου u, αι e, ει οι υι η υ i, ω o; αυ ευ av ev (af ef before a voiceless sound); μπ ντ
    γκ b d g at the start of a word, mb nd ng inside; γ before e or i as y. A diaeresis keeps a vowel apart (αϊ a-i)."""
    chars: list[str] = []
    for c in unicodedata.normalize("NFD", word.lower()):
        if c == "\u0308" and chars:
            chars[-1] += c  # its own vowel, never part of a pair
        elif not unicodedata.combining(c):
            chars.append(c)
    out, i = [], 0
    while i < len(chars):
        c = chars[i]
        pair = c + (chars[i + 1] if i + 1 < len(chars) else "")
        after = chars[i + 2] if i + 2 < len(chars) else ""
        if pair in GREEK_PAIRS:
            out.append(GREEK_PAIRS[pair])
            i += 2
        elif pair in ("αυ", "ευ", "ηυ"):
            out.append(GREEK[c] + ("f" if not after or after in GREEK_VOICELESS else "v"))
            i += 2
        elif pair in GREEK_STOPS:
            out.append(GREEK_STOPS[pair][0 if i == 0 else 1])
            i += 2
        elif c == "γ" and (pair[1:] in ("ε", "ι", "η", "υ") or pair[1:] + after in ("αι", "οι")):
            out.append("y")
            i += 1
        else:
            base = c[0]
            out.append(GREEK.get(base, base if base.isascii() else ""))
            i += 1
    return "".join(out)


def spaced_words(text: str, roman) -> list[dict]:
    """Scripts that put spaces between words: each word read by `roman`."""
    return [{"text": m[0], "a": m.start(), "b": m.end(), "roman": roman(m[0]), "latin": not any(
        kind_of(c) not in (None, "latin") for c in m[0])} for m in re.finditer(r"\S+", text)]


def any_roman(word: str) -> str:
    from anyascii import anyascii

    return anyascii(word).lower()


def read_line(text: str, script: str, language: str | None = None) -> list[dict]:
    """The line's words with a reading in Latin letters: to pair them with a romanization and, for the AUTO scripts
    without one, as the phonetic version itself."""
    if script == "ja":
        return japanese_words(text)
    if script == "zh":
        return chinese_words(text)
    if script == "ko":
        words = spaced_words(text, korean_roman)
    elif script == "devanagari":
        words = spaced_words(text, devanagari_roman)
    elif script == "cyrillic":
        words = spaced_words(text, lambda word: cyrillic_roman(word, language))
    elif script == "greek":
        words = spaced_words(text, greek_roman)
    else:
        words = spaced_words(text, any_roman)
    for word in words:
        word["roman"] = re.sub(r"[^\w'\u2019-]", "", word["roman"]) if not word["latin"] else word["text"].lower()
    return [w for w in words if w["roman"] or w["latin"]]


# --- the spelling for Portuguese ------------------------------------------------------------------------------------

def _rules(*pairs):
    return [(re.compile(a), b) for a, b in pairs]


PT_RULES = {
    "ja": _rules(("shi", "xi"), ("sh", "x"), ("(?<!t)ch", "tch"), ("j", "dj"), ("g(?=[ei])", "gu"),
                 ("oo", "ou"), ("ee", "ei"), ("y", "i"), ("w", "u")),
    "zh": _rules(("zh", "dj"), ("ch", "tch"), ("sh", "x"), ("q", "tch"), ("^j|(?<=[^a-z])j", "dj"), ("j", "dj"),
                 ("c", "ts"), ("z", "dz"), ("ü", "iu"), ("y", "i"), ("w", "u")),
    "ko": _rules(("eo", "ó"), ("eu", "u"), ("ae", "é"), ("oe", "uê"), ("(?<!t)ch", "tch"), ("j", "dj"),
                 ("y", "i"), ("w", "u")),
    "greek": _rules(("y(?=i)", ""), ("y", "i"), ("^kh", "r"), ("kh", "rr")),
    "cyrillic": _rules(("shch", "xtch"), ("zh", "j"), ("^kh", "r"), ("kh", "rr"), ("sh", "x"), ("(?<!t)ch", "tch"),
                       ("y(?=[aeiou])", "i"), ("y", "i"), ("['\u2019\u02b9\u02ba]", "")),
}


def portuguese(word: dict, script: str, roman: str | None = None) -> str:
    """The word as a Brazilian reads it. A Latin word stays as written; を is said o."""
    if word["latin"]:
        return word["text"]
    if word.get("particle_o"):
        return "o"
    text = (roman if roman is not None else word["roman"]).lower()
    for pattern, replacement in PT_RULES.get(script, []):
        text = pattern.sub(replacement, text)
    return text


# --- pairing with the fans' romanization ---------------------------------------------------------------------------

MACRONS = {"ā": "aa", "ē": "ee", "ī": "ii", "ō": "ou", "ū": "uu", "â": "aa", "ê": "ee", "î": "ii", "ô": "ou", "û": "uu"}


def letters(text: str) -> str:
    text = "".join(MACRONS.get(c, c) for c in text.lower())
    text = unicodedata.normalize("NFKD", text)
    return re.sub(r"[^a-z]", "", text)


def _match_letters(word: dict) -> str:
    # most romanizations write the particle を as "wo"
    return "wo" if word.get("particle_o") else letters(word["roman"])


def _split(parts: list[str], h: str) -> tuple[list[str], float]:
    """`h` cut where the joined `parts` land on it, letter by letter: each part takes the letters of `h` its own
    letters matched; letters `h` has more of, where a part starts, go to that part. Also how well the two agree."""
    d = "".join(parts)
    spans, a = [], 0
    for part in parts:
        spans.append((a, a + len(part)))
        a += len(part)
    matcher = difflib.SequenceMatcher(None, d, h, autojunk=False)
    where: list[int | None] = [None] * (len(d) + 1)
    inserted = {}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            inserted[i1] = j1
        for k in range(i1, i2):
            where[k] = j1 + (k - i1) * (j2 - j1) // max(i2 - i1, 1)
    where[len(d)] = len(h)
    for k in range(len(d) - 1, -1, -1):
        if where[k] is None:
            where[k] = where[k + 1]

    def start(k: int) -> int:
        return 0 if k == 0 else inserted.get(k, where[k])

    pieces = [h[start(a):(start(b) if b < len(d) else len(h))] if a < b else "" for a, b in spans]
    return pieces, matcher.ratio() if d or h else 1.0


def marry(words: list[dict], human: str) -> tuple[list[str], float]:
    """Each word's piece of a line of romanization, matched letter by letter."""
    return _split([_match_letters(word) for word in words], letters(human))


def pair(lines_words: list[list[dict]], human: list[str]) -> tuple[list[list[str] | None] | None, float]:
    """The fans' romanization read against the original in order: the whole text matched letter by letter, cut at the
    original's lines and then at its words. Times play no part, so it serves for lyrics without them and for versions
    of other lengths, as long as the words are the same. None when it does not fit (a translation, another song)."""
    parts = ["".join(_match_letters(word) for word in words) for words in lines_words]
    theirs = "".join(letters(text) for text in human if text)
    if not "".join(parts) or not theirs:
        return None, 0.0
    lines, agreement = _split(parts, theirs)
    sung = [n for n, part in enumerate(parts) if part]
    covered = sum(1 for n in sung if lines[n])
    if agreement < AGREEMENT or covered < COVERAGE * len(sung):
        return None, agreement
    # a line the romanization does not cover keeps the original's words
    pieces = [marry(words, text)[0] if text else None for words, text in zip(lines_words, lines, strict=True)]
    return pieces, agreement


def is_latin(text: str) -> bool:
    letters_ = [c for c in text if c.isalpha()]
    return bool(letters_) and sum(kind_of(c) == "latin" for c in letters_) >= 0.95 * len(letters_)


def fans_romanization(lyrics: dict, meta: dict) -> list[dict]:
    """The Latin versions of the same song on LRCLIB, with or without times, of any length (the agreement decides),
    not the original itself. Searched by the names the lyrics were found with and by the video's, cleaned and each
    part of a double name; then by the other names the same artist's versions of the song go by there, which is how a
    Japanese title leads to its romanized one ("真夜中のドア" → "Mayonaka no Door")."""
    from karaoke.pipeline.lyrics import guess_artist_track, lrclib_search

    pairs = [(lyrics.get("artist") or "", lyrics.get("track") or ""), guess_artist_track(meta)]
    artists = [clean_name(artist) for artist, _ in pairs if artist]
    queries = [f"{clean_name(artist)} {name}".strip() for artist, track in pairs for name in names_of(track)]
    seen, found, others = set(), [], set()

    def search(query: str) -> None:
        for candidate in lrclib_search(query):
            if candidate["id"] in seen:
                continue
            seen.add(candidate["id"])
            same_artist = any(letters(candidate.get("artist") or "") == letters(a) for a in artists)
            if same_artist and candidate.get("track"):
                others.add((candidate["artist"], candidate["track"]))
            if candidate["id"] == lyrics.get("id"):
                continue
            if is_latin(" ".join(line["text"] for line in candidate["lines"])):
                found.append(candidate)

    asked = list(dict.fromkeys(q for q in queries if q))
    for query in asked:
        search(query)
    if not found:  # the second step: the romanized names the same song goes by
        for artist, track in sorted(others):
            for name in names_of(track):
                query = f"{clean_name(artist)} {name}".strip()
                if is_latin(name) and query not in asked:
                    asked.append(query)
                    search(query)
    return found


BRACKETS = re.compile(r"\s*[(\[][^)\]]*[)\]]")
WORD_TIMES = re.compile(r"<\d+:\d+(?:\.\d+)?>")  # an LRC with a time for each word: <00:06.677>
SINGER = re.compile(r"^\s*[^\W\d][^:]{0,24}:\s+")  # "Rosé: ...", "Bruno & Rosé: ..."


def plain(text: str) -> str:
    """A line of the fans' romanization without what is not sung: the word times, the singer's name."""
    return SINGER.sub("", WORD_TIMES.sub("", text)).strip()


def readings_of(candidate: dict) -> list[list[str]]:
    """The candidate's lines as they are, without the word times and singers' names (plain), and also without what
    is in brackets: some romanizations carry the translation in brackets after each line ("... (I look up as I
    walk)"). The pairing keeps the one that agrees most."""
    raw = [line["text"] for line in candidate["lines"]]
    texts = [plain(text) for text in raw]
    bare = [BRACKETS.sub("", text).strip() for text in texts]
    return list({tuple(v): v for v in (raw, texts, bare)}.values())


# --- times ------------------------------------------------------------------------------------------------------------

def _close(char: str) -> bool:
    return kind_of(char) in ("kana", "han")


def line_text(aligned_line: dict, script: str) -> tuple[str, list[tuple[int, int]]]:
    """The line as the aligned words spell it and each word's span in it: a space between words, except between two
    of Japanese or Chinese, as the TV shows them (an English bit in a Japanese song keeps its spaces)."""
    text, spans = "", []
    for k, word in enumerate(aligned_line["words"]):
        if k and word["w"] and not (script in ("ja", "zh") and _close(text[-1:] or " ") and _close(word["w"][0])):
            text += " "
        spans.append((len(text), len(text) + len(word["w"])))
        text += word["w"]
    return text, spans


def _word_at(spans: list[tuple[int, int]], offset: int) -> int:
    """The aligned word an offset of the line falls in."""
    for k, (_, b) in enumerate(spans):
        if offset < b:
            return k
    return len(spans) - 1


def at_pauses(word: dict, piece: str, aligned_line: dict, spans: list[tuple[int, int]], text: str,
              script: str, language: str | None = None) -> list[tuple[dict, str]]:
    """A phonetic word read over aligned words with a pause between them, cut at each pause: each part takes the
    letters of `piece` that the original's characters on its side read, so it lights up when they are sung and not
    over the whole pause."""
    aligned = aligned_line["words"]
    j, k = _word_at(spans, word["a"]), _word_at(spans, max(word["b"] - 1, word["a"]))
    cuts = [m for m in range(j, k) if aligned[m + 1]["s"] - aligned[m]["e"] >= PAUSE_S]
    if word["latin"] or not cuts:
        return [(word, piece)]
    bounds = [word["a"], *(spans[m + 1][0] for m in cuts), word["b"]]
    groups = [(a, b) for a, b in itertools.pairwise(bounds) if a < b]
    readings = ["".join(_match_letters(w) for w in read_line(text[a:b], script, language)) for a, b in groups]
    parts = _split(readings, piece)[0]
    out = [({"text": text[a:b], "a": a, "b": b, "roman": part, "latin": False}, part)
           for (a, b), part in zip(groups, parts, strict=True) if part]
    return out if len(out) > 1 else [(word, piece)]


def confidence(words: list[dict]) -> float | None:
    """The alignment's confidence over some aligned words (their mean), None when it gave none. A phonetic word takes
    it from the words it reads, so the TV lights a line whole where the original's timing is unsure, as it does for
    the original (from 0.17.2; before, a phonetic line filled word by word with times nobody trusted)."""
    scores = [w["c"] for w in words if w.get("c") is not None]
    return round(sum(scores) / len(scores), 3) if scores else None


def timed(words: list[dict], spells: list[str], aligned_line: dict, spans: list[tuple[int, int]]) -> list[dict]:
    """The phonetic words with the times of the original characters they read, and their confidence. Several phonetic
    words inside one aligned word share its time by length; one over several aligned words spans them all (at_pauses
    has already cut it where the singing pauses)."""
    aligned = aligned_line["words"]
    first = [_word_at(spans, w["a"]) for w in words]
    last = [_word_at(spans, max(w["b"] - 1, w["a"])) for w in words]
    out = []
    for i, spell in enumerate(spells):
        j, k = first[i], last[i]
        s, e = aligned[j]["s"], aligned[k]["e"]
        if j == k:
            sharing = [n for n in range(len(words)) if first[n] == last[n] == j]
            if len(sharing) > 1:
                weights = [max(len(spells[n]), 1) for n in sharing]
                before = sum(weights[:sharing.index(i)])
                total = sum(weights)
                span = e - s
                s, e = s + span * before / total, s + span * (before + weights[sharing.index(i)]) / total
        out.append({"w": spell, "s": round(s, 3), "e": round(e, 3), "c": confidence(aligned[j:k + 1])})
    for n in range(1, len(out)):  # never back in time
        out[n]["s"] = max(out[n]["s"], out[n - 1]["s"])
        out[n]["e"] = max(out[n]["e"], out[n]["s"])
    return out


def as_original(line: dict) -> list[dict]:
    """A line left as the original: its words, times and confidence."""
    return [{"w": w["w"], "s": w["s"], "e": w["e"], "c": w.get("c")} for w in line["words"]]


def build(aligned: dict, script: str, pieces: list[list[str] | None], spell: bool = True) -> list[dict]:
    """The phonetic lines, one for each aligned line, from people's romanization (`pieces`, each line's word pieces).
    A line with none keeps the original's words; a word with no piece is left out, never read by the app."""
    lines = []
    for index, line in enumerate(aligned["lines"]):
        human = pieces[index] if index < len(pieces) else None
        text, spans = line_text(line, script)
        words = read_line(text, script, aligned.get("language")) if line["words"] and human else []
        if not words:
            lines.append({**line, "words": as_original(line)})
            continue
        kept = [cut for n, w in enumerate(words) if w["latin"] or human[n]
                for cut in at_pauses(w, human[n], line, spans, text, script, aligned.get("language"))]
        if not kept:
            lines.append({**line, "words": as_original(line)})
            continue
        spells = [portuguese(w, script, piece) if spell else (w["text"] if w["latin"] else piece) for w, piece in kept]
        lines.append({"start": line["start"], "end": line["end"], "low_confidence": line.get("low_confidence", False),
                      "words": timed([w for w, _ in kept], spells, line, spans)})
    return lines


def from_host(aligned: dict, script: str, texts: list[str]) -> list[dict]:
    """The host's romanization, one text for each line, exactly as typed: paired with the original as the fans' is,
    for the times, and then each typed word put on the times of the letters it covers."""
    pieces = []
    for line, text in zip(aligned["lines"], texts, strict=True):
        words = (read_line(line_text(line, script)[0], script, aligned.get("language"))
                 if line["words"] and text.strip() else [])
        pieces.append(marry(words, text)[0] if words else None)
    timeline = build(aligned, script, pieces, spell=False)
    return [{**line, "words": retime(line, text) or line["words"]} for line, text in zip(timeline, texts,
                                                                                         strict=True)]


def retime(line: dict, text: str) -> list[dict]:
    """The host's words for a line, timed against the line's phonetic words as they are: the letters matched, each
    new word takes the times of the old letters it lands on. The alignment does not run again."""
    new = text.split()
    if not new:
        return []
    old = [w for w in line["words"] if letters(w["w"])]
    if not old:
        span = (line["end"] - line["start"]) / len(new)
        return [{"w": w, "s": round(line["start"] + k * span, 3), "e": round(line["start"] + (k + 1) * span, 3)}
                for k, w in enumerate(new)]
    clock: list[tuple[float, float]] = []  # each old letter's time
    sure: list[dict] = []  # each old letter's word, for its confidence
    for w in old:
        n = len(letters(w["w"]))
        step = (w["e"] - w["s"]) / n
        clock += [(w["s"] + k * step, w["s"] + (k + 1) * step) for k in range(n)]
        sure += [w] * n
    d = "".join(letters(w["w"]) for w in old)
    h, spans = "", []
    for w in new:
        a = len(h)
        h += letters(w)
        spans.append((a, len(h)))
    where: list[int | None] = [None] * len(h)
    for _, i1, i2, j1, j2 in difflib.SequenceMatcher(None, h, d, autojunk=False).get_opcodes():
        for k in range(i1, i2):
            where[k] = min(j1 + (k - i1) * max(j2 - j1, 1) // max(i2 - i1, 1), len(d) - 1)
    out, last = [], line["start"]
    for w, (a, b) in zip(new, spans, strict=True):
        if a == b:  # no letters: a mark that takes no time
            out.append({"w": w, "s": round(last, 3), "e": round(last, 3)})
            continue
        s, e = clock[where[a]][0], clock[where[b - 1]][1]
        s = max(s, last)
        covered = list({id(x): x for x in sure[where[a]:where[b - 1] + 1]}.values())
        out.append({"w": w, "s": round(s, 3), "e": round(max(e, s), 3), "c": confidence(covered)})
        last = s
    return out


# --- the stage ------------------------------------------------------------------------------------------------------

def make(ctx) -> dict:
    """The phonetic version of the aligned lyrics, if they need one: the fans' or, for the AUTO scripts, the app's
    reading, kept until someone accepts it. Returns the manifest's info: the script (None for Latin lyrics) and the
    source, lrclib, pendente or nenhuma."""
    aligned = read_json(ctx.folder.aligned)
    if not aligned or not aligned.get("lines"):
        return {"script": None}
    text = "\n".join(w["w"] for line in aligned["lines"] for w in line["words"])
    script = script_of(text, aligned.get("language"))
    if script is None:
        ctx.folder.phonetic.unlink(missing_ok=True)
        ctx.folder.romanized.unlink(missing_ok=True)
        return {"script": None}

    pieces, agreement, chosen = None, None, None
    lyrics = read_json(ctx.folder.lyrics_source) or {}  # none when the lyrics were transcribed
    language = aligned.get("language")
    lines_words = [read_line(line_text(line, script)[0], script, language) for line in aligned["lines"]]
    for candidate in fans_romanization(lyrics, ctx.manifest.info("metadata")):
        for texts in readings_of(candidate):
            found, score = pair(lines_words, texts)
            log.info("romanização do LRCLIB %s: concordância %.2f", candidate["id"], score)
            if found is not None and (agreement is None or score > agreement):
                pieces, agreement, chosen = found, score, candidate
    if pieces is None and script in AUTO:
        ctx.folder.romanized.unlink(missing_ok=True)
        pieces = [[w["text"] if w["latin"] else re.sub(r"[^a-z\u00fc]", "", w["roman"].lower()) for w in words]
                  for words in lines_words]
        write_json(ctx.folder.phonetic, {"version": 1, "script": script, "language": language, "source": "pendente",
                                         "lines": build(aligned, script, pieces)})
        return {"script": script, "source": "pendente"}
    if pieces is None:
        ctx.folder.phonetic.unlink(missing_ok=True)
        ctx.folder.romanized.unlink(missing_ok=True)
        return {"script": script, "source": "nenhuma"}
    write_json(ctx.folder.romanized, chosen)
    write_json(ctx.folder.phonetic, {"version": 1, "script": script, "language": language,
                                     "source": "lrclib", "lines": build(aligned, script, pieces)})
    return {"script": script, "source": "lrclib", "agreement": round(agreement, 3)}


def run(ctx) -> dict:
    """Never fails the song: without a phonetic version (LRCLIB down, odd data), it plays with the original, and says
    the phonetic lyrics were not found."""
    try:
        return make(ctx)
    except Exception as exc:
        log.exception("letra fonética falhou")
        ctx.folder.phonetic.unlink(missing_ok=True)
        aligned = read_json(ctx.folder.aligned) or {}
        text = "\n".join(w["w"] for line in aligned.get("lines", []) for w in line["words"])
        script = script_of(text, aligned.get("language")) if text else None
        return {"script": script, "source": "nenhuma" if script else None, "error": str(exc)[:300]}
