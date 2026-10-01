"""Stage 5: the language of the lyrics, from their text (lingua). A transcription leaves it to Whisper."""
from __future__ import annotations

from karaoke.core.storage import read_json


def detect(text: str) -> str | None:
    """ISO 639-1 code (the form Whisper takes), or None when the text gives no answer."""
    from lingua import LanguageDetectorBuilder

    # Low accuracy mode is meant for short snippets; whole lyrics are long enough for it and it loads far faster.
    detector = LanguageDetectorBuilder.from_all_languages().with_low_accuracy_mode().build()
    language = detector.detect_language_of(text)
    return language.iso_code_639_1.name.lower() if language else None


def run(ctx) -> dict:
    lyrics = read_json(ctx.folder.lyrics_source)
    if not lyrics:
        return {"language": None, "by": "whisper"}
    text = "\n".join(line["text"] for line in lyrics["lines"] if line["text"])
    return {"language": detect(text), "by": "lingua"}
