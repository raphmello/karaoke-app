import pytest
import requests

from karaoke.pipeline import lyrics as lyrics_module
from karaoke.pipeline.lyrics import (
    artist_and_track,
    choose,
    fits_video,
    guess_artist_track,
    match_lyrics,
    parse_lrc,
    same_name,
)


def test_parse_lrc_keeps_empty_lines_and_repeated_stamps():
    lines = parse_lrc("[ar:Someone]\n[00:12.50]first line\n[00:20.00]\n[01:02.25][00:30.00]chorus\nno stamp here")
    assert [(round(line["t"], 2), line["text"]) for line in lines] == [
        (12.5, "first line"),
        (20.0, ""),
        (30.0, "chorus"),
        (62.25, "chorus"),
    ]


def test_artist_and_track_come_from_youtube_music_metadata_first():
    meta = {"track": "Tempo Perdido", "artist": "Legião Urbana, Outro", "title": "whatever", "channel": "x"}
    assert guess_artist_track(meta) == ("Legião Urbana", "Tempo Perdido")


def test_artist_and_track_from_a_noisy_title():
    meta = {"title": "Michel Teló - Ai Se Eu Te Pego -  Video Oficial (Ao Vivo) [HD]", "channel": "Michel Teló"}
    assert guess_artist_track(meta) == ("Michel Teló", "Ai Se Eu Te Pego")


def test_a_track_named_like_noise_is_kept():
    assert guess_artist_track({"title": "Oasis - Live Forever", "channel": "Oasis"}) == ("Oasis", "Live Forever")


def test_artist_from_the_channel_when_the_title_has_no_dash():
    meta = {"title": "Bohemian Rhapsody (Remastered 2011)", "channel": "Queen - Topic"}
    assert guess_artist_track(meta) == ("Queen", "Bohemian Rhapsody")


def candidate(synced: bool, duration: float) -> dict:
    return {"synced": synced, "duration": duration, "lines": []}


def test_choose_prefers_synced_then_closest_duration():
    plain_exact = candidate(False, 200)
    synced_far = candidate(True, 206)
    synced_close = candidate(True, 202)
    assert choose([plain_exact, synced_far, synced_close], 200) is synced_close


def test_synced_lyrics_without_duration_must_fit_the_video():
    lyrics = {"synced": True, "lines": [{"t": 5.0, "text": "a"}, {"t": 180.0, "text": "b"}]}
    assert fits_video(lyrics, 200)
    assert not fits_video(lyrics, 19)  # ends long after the video
    assert not fits_video(lyrics, 600)  # covers too little of it
    assert fits_video({"synced": False, "lines": [{"t": None, "text": "a"}]}, 19)


def test_choose_rejects_other_versions_of_the_song():
    assert choose([candidate(True, 260)], 200) is None
    assert choose([], 200) is None


def test_a_track_artist_title_is_read_the_right_way_by_the_channel():
    meta = {"title": "In The End [Official HD Music Video] - Linkin Park", "channel": "Linkin Park"}
    assert guess_artist_track(meta) == ("Linkin Park", "In The End")


def test_the_usual_order_stays_when_the_channel_is_someone_else():
    meta = {"title": "Linkin Park - In the End (Lyrics)", "channel": "Taj Tracks"}
    assert guess_artist_track(meta) == ("Linkin Park", "In the End")


def test_the_lyrics_found_correct_a_reversed_guess():
    found = {"artist": "[LINKIN PARK]", "track": "In The End"}
    assert match_lyrics("In The End", "Linkin Park", found) == ("Linkin Park", "In The End")
    assert match_lyrics("Linkin Park", "In The End", found) == ("Linkin Park", "In The End")
    assert match_lyrics("Linkin Park", "In The End", None) == ("Linkin Park", "In The End")


def test_names_compare_without_case_spaces_or_punctuation():
    assert same_name("[LINKIN PARK]", "Linkin Park")
    assert not same_name("", "")
    assert not same_name("Legião Urbana", "Legiao Urbana")  # accents count: no false matches across languages


def test_the_channel_outranks_lyrics_filed_the_wrong_way_round():
    meta = {"title": "In The End [Official HD Music Video] - Linkin Park", "channel": "Linkin Park"}
    reversed_on_lrclib = {"artist": "In The End", "track": "Linkin Park"}
    assert artist_and_track(meta, reversed_on_lrclib) == ("Linkin Park", "In The End")


def test_without_the_channel_the_lyrics_decide():
    meta = {"title": "In The End - Linkin Park", "channel": "Some Uploader"}
    assert artist_and_track(meta, {"artist": "Linkin Park", "track": "In The End"}) == ("Linkin Park", "In The End")


class Answer:
    def __init__(self, status):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)

    def json(self):
        return []


def answering(monkeypatch, *answers):
    calls = []

    def get(url, params, headers, timeout):
        calls.append(url)
        answer = answers[len(calls) - 1]
        if isinstance(answer, Exception):
            raise answer
        return Answer(answer)

    monkeypatch.setattr(lyrics_module.requests, "get", get)
    monkeypatch.setattr(lyrics_module.time, "sleep", lambda s: None)
    return calls


def test_a_busy_lrclib_is_tried_again(monkeypatch):
    calls = answering(monkeypatch, 503, requests.ConnectionError("reset"), 200)
    assert lyrics_module.lrclib_request("search", {"q": "x"}).status_code == 200
    assert len(calls) == 3


def test_an_lrclib_still_down_after_four_tries_fails_the_stage(monkeypatch):
    calls = answering(monkeypatch, 503, 503, 503, 503)
    with pytest.raises(requests.HTTPError):
        lyrics_module.lrclib_request("search", {"q": "x"})
    assert len(calls) == 4


def test_not_found_is_an_answer_not_an_outage(monkeypatch):
    calls = answering(monkeypatch, 404)
    assert lyrics_module.lrclib_get("Artista", "Música", 200) is None
    assert len(calls) == 1
