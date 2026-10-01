"""The job's bookkeeping, with stand-in stages: what runs, what is skipped, where it stops."""
import pytest

from karaoke.core.config import Settings
from karaoke.core.storage import Manifest, SongFolder
from karaoke.pipeline.process import Stage, lyrics_gate, process

VIDEO = "dQw4w9WgXcQ"


class Recorder:
    def __init__(self, fail_at: str | None = None, lyrics_found: bool = True):
        self.calls: list[str] = []
        self.fail_at = fail_at
        self.lyrics_found = lyrics_found

    def stage(self, name: str) -> Stage:
        def run(ctx):
            self.calls.append(name)
            if name == self.fail_at:
                raise RuntimeError(f"{name} broke")
            return {"found": self.lyrics_found} if name == "lyrics" else {}

        return Stage(name, run, stop=lyrics_gate if name == "lyrics" else (lambda ctx: None))

    def stages(self) -> list[Stage]:
        return [self.stage(n) for n in ("metadata", "lyrics", "download", "separation", "alignment", "encode")]


def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path)


def test_second_run_does_nothing(tmp_path):
    first = Recorder()
    assert process(VIDEO, settings(tmp_path), stages=first.stages()) == "ready"
    assert first.calls == ["metadata", "lyrics", "download", "separation", "alignment", "encode"]

    second = Recorder()
    assert process(VIDEO, settings(tmp_path), stages=second.stages()) == "ready"
    assert second.calls == []


def test_interrupted_run_resumes_at_the_failed_stage(tmp_path):
    broken = Recorder(fail_at="separation")
    with pytest.raises(RuntimeError):
        process(VIDEO, settings(tmp_path), stages=broken.stages())
    manifest = Manifest.load(SongFolder(tmp_path / "media", VIDEO))
    assert manifest.status == "failed" and "separation broke" in manifest.data["error"]

    resumed = Recorder()
    assert process(VIDEO, settings(tmp_path), stages=resumed.stages()) == "ready"
    assert resumed.calls == ["separation", "alignment", "encode"]


def test_missing_lyrics_stop_before_the_download(tmp_path):
    no_lyrics = Recorder(lyrics_found=False)
    assert process(VIDEO, settings(tmp_path), stages=no_lyrics.stages()) == "awaiting_decision"
    assert no_lyrics.calls == ["metadata", "lyrics"]

    asked_again = Recorder(lyrics_found=False)
    assert process(VIDEO, settings(tmp_path), stages=asked_again.stages()) == "awaiting_decision"
    assert asked_again.calls == []


def test_transcription_continues_from_the_download(tmp_path):
    process(VIDEO, settings(tmp_path), stages=Recorder(lyrics_found=False).stages())

    yes = Recorder(lyrics_found=False)
    assert process(VIDEO, settings(tmp_path), transcribe=True, stages=yes.stages()) == "ready"
    assert yes.calls == ["download", "separation", "alignment", "encode"]
    assert Manifest.load(SongFolder(tmp_path / "media", VIDEO)).data["transcribe"] is True
