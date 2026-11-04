"""phonetic_source: where a song's phonetic lyrics came from (docs/ARCHITECTURE.md, phase 6, "Letra fonética")

Empty for every song already there: they get phonetic lyrics by reprocessing that stage.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-19
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE songs ADD COLUMN phonetic_source VARCHAR(20)")


def downgrade() -> None:
    op.execute("ALTER TABLE songs DROP COLUMN phonetic_source")
