"""The migrations must build exactly the schema the models describe."""
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from app.db import Base, _alembic_config


def test_migrations_match_models(tmp_path: Path):
    eng = create_engine(f"sqlite:///{(tmp_path / 'm.db').as_posix()}")
    cfg = _alembic_config()
    with eng.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"Model changes without a migration: {diff}"
