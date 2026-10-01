import pytest

from karaoke.core.storage import Manifest, SongFolder, atomic_path, parse_video_id, read_json, write_json

VIDEO = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "value",
    [
        VIDEO,
        f"https://www.youtube.com/watch?v={VIDEO}",
        f"https://www.youtube.com/watch?list=PL123&v={VIDEO}&t=42",
        f"https://youtu.be/{VIDEO}?si=abc",
        f"https://www.youtube.com/shorts/{VIDEO}",
        f"  {VIDEO}  ",
    ],
)
def test_parse_video_id_accepts_ids_and_urls(value):
    assert parse_video_id(value) == VIDEO


@pytest.mark.parametrize("value", ["", "abc", "../../etc/passwd", "dQw4w9WgXcQ/..", "https://example.com/x"])
def test_parse_video_id_rejects_anything_else(value):
    with pytest.raises(ValueError):
        parse_video_id(value)


def test_ids_differing_only_in_case_get_different_folders(tmp_path):
    assert SongFolder(tmp_path, "abcdefghijk").root != SongFolder(tmp_path, "ABCDEFGHIJK").root


def test_atomic_path_replaces_only_on_success(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("old")
    with pytest.raises(RuntimeError), atomic_path(target) as tmp:
        tmp.write_text("half")
        raise RuntimeError("crash")
    assert target.read_text() == "old"
    assert list(tmp_path.iterdir()) == [target]

    with atomic_path(target) as tmp:
        assert tmp.suffix == ".txt"  # tools that read the format from the extension keep working
        tmp.write_text("new")
    assert target.read_text() == "new"


def test_json_round_trip_keeps_accents(tmp_path):
    write_json(tmp_path / "x.json", {"título": "Evidências"})
    assert read_json(tmp_path / "x.json") == {"título": "Evidências"}
    assert "Evidências" in (tmp_path / "x.json").read_text(encoding="utf-8")


def test_manifest_records_stages_across_loads(tmp_path):
    folder = SongFolder(tmp_path, VIDEO)
    folder.root.mkdir()
    manifest = Manifest.load(folder)
    assert manifest.status == "pending" and not manifest.done("metadata")
    manifest.complete("metadata", {"title": "x"})

    again = Manifest.load(folder)
    assert again.done("metadata")
    assert again.info("metadata")["title"] == "x"
