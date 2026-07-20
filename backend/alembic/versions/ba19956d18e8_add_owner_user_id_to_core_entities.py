"""add nullable owner_user_id (FK users.id) to candidates, client_companies, candidate_submissions, tasks

Revision ID: ba19956d18e8
Revises: ec9beff2cbaa
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ba19956d18e8"
down_revision: str | None = "ec9beff2cbaa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, fk_constraint_name, index_name)
_TABLES = [
    ("candidates", "fk_candidates_owner_user_id_users", "ix_candidates_owner_user_id"),
    (
        "client_companies",
        "fk_client_companies_owner_user_id_users",
        "ix_client_companies_owner_user_id",
    ),
    (
        "candidate_submissions",
        "fk_candidate_submissions_owner_user_id_users",
        "ix_candidate_submissions_owner_user_id",
    ),
    ("tasks", "fk_tasks_owner_user_id_users", "ix_tasks_owner_user_id"),
]


def upgrade() -> None:
    # Nullable, kein Backfill - "nicht zugewiesen" ist ein gueltiger Zustand
    # fuer Bestandsdaten (Nutzer-Vorgabe: keine automatische Zuweisung).
    # batch_alter_table fuer die FK-Constraint (SQLite kann sie nicht per
    # plain ALTER TABLE nachtraeglich hinzufuegen, siehe bereits bestehende
    # Migration ec9beff2cbaa fuer dasselbe Muster).
    for table, fk_name, index_name in _TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column("owner_user_id", sa.Uuid(), nullable=True))
            batch_op.create_foreign_key(fk_name, "users", ["owner_user_id"], ["id"], ondelete="SET NULL")
            batch_op.create_index(index_name, ["owner_user_id"])


def downgrade() -> None:
    for table, fk_name, index_name in reversed(_TABLES):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_index(index_name)
            batch_op.drop_constraint(fk_name, type_="foreignkey")
            batch_op.drop_column("owner_user_id")
