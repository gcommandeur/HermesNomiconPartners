"""add quali-call candidate fields and honorar-stufe fields

Revision ID: f2a7b9c3d1e4
Revises: d4e9f7c2a891
Create Date: 2026-07-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2a7b9c3d1e4"
down_revision: str | None = "d4e9f7c2a891"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    candidate_columns = [
        sa.Column(
            "fachliche_schwerpunkte",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("ausbildung_titel", sa.String(240)),
        sa.Column(
            "berufliche_stationen",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("aktuelles_umfeld_kanzleityp", sa.String(160)),
        sa.Column("aktuelles_umfeld_kanzleigroesse", sa.String(160)),
        sa.Column("wechselgrund", sa.Text()),
        sa.Column("remote_teilzeit_wuensche", sa.String(240)),
        sa.Column("passender_kanzleityp", sa.String(160)),
        sa.Column(
            "no_gos",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("freitext_notizen", sa.Text()),
    ]
    for column in candidate_columns:
        op.add_column("candidates", column)

    client_columns = [
        sa.Column(
            "honorar_stufe",
            sa.Enum(
                "STANDARD",
                "NACHLASS_1",
                "NACHLASS_2",
                "INDIVIDUELL",
                name="honorarstufe",
                native_enum=False,
                length=32,
            ),
            nullable=False,
            server_default="STANDARD",
        ),
        sa.Column("nachlass_begruendung", sa.Text()),
        sa.Column("agb_version", sa.String(40)),
    ]
    for column in client_columns:
        op.add_column("client_companies", column)


def downgrade() -> None:
    for name in ["agb_version", "nachlass_begruendung", "honorar_stufe"]:
        op.drop_column("client_companies", name)
    for name in [
        "freitext_notizen",
        "no_gos",
        "passender_kanzleityp",
        "remote_teilzeit_wuensche",
        "wechselgrund",
        "aktuelles_umfeld_kanzleigroesse",
        "aktuelles_umfeld_kanzleityp",
        "berufliche_stationen",
        "ausbildung_titel",
        "fachliche_schwerpunkte",
    ]:
        op.drop_column("candidates", name)
