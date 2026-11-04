"""The phonetic lyrics (docs/ARCHITECTURE.md, "Pronúncia"): which lyrics get them, the readings that
pair a romanization with the original and the spelling for Portuguese, the fans' romanization paired word by word,
the times, the stage that never fails the song and never shows a reading of its own, and the host's romanization.
The phrases are made up for the tests."""
import json
from itertools import pairwise

import pytest
from helpers import write_manifest

from karaoke.core.db import transaction
from karaoke.core.models import Song, SongEvent
from karaoke.core.storage import Manifest, SongFolder, read_json, write_json
from karaoke.pipeline import phonetic
from karaoke.pipeline.process import Context

VIDEO = "dQw4w9WgXcQ"



# --- which lyrics ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("text", "language", "script"), [
    ("君を待っている", None, "ja"),
    ("学生", "ja", "ja"),  # kanji alone are Japanese when the language says so
    ("我爱你", None, "zh"),
    ("사랑해요", None, "ko"),
    ("Привет мир", None, "cyrillic"),
    ("Καλημέρα", None, "greek"),
    ("नमस्ते", None, "devanagari"),
    ("שלום עולם", None, None),  # Hebrew and Arabic leave the vowels out
    ("مرحبا", None, None),
    ("eu te amo, meu bem", None, None),
    ("Yes 君が好きだよ", None, "ja"),  # mostly Japanese, with an English bit
    ("I love you so much and more 君", None, None),  # a word: too little to need it
    ("Oh baby baby 사랑해요", None, "ko"),  # an English song with a Korean part, as APT.
])
def test_which_lyrics_get_a_phonetic_version(text, language, script):
    assert phonetic.script_of(text, language) == script


# --- readings and spelling ------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("kana", "roman"), [
    ("きみ", "kimi"), ("まって", "matte"), ("まっちゃ", "matcha"), ("きょう", "kyou"), ("しゃしん", "shashin"),
    ("コーヒー", "koohii"), ("ティー", "tii"), ("じゅう", "juu"),
])
def test_kana_in_hepburn(kana, roman):
    assert phonetic.kana_romaji(kana) == roman


def spelled(text, script):
    return [phonetic.portuguese(w, script) for w in phonetic.read_line(text, script)]


def test_japanese_words_group_as_a_reader_does_and_are_spelled_for_portuguese():
    words = phonetic.read_line("君を待っている", "ja")
    assert [w["text"] for w in words] == ["君", "を", "待っている"]
    assert spelled("君を待っている", "ja") == ["kimi", "o", "matteiru"]
    assert spelled("私は学生です", "ja")[1:] == ["ua", "gakusei", "desu"]  # は said wa; です apart from the noun
    assert spelled("写真を撮った", "ja") == ["xaxin", "o", "totta"]


def test_a_latin_word_in_a_japanese_line_stays_as_written():
    assert spelled("Yes 君が好き", "ja")[0] == "Yes"


def test_other_scripts():
    assert spelled("我爱你", "zh") == ["uo", "ai", "ni"]
    assert spelled("사랑해요", "ko") == ["saranghéio"]  # ㄹ between vowels is r
    assert spelled("щука хорошо", "cyrillic") == ["xtchuka", "roroxo"]
    assert [w["roman"] for w in phonetic.read_line("नमस्ते", "devanagari")] == ["namaste"]


@pytest.mark.parametrize(("word", "roman"), [
    ("없이", "eopsi"), ("읽어", "ilgeo"), ("앉아", "anja"),  # a double final moves its second sound
    ("싫어", "sireo"), ("않아", "ana"), ("좋아", "joa"),  # ㅎ goes silent before a vowel
    ("좋다", "jota"), ("않고", "anko"), ("정숙해", "jeongsukae"),  # ㅎ next to ㄱ ㄷ ㅈ makes them aspirated
    ("거짓말", "geojinmal"), ("있는", "inneun"),  # nasalization, as before
])
def test_korean_as_it_is_said(word, roman):
    assert phonetic.korean_roman(word) == roman


def test_russian_yo_and_ye_and_greek_as_it_is_said():
    assert phonetic.cyrillic_roman("всё", "ru") == "vsyo"
    assert phonetic.cyrillic_roman("есть", "ru").startswith("yest")
    assert phonetic.cyrillic_roman("есть", "uk").startswith("est")  # Ukrainian says it e
    assert [phonetic.greek_roman(w) for w in ["ουρανός", "ευχαριστώ", "αυτό", "μπορώ", "άγγελος", "γεια", "παιδί"]] == [
        "uranos", "efkharisto", "afto", "boro", "angelos", "yia", "pedi"]
    assert phonetic.greek_roman("Ευρωπαϊκή") == "evropaiki"  # the diaeresis keeps αϊ apart


# --- the fans' romanization -----------------------------------------------------------------------------------------

def test_the_human_reading_goes_to_the_word_it_reads():
    words = phonetic.read_line("瞬間を待つ", "ja")  # the dictionary reads shunkan; sung toki
    pieces, _ = phonetic.marry(words, "Toki wo matsu")
    assert pieces == ["toki", "wo", "matsu"]
    assert [phonetic.portuguese(w, "ja", p) for w, p in zip(words, pieces, strict=True)] == ["toki", "o", "matsu"]


def test_the_romanization_pairs_in_order_whatever_its_lines_and_a_translation_is_refused():
    lines = [phonetic.read_line(text, "ja") for text in ["君を待つ", "夜が来る"]]
    human = ["Kimi wo", "matsu yoru ga", "kuru"]  # cut in other places than the original
    pieces, agreement = phonetic.pair(lines, human)
    assert agreement > 0.9 and pieces == [["kimi", "wo", "matsu"], ["yoru", "ga", "kuru"]]

    assert phonetic.pair(lines, ["I wait for you", "The night comes"])[0] is None


# --- times ----------------------------------------------------------------------------------------------------------

def aligned_line(chars, start=10.0, step=0.5):
    """One word per character, as Whisper gives Japanese."""
    return {"start": start, "end": start + step * len(chars), "low_confidence": False,
            "words": [{"w": c, "s": start + k * step, "e": start + (k + 1) * step, "c": 0.9}
                      for k, c in enumerate(chars)]}


def test_each_phonetic_word_takes_the_time_of_the_characters_it_reads():
    line = aligned_line("君を待つ")
    [built] = phonetic.build({"lines": [line]}, "ja", [["kimi", "wo", "matsu"]])
    assert [(w["w"], w["s"], w["e"]) for w in built["words"]] == [("kimi", 10.0, 10.5), ("o", 10.5, 11.0),
                                                                   ("matsu", 11.0, 12.0)]


def test_an_english_bit_in_a_japanese_line_keeps_its_spaces():
    line = {"start": 0.0, "end": 4.0, "low_confidence": False, "words": [
        {"w": w, "s": float(k), "e": k + 1.0, "c": 0.9} for k, w in enumerate(["my", "love", "君", "を"])]}
    assert phonetic.line_text(line, "ja")[0] == "my love 君を"
    [built] = phonetic.build({"lines": [line]}, "ja", [["my", "love", "kimi", "wo"]])
    assert [w["w"] for w in built["words"]][:2] == ["my", "love"]


def test_words_inside_one_spread_word_share_its_time():
    line = {"start": 10.0, "end": 12.0, "low_confidence": True,
            "words": [{"w": "君を待つ", "s": 10.0, "e": 12.0, "c": None}]}
    [built] = phonetic.build({"lines": [line]}, "ja", [["kimi", "wo", "matsu"]])
    times = [(w["s"], w["e"]) for w in built["words"]]
    assert times[0][0] == 10.0 and times[-1][1] == 12.0
    assert all(a[1] <= b[0] + 1e-6 for a, b in pairwise(times))


def test_without_people_s_words_a_line_keeps_the_original_never_a_reading_of_the_app():
    lines = [aligned_line("君を待つ"), aligned_line("夜が来る", start=14.0)]
    built = phonetic.build({"lines": lines}, "ja", [None, ["yoru", "", "kuru"]])
    assert [w["w"] for w in built[0]["words"]] == list("君を待つ")  # not covered: the original
    assert [w["w"] for w in built[1]["words"]] == ["ioru", "kuru"]  # a word without a piece is left out


def test_the_host_words_keep_the_times_of_the_letters_they_replace():
    line = {"start": 10.0, "end": 12.0, "words": [{"w": "kimi", "s": 10.0, "e": 10.5}, {"w": "o", "s": 10.5, "e": 11.0},
                                                  {"w": "matsu", "s": 11.0, "e": 12.0}]}
    words = phonetic.retime(line, "kimi wo matsu yo")
    assert [w["w"] for w in words] == ["kimi", "wo", "matsu", "yo"]
    assert words[0]["s"] == 10.0 and words[2]["s"] >= 11.0 and words[-1]["e"] <= 12.0


# --- the stage ------------------------------------------------------------------------------------------------------

def folder_with(settings, lines, sung=None, language="ja"):
    folder = SongFolder(settings.media_dir, VIDEO)
    write_json(folder.aligned, {"version": 1, "language": language, "source": "lrclib", "lines": lines})
    if sung is not None:
        write_json(folder.lyrics_source, {"source": "lrclib", "id": 1, "artist": "Alguém", "track": "Canção",
                                          "duration": 200, "synced": True, "lines": sung})
    manifest = write_manifest(settings, VIDEO, "processing", {"metadata": {"title": "Canção", "duration_s": 200}})
    return Context(settings=settings, folder=folder, manifest=manifest)


def test_with_the_fans_romanization_the_stage_uses_it(settings, monkeypatch):
    texts = ["瞬間を待つ", "君を待つ", "夜が来る", "君が好き"]
    sung = [{"t": 10.0 + 4 * k, "text": text} for k, text in enumerate(texts)]
    ctx = folder_with(settings, [aligned_line(text, start=line["t"]) for text, line in zip(texts, sung, strict=True)],
                      sung=sung)
    human = ["Toki wo matsu", "Kimi wo matsu", "Yoru ga kuru", "Kimi ga suki"]
    found = [{"id": 2, "synced": True, "duration": 200,
              "lines": [{"t": line["t"] + 0.2, "text": text} for text, line in zip(human, sung, strict=True)]}]
    monkeypatch.setattr(phonetic, "fans_romanization", lambda lyrics, meta: found)
    info = phonetic.run(ctx)
    assert info["script"] == "ja" and info["source"] == "lrclib"
    saved = read_json(ctx.folder.phonetic)
    assert [w["w"] for w in saved["lines"][0]["words"]] == ["toki", "o", "matsu"]
    assert read_json(ctx.folder.romanized)["id"] == 2


def test_without_it_the_song_says_the_phonetic_lyrics_were_not_found(settings, monkeypatch):
    ctx = folder_with(settings, [aligned_line("私は")], sung=[{"t": 10.0, "text": "私は"}])
    monkeypatch.setattr(phonetic, "fans_romanization", lambda lyrics, meta: [])
    assert phonetic.run(ctx) == {"script": "ja", "source": "nenhuma"}
    assert not ctx.folder.phonetic.exists()


def test_without_the_fans_korean_gets_the_app_s_reading_waiting_for_an_answer(settings, monkeypatch):
    line = {"start": 10.0, "end": 13.0, "low_confidence": False, "words": [
        {"w": w, "s": 10.0 + k, "e": 11.0 + k, "c": 0.9} for k, w in enumerate(["Oh", "baby", "사랑해요"])]}
    ctx = folder_with(settings, [line], language="ko", sung=[{"t": 10.0, "text": "Oh baby 사랑해요"}])
    monkeypatch.setattr(phonetic, "fans_romanization", lambda lyrics, meta: [])
    assert phonetic.run(ctx) == {"script": "ko", "source": "pendente"}  # prepared, used only when someone says yes
    saved = read_json(ctx.folder.phonetic)
    assert saved["source"] == "pendente" and not ctx.folder.romanized.exists()
    assert [(w["w"], w["s"]) for w in saved["lines"][0]["words"]] == [("Oh", 10.0), ("baby", 11.0),
                                                                       ("saranghéio", 12.0)]


def test_lyrics_in_latin_letters_get_no_phonetic_version(settings):
    line = {"start": 1.0, "end": 2.0, "low_confidence": False, "words": [{"w": "olá", "s": 1.0, "e": 2.0, "c": 1}]}
    ctx = folder_with(settings, [line], language="pt")
    assert phonetic.run(ctx) == {"script": None}
    assert not ctx.folder.phonetic.exists()


def test_the_stage_never_fails_the_song(settings, monkeypatch):
    ctx = folder_with(settings, [aligned_line("君を待つ")], sung=[{"t": 10.0, "text": "君を待つ"}])

    def broken(*args):
        raise RuntimeError("quebrou")

    monkeypatch.setattr(phonetic, "fans_romanization", broken)  # LRCLIB down, for one
    info = phonetic.run(ctx)
    assert info["source"] == "nenhuma" and "quebrou" in info["error"]
    assert not ctx.folder.phonetic.exists()


# --- the API ----------------------------------------------------------------------------------------------------------

def ready_song(db, settings, source):
    """A ready song in Japanese: with the fans' phonetic lyrics (source lrclib) or without them (nenhuma)."""
    with transaction(db) as session:
        session.add(Song(video_id=VIDEO, title="Canção", status="ready", phonetic_source=source))
    write_manifest(settings, VIDEO, "ready", {"phonetic": {"script": "ja", "source": source}})
    folder = SongFolder(settings.media_dir, VIDEO)
    write_json(folder.aligned, {"version": 1, "language": "ja", "source": "lrclib",
                                "lines": [aligned_line("君を待つ")]})
    if source == "lrclib":
        write_json(folder.phonetic, {"version": 1, "script": "ja", "source": "lrclib", "lines": [
            {"start": 10.0, "end": 12.0, "low_confidence": False, "words": [
                {"w": "kimi", "s": 10.0, "e": 10.5}, {"w": "o", "s": 10.5, "e": 11.0},
                {"w": "matsu", "s": 11.0, "e": 12.0}]},
        ]})
    return folder


def test_the_song_says_where_its_phonetic_lyrics_are(host, code, db, settings):
    ready_song(db, settings, "lrclib")
    song = host.get("/api/library").json()[0]
    assert song["phonetic_source"] == "lrclib" and "/lyrics/phonetic.json" in song["media"]["phonetic"]


def test_without_them_the_song_says_so_and_has_no_address(host, code, db, settings):
    ready_song(db, settings, "nenhuma")
    song = host.get("/api/library").json()[0]
    assert song["phonetic_source"] == "nenhuma" and song["media"]["phonetic"] is None


def test_the_host_corrects_the_phonetic_lyrics_as_typed(host, phone, code, db, settings):
    folder = ready_song(db, settings, "lrclib")
    path = f"/api/songs/{VIDEO}/phonetic"
    assert phone(code, "Ana").put(path, json={"lines": ["kimi uo matsu"]}).status_code in (401, 403)
    assert host.put(path, json={"lines": ["a", "b"]}).status_code == 409  # one text per line
    assert host.put(path, json={"lines": ["kimi uo mátsu"]}).status_code == 204
    saved = json.loads(folder.phonetic.read_text(encoding="utf-8"))
    assert saved["source"] == "host" and [w["w"] for w in saved["lines"][0]["words"]] == ["kimi", "uo", "mátsu"]
    assert Manifest.load(folder).info("phonetic")["source"] == "host"
    with db() as session:
        assert session.get(Song, VIDEO).phonetic_source == "host"


def test_without_the_fans_the_host_writes_it_timed_with_the_original(host, code, db, settings):
    folder = ready_song(db, settings, "nenhuma")
    assert host.put(f"/api/songs/{VIDEO}/phonetic", json={"lines": ["Kimi o matsu"]}).status_code == 204
    words = json.loads(folder.phonetic.read_text(encoding="utf-8"))["lines"][0]["words"]
    assert [w["w"] for w in words] == ["Kimi", "o", "matsu"]
    assert words[0]["s"] == 10.0 and words[-1]["e"] == 12.0  # the times of 君 … つ
    song = host.get("/api/library").json()[0]
    assert song["phonetic_source"] == "host" and song["media"]["phonetic"]


def test_a_song_in_latin_letters_takes_no_phonetic_lyrics(host, code, db, settings):
    with transaction(db) as session:
        session.add(Song(video_id=VIDEO, title="Canção", status="ready"))
    write_manifest(settings, VIDEO, "ready", {"phonetic": {"script": None}})
    assert host.put(f"/api/songs/{VIDEO}/phonetic", json={"lines": ["la"]}).status_code == 409


# --- finding the fans' romanization -----------------------------------------------------------------------------------

def test_a_repeat_the_romanization_leaves_out_keeps_the_original_line():
    texts = ["君を待つ", "夜が来る", "君が好き", "君が好き", "君が好き", "夜が来る"]
    lines = [phonetic.read_line(text, "ja") for text in texts]
    human = ["Kimi wo matsu", "Yoru ga kuru", "Kimi ga suki", "Kimi ga suki", "Yoru ga kuru"]  # one chorus less
    pieces, agreement = phonetic.pair(lines, human)
    assert agreement > 0.85 and pieces[0] == ["kimi", "wo", "matsu"] and pieces[-1] == ["yoru", "ga", "kuru"]
    assert sum(piece is None for piece in pieces) == 1


def test_a_japanese_title_leads_to_the_romanized_one(monkeypatch):
    original = {"id": 1, "artist": "Alguém", "track": "君の歌", "synced": True, "duration": 200,
                "lines": [{"t": 1.0, "text": "君を待つ"}]}
    same_song = {"id": 2, "artist": "Alguém", "track": "Kimi no Uta", "synced": True, "duration": 201,
                 "lines": [{"t": 1.0, "text": "君を待つ"}]}
    fans = {"id": 3, "artist": "Alguém", "track": "Kimi no Uta", "synced": True, "duration": 199,
            "lines": [{"t": 1.0, "text": "Kimi wo matsu"}]}
    asked = []

    def search(query):
        asked.append(query)
        return [original, same_song] if "君" in query else [same_song, fans]

    monkeypatch.setattr("karaoke.pipeline.lyrics.lrclib_search", search)
    lyrics = {"id": 1, "artist": "Alguém", "track": "君の歌 [Tradução em PT-BR]", "duration": None}
    found = phonetic.fans_romanization(lyrics, {"title": "Alguém - 君の歌", "duration_s": 200})
    assert [c["id"] for c in found] == [3]
    assert "Alguém Kimi no Uta" in asked


def test_a_word_sung_over_a_pause_is_cut_there():
    line = {"start": 10.0, "end": 13.5, "low_confidence": False, "words": [
        {"w": "ま", "s": 10.0, "e": 10.5, "c": 0.9}, {"w": "つ", "s": 13.0, "e": 13.5, "c": 0.9}]}
    [built] = phonetic.build({"lines": [line]}, "ja", [["matsu"]])
    assert [(w["w"], w["s"], w["e"]) for w in built["words"]] == [("ma", 10.0, 10.5), ("tsu", 13.0, 13.5)]

    line["words"][1].update(s=10.6, e=11.0)  # no pause: one word
    [built] = phonetic.build({"lines": [line]}, "ja", [["matsu"]])
    assert [(w["w"], w["s"], w["e"]) for w in built["words"]] == [("matsu", 10.0, 11.0)]


def test_a_romanization_with_the_translation_in_brackets_pairs_without_it():
    lines = [phonetic.read_line(text, "ja") for text in ["君を待つ", "夜が来る"]]
    candidate = {"lines": [{"t": 1.0, "text": "Kimi wo matsu (I wait for you)"},
                           {"t": 5.0, "text": "Yoru ga kuru (The night comes)"}]}
    scores = [phonetic.pair(lines, texts)[1] for texts in phonetic.readings_of(candidate)]
    assert scores[0] < phonetic.AGREEMENT < scores[1]


def test_the_fans_text_loses_the_word_times_and_the_singers_names():
    assert phonetic.plain("Rosé: <00:06.677>Kimi <00:07.066>wo matsu") == "Kimi wo matsu"
    assert phonetic.plain("Bruno & Rosé: Yoru ga kuru") == "Yoru ga kuru"
    assert phonetic.plain("Yoru ga kuru") == "Yoru ga kuru"


def waiting_for_the_answer(db, settings, phone, code):
    """A ready song whose automatic phonetic lyrics wait for an answer, in Ana's entry."""
    ana = phone(code, "Ana")
    response = ana.post(f"/api/rooms/{code}/queue", json={"video_id": VIDEO})
    assert response.status_code == 201, response.text
    with transaction(db) as session:
        song = session.get(Song, VIDEO)
        song.status, song.phonetic_source = "ready", "pendente"
    folder = SongFolder(settings.media_dir, VIDEO)
    write_manifest(settings, VIDEO, "ready", {"phonetic": {"script": "ko", "source": "pendente"}})
    write_json(folder.phonetic, {"version": 1, "script": "ko", "source": "pendente", "lines": []})
    return ana, response.json()["id"], folder


def test_the_owner_says_yes_and_the_automatic_phonetic_lyrics_play(db, settings, phone, code, host):
    ana, entry, folder = waiting_for_the_answer(db, settings, phone, code)
    path = f"/api/rooms/{code}/queue/{entry}/phonetic"
    library = host.get("/api/library").json()[0]
    assert library["phonetic_source"] == "pendente" and library["media"]["phonetic"] is None  # original on the TV
    assert phone(code, "Bia").post(path, json={"accept": True}).status_code == 403  # not hers
    assert ana.post(path, json={"accept": True}).status_code == 204
    assert read_json(folder.phonetic)["source"] == "auto" and Manifest.load(folder).info("phonetic")["source"] == "auto"
    with db() as session:
        assert session.get(Song, VIDEO).phonetic_source == "auto"
        kinds = [e.kind for e in session.query(SongEvent).filter(SongEvent.video_id == VIDEO)]
    assert "phonetic_auto_accepted" in kinds
    assert "/lyrics/phonetic.json" in host.get("/api/library").json()[0]["media"]["phonetic"]
    assert ana.post(path, json={"accept": False}).status_code == 409  # answered already


def test_no_keeps_the_original_and_the_answer_is_kept(db, settings, phone, code, host):
    _, entry, folder = waiting_for_the_answer(db, settings, phone, code)
    assert host.post(f"/api/rooms/{code}/queue/{entry}/phonetic", json={"accept": False}).status_code == 204
    assert not folder.phonetic.exists() and Manifest.load(folder).info("phonetic")["source"] == "nenhuma"
    with db() as session:
        assert session.get(Song, VIDEO).phonetic_source == "nenhuma"
        kinds = [e.kind for e in session.query(SongEvent).filter(SongEvent.video_id == VIDEO)]
    assert "phonetic_auto_declined" in kinds


def test_the_host_answers_from_the_library_too(db, settings, phone, code, host):
    waiting_for_the_answer(db, settings, phone, code)
    path = f"/api/songs/{VIDEO}/phonetic/auto"
    assert phone(code, "Ana").post(path, json={"accept": True}).status_code in (401, 403)  # only the host
    assert host.post(path, json={"accept": True}).status_code == 204
    with db() as session:
        assert session.get(Song, VIDEO).phonetic_source == "auto"
    assert host.post(path, json={"accept": True}).status_code == 409  # answered already


def test_a_phonetic_word_takes_the_confidence_of_what_it_reads():
    line = {"start": 10.0, "end": 12.0, "low_confidence": False, "words": [
        {"w": "君", "s": 10.0, "e": 10.5, "c": 0.2}, {"w": "を", "s": 10.5, "e": 11.0, "c": 0.3},
        {"w": "待つ", "s": 11.0, "e": 12.0, "c": None}]}
    [built] = phonetic.build({"lines": [line]}, "ja", [["kimi", "wo", "matsu"]])
    # the TV lights the line whole when this is low, as for the original
    assert [(w["w"], w["c"]) for w in built["words"]] == [("kimi", 0.2), ("o", 0.3), ("matsu", None)]
    [kept] = phonetic.build({"lines": [line]}, "ja", [None])
    assert [w["c"] for w in kept["words"]] == [0.2, 0.3, None]
