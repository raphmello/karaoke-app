"""Phase 5 through the API: the host's lyrics, reprocessing, removal and restore, history, the panel, and the
player's guide voice, delay and skip between songs."""
import json

import pytest
from helpers import write_manifest
from sqlalchemy import select

from karaoke.core.db import transaction
from karaoke.core.models import Job, QueueEntry, Song
from karaoke.core.songs import STAGES, with_dependents
from karaoke.core.storage import SongFolder

VIDEO, OTHER = "dQw4w9WgXcQ", "aaaaaaaaaaa"
STAGES_DONE = {stage: {"found": True, "source": "lrclib"} if stage == "lyrics" else {} for stage in STAGES}


def make_song(db, settings, video=VIDEO, status="ready", stages=None, title="Música"):
    with transaction(db) as session:
        session.add(Song(video_id=video, title=title, status=status))
    write_manifest(settings, video, "ready" if status == "ready" else status, STAGES_DONE if stages is None else stages)


def jobs(db, video=VIDEO) -> list[Job]:
    with db() as session:
        return list(session.scalars(select(Job).where(Job.video_id == video).order_by(Job.id)))


def song(db, video=VIDEO) -> Song:
    with db() as session:
        return session.get(Song, video)


def test_the_stages_match_the_pipeline():
    from karaoke.pipeline.process import default_stages

    assert tuple(stage.name for stage in default_stages()) == STAGES


def test_redoing_a_stage_redoes_what_reads_it():
    assert with_dependents({"alignment"}) == ["alignment"]
    assert with_dependents({"separation"}) == ["separation", "alignment", "key", "encode"]
    assert with_dependents({"lyrics"}) == ["lyrics", "language", "alignment"]
    assert with_dependents(set()) == []


@pytest.mark.parametrize(("method", "path", "body"), [
    ("put", f"/api/songs/{VIDEO}/lyrics", {"text": "la la"}),
    ("post", f"/api/songs/{VIDEO}/reprocess", {"stages": []}),
    ("delete", f"/api/songs/{VIDEO}", None),
    ("post", f"/api/songs/{VIDEO}/restore", None),
    ("get", f"/api/songs/{VIDEO}/history", None),
    ("get", "/api/jobs", None),
    ("get", "/api/disk", None),
    ("get", "/api/library?removed=true", None),
])
def test_only_the_host(phone, code, db, settings, method, path, body):
    make_song(db, settings)
    ana = phone(code, "Ana")
    response = getattr(ana, method)(path, **({"json": body} if body is not None else {}))
    assert response.status_code in (401, 403)


# --- lyrics and reprocessing ---------------------------------------------------------------------------------------

def test_new_lyrics_redo_only_the_language_and_the_alignment(host, code, db, settings):
    make_song(db, settings)
    lrc = "[00:12.00] primeira linha\n[00:15.50] segunda linha\n"
    assert host.put(f"/api/songs/{VIDEO}/lyrics", json={"text": lrc}).status_code == 204

    source = json.loads(SongFolder(settings.media_dir, VIDEO).lyrics_source.read_text(encoding="utf-8"))
    assert source["source"] == "manual" and source["synced"]
    assert source["lines"] == [{"t": 12.0, "text": "primeira linha"}, {"t": 15.5, "text": "segunda linha"}]
    assert [job.options for job in jobs(db)] == [{"redo": ["language", "alignment"]}]
    assert (song(db).status, song(db).lyrics_source) == ("pending", "manual")
    assert host.put(f"/api/songs/{VIDEO}/lyrics", json={"text": lrc}).status_code == 409  # a job is pending


def test_pasted_lyrics_answer_the_transcription_question(phone, host, code, db, settings):
    ana = phone(code, "Ana")
    entry = ana.post(f"/api/rooms/{code}/queue", json={"video_id": VIDEO}).json()["id"]
    with transaction(db) as session:
        session.get(Song, VIDEO).status = "awaiting_decision"
        session.get(QueueEntry, entry).status = "awaiting_decision"
        session.scalar(select(Job)).status = "done"
    write_manifest(settings, VIDEO, "awaiting_decision", {"metadata": {}, "lyrics": {"found": False}})

    assert host.put(f"/api/songs/{VIDEO}/lyrics", json={"text": "uma linha\noutra linha"}).status_code == 204
    with db() as session:
        assert session.get(QueueEntry, entry).status == "queued"
    manifest = json.loads(SongFolder(settings.media_dir, VIDEO).manifest.read_text(encoding="utf-8"))
    assert manifest["stages"]["lyrics"]["found"] and not manifest["stages"]["lyrics"]["synced"]


def test_reprocess_runs_the_chosen_stages_and_their_dependents(host, code, db, settings):
    make_song(db, settings)
    response = host.post(f"/api/songs/{VIDEO}/reprocess", json={"stages": ["separation"]})
    assert response.json() == {"stages": ["separation", "alignment", "key", "encode"]}
    assert jobs(db)[0].options == {"redo": ["separation", "alignment", "key", "encode"]}
    assert host.post(f"/api/songs/{VIDEO}/reprocess", json={"stages": ["nope"]}).status_code == 409


def test_a_failed_song_is_tried_again(host, code, db, settings):
    make_song(db, settings, status="failed", stages={"metadata": {}, "lyrics": {"found": True}})
    assert host.post(f"/api/songs/{VIDEO}/reprocess", json={"stages": []}).json() == {"stages": []}
    assert jobs(db)[0].options == {}
    assert song(db).status == "pending"


# --- removal, restore, history -------------------------------------------------------------------------------------

def test_removing_a_song_takes_its_entries_out_and_restoring_needs_no_processing(phone, host, code, db, settings):
    make_song(db, settings)
    ana = phone(code, "Ana")
    entry = ana.post(f"/api/rooms/{code}/queue", json={"video_id": VIDEO}).json()["id"]

    assert host.delete(f"/api/songs/{VIDEO}").status_code == 204
    assert (song(db).status, song(db).removed_reason) == ("removed", "host")
    with db() as session:
        assert session.get(QueueEntry, entry).status == "removed"
    assert [s["video_id"] for s in host.get("/api/library").json()] == []
    assert [s["video_id"] for s in host.get("/api/library?removed=true").json()] == [VIDEO]
    assert host.delete(f"/api/songs/{VIDEO}").status_code == 409

    assert host.post(f"/api/songs/{VIDEO}/restore").status_code == 204
    assert song(db).status == "ready"
    assert jobs(db) == []  # the files were kept: nothing runs
    assert host.post(f"/api/songs/{VIDEO}/restore").status_code == 409

    events = host.get(f"/api/songs/{VIDEO}/history").json()
    assert [(e["kind"], e["by"]) for e in events] == [("removed", "host"), ("reactivated", "host")]


def test_history_names_who_did_it(phone, host, code, db, settings):
    phone(code, "Ana").post(f"/api/rooms/{code}/queue", json={"video_id": OTHER})
    assert [(e["kind"], e["by"]) for e in host.get(f"/api/songs/{OTHER}/history").json()] == [("created", "Ana")]


# --- panel ---------------------------------------------------------------------------------------------------------

def test_the_jobs_panel_lists_the_newest_first(phone, host, code, db, settings):
    ana = phone(code, "Ana")
    ana.post(f"/api/rooms/{code}/queue", json={"video_id": VIDEO})
    ana.post(f"/api/rooms/{code}/queue", json={"video_id": OTHER})
    panel = host.get("/api/jobs").json()
    assert [(j["video_id"], j["status"]) for j in panel] == [(OTHER, "pending"), (VIDEO, "pending")]


def test_the_disk_panel_counts_the_songs_and_what_removed_ones_keep(host, code, db, settings):
    make_song(db, settings)
    make_song(db, settings, OTHER, status="removed")
    (SongFolder(settings.media_dir, OTHER).root / "big.bin").write_bytes(b"x" * 1000)
    panel = host.get("/api/disk").json()
    assert panel["songs"] == 2 and panel["removed_songs"] == 1
    assert panel["removed_bytes"] >= 1000 and panel["media_bytes"] > panel["removed_bytes"]
    assert panel["free_bytes"] > 0 and isinstance(panel["low"], bool)


# --- player ---------------------------------------------------------------------------------------------------------

def receive(ws, kind):
    while True:
        message = ws.receive_json()
        if message["type"] == kind:
            return message


def test_the_host_sets_the_guide_voice_and_the_delay_on_the_tv(host, code):
    with host.websocket_connect(f"/ws/rooms/{code}?role=tv") as tv:
        assert host.post(f"/api/rooms/{code}/player/guide", json={"value": 40}).status_code == 204
        assert receive(tv, "player.command") == {"type": "player.command", "action": "guide", "value": 40}
        assert host.post(f"/api/rooms/{code}/player/delay", json={"value": -150}).status_code == 204
        assert receive(tv, "player.command")["value"] == -150
    assert host.post(f"/api/rooms/{code}/player/guide", json={"value": 140}).status_code == 422
    assert host.post(f"/api/rooms/{code}/player/delay").status_code == 422


def test_skip_between_songs_skips_the_one_about_to_start(phone, host, code, db, settings):
    make_song(db, settings, OTHER, title="Pronta")
    ana = phone(code, "Ana")
    waiting = ana.post(f"/api/rooms/{code}/queue", json={"video_id": VIDEO}).json()["id"]  # still processing
    ready = ana.post(f"/api/rooms/{code}/queue", json={"video_id": OTHER}).json()["id"]

    assert host.post(f"/api/rooms/{code}/player/skip").status_code == 204
    with db() as session:
        assert session.get(QueueEntry, ready).status == "skipped"  # what the TV would have played
        assert session.get(QueueEntry, waiting).status == "queued"
