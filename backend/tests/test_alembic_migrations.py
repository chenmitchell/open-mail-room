"""M0-R1 suggestion: an executed-migration test to catch model/migration
drift. `Base.metadata.create_all()` (used by every other test's `db_engine`
fixture) and `alembic upgrade head` (used by real deployments, via
scripts/entrypoint.sh) are two independent ways of building the schema --
nothing previously asserted they produce the same result. If someone edits
a model without writing/committing the matching migration, this is the test
that should fail.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

BACKEND_DIR = Path(__file__).resolve().parent.parent


def test_alembic_upgrade_head_runs_cleanly(tmp_path):
    db_path = tmp_path / "alembic_migration_test.db"
    db_url = f"sqlite:///{db_path}"

    env = dict(os.environ)
    env["DATABASE_URL"] = db_url

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}"
    assert db_path.exists()


def test_alembic_schema_matches_models(tmp_path):
    """After `alembic upgrade head`, the resulting schema's tables/columns/
    indexes should match what `Base.metadata` (i.e. the model classes)
    describes -- otherwise the migration has drifted from the models."""
    db_path = tmp_path / "alembic_drift_test.db"
    db_url = f"sqlite:///{db_path}"

    env = dict(os.environ)
    env["DATABASE_URL"] = db_url

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}"

    from app.models import Base

    migrated_engine = create_engine(db_url)
    migrated_inspector = inspect(migrated_engine)
    migrated_tables = set(migrated_inspector.get_table_names()) - {"alembic_version"}

    model_tables = set(Base.metadata.tables.keys())
    assert migrated_tables == model_tables, (
        f"Tables only in migrations: {migrated_tables - model_tables}; "
        f"tables only in models: {model_tables - migrated_tables}"
    )

    for table_name in sorted(model_tables):
        migrated_columns = {
            col["name"] for col in migrated_inspector.get_columns(table_name)
        }
        model_columns = {col.name for col in Base.metadata.tables[table_name].columns}
        assert migrated_columns == model_columns, (
            f"Column mismatch on '{table_name}': "
            f"only in migrations: {migrated_columns - model_columns}; "
            f"only in models: {model_columns - migrated_columns}"
        )

    mail_items_indexes = {
        idx["name"] for idx in migrated_inspector.get_indexes("mail_items")
    }
    assert "ix_mail_items_status_received_at" in mail_items_indexes
    assert "ix_mail_items_recipient_employee_id_status" in mail_items_indexes

    migrated_engine.dispose()
