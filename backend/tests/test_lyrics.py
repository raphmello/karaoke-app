from karaoke.pipeline.lyrics import choose, fits_video, guess_artist_track, parse_lrc


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
