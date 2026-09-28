"""add kpi_point_rules and app_settings tables

Revision ID: ec31119ae3be
Revises: ccaba8153441
Create Date: 2026-09-28

Auftrag "Geschaeftsfuehrer-Ansicht + KPI-Punkte-System + Live-Ranking":

- kpi_point_rules: ein Datensatz je Stufe der konsolidierten 7-Stufen-
  Pipeline (pitch + die 6 SubmissionStatus-Stufen ausser cancelled, siehe
  STAGE_ORDER in frontend/src/lib/stage-labels.ts / STAGE_KEYS in
  services/kpi_scoring.py), points=0 vorbelegt (Nutzer-Vorgabe: "wird noch
  definiert" - echte Platzhalter statt geratener Werte).
- app_settings: kleine Key-Value-Tabelle fuer globale Admin-Einstellungen,
  vorbelegt mit den beiden Ranking-Widget-Defaults (Metrik "points",
  Zeitraum "week").
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ec31119ae3be"
down_revision: str | None = "ccaba8153441"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Deckungsgleich mit services/kpi_scoring.py::STAGE_KEYS - dort die
# einzige Quelle der Wahrheit fuer die Stufen-Reihenfolge, hier nur als
# Seed-Daten fuer die initiale Zeile je Stufe.
_STAGE_KEYS = ["pitch", "qualification_call", "cv_in", "cv_out", "interview", "offer", "placement"]


def upgrade() -> None:
    op.create_table(
        "kpi_point_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kpi_point_rules")),
    )
    op.create_index(
        op.f("ix_kpi_point_rules_stage"), "kpi_point_rules", ["stage"], unique=True
    )

    op.create_table(
        "app_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_settings")),
    )
    op.create_index(op.f("ix_app_settings_key"), "app_settings", ["key"], unique=True)

    kpi_point_rules = sa.table(
        "kpi_point_rules",
        sa.column("id", sa.Uuid()),
        sa.column("stage", sa.String()),
        sa.column("points", sa.Integer()),
    )
    op.bulk_insert(
        kpi_point_rules,
        [{"id": uuid.uuid4(), "stage": stage, "points": 0} for stage in _STAGE_KEYS],
    )

    app_settings = sa.table(
        "app_settings",
        sa.column("id", sa.Uuid()),
        sa.column("key", sa.String()),
        sa.column("value", sa.JSON()),
    )
    op.bulk_insert(
        app_settings,
        [
            {"id": uuid.uuid4(), "key": "kpi_ranking_metric", "value": "points"},
            {"id": uuid.uuid4(), "key": "kpi_ranking_period", "value": "week"},
        ],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_app_settings_key"), table_name="app_settings")
    op.drop_table("app_settings")
    op.drop_index(op.f("ix_kpi_point_rules_stage"), table_name="kpi_point_rules")
    op.drop_table("kpi_point_rules")
