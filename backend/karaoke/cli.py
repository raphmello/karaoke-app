"""Command line: `karaoke process <video>` builds a song's complete folder; `karaoke worker` runs the job loop;
`karaoke rebuild-index` recreates the songs table from the manifests."""
from __future__ import annotations

import argparse
import logging
import sys

from karaoke.core.config import load_settings
from karaoke.core.storage import parse_video_id

EXIT_READY, EXIT_FAILED, EXIT_AWAITING = 0, 1, 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="karaoke")
    commands = parser.add_subparsers(dest="command", required=True)
    process_cmd = commands.add_parser("process", help="processa um vídeo do YouTube e gera a pasta completa da música")
    process_cmd.add_argument("video", help="ID do vídeo ou URL do YouTube")
    process_cmd.add_argument(
        "--transcribe", action="store_true", help="se a letra não for encontrada, transcreve a voz com o Whisper"
    )
    commands.add_parser("worker", help="pega jobs no banco, por prioridade, e roda o pipeline")
    commands.add_parser("rebuild-index", help="recria a tabela songs a partir dos manifest.json do armazenamento")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("audio_separator", "urllib3", "numba", "httpx", "alembic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if args.command == "worker":
        from karaoke.worker.main import main as worker

        worker(load_settings())
        return 0
    if args.command == "rebuild-index":
        return rebuild_index()

    try:
        video_id = parse_video_id(args.video)
    except ValueError as exc:
        parser.error(str(exc))

    from karaoke.pipeline.process import process

    settings = load_settings()
    try:
        status = process(video_id, settings, transcribe=args.transcribe)
    except Exception as exc:
        logging.getLogger("karaoke").error("falhou: %s: %s", type(exc).__name__, exc)
        return EXIT_FAILED
    folder = settings.media_dir / video_id
    if status == "awaiting_decision":
        print(f"Letra não encontrada para {video_id}. Nada foi baixado. Para transcrever a voz, rode de novo com "
              f"--transcribe.")
        return EXIT_AWAITING
    print(f"Pronto: {folder}")
    return EXIT_READY


def rebuild_index() -> int:
    from karaoke.core.db import make_engine, make_sessionmaker, migrate, transaction
    from karaoke.core.songs import rebuild_index as rebuild

    settings = load_settings()
    engine = make_engine(settings.database_url)
    migrate(engine)
    with transaction(make_sessionmaker(engine)) as session:
        counts = rebuild(session, settings)
    print(f"Músicas criadas: {counts['created']}; atualizadas: {counts['updated']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
