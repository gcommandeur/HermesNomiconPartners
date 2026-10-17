"""NOMICON: Equal Pay bestätigen (Datum und Person am Einsatz)

Revision ID: nomicon08equalpay
Revises: nomicon07prior
Create Date: 2026-10-17

Nur in der Nomicon-Kopie. Zwei neue, leere Spalten am Einsatz; es werden keine Werte erfunden und
keine bestehenden Daten verändert.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "nomicon08equalpay"
down_revision: str | None = "nomicon07prior"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    with op.batch_alter_table("staffing_assignments") as batch_op:
        batch_op.add_column(sa.Column("equal_pay_confirmed_on", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("equal_pay_confirmed_by_user_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            op.f("fk_staffing_assignments_equal_pay_confirmed_by_user_id_users"),
            "users",
            ["equal_pay_confirmed_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Revert this migration."""
    with op.batch_alter_table("staffing_assignments") as batch_op:
        batch_op.drop_constraint(
            op.f("fk_staffing_assignments_equal_pay_confirmed_by_user_id_users"),
            type_="foreignkey",
        )
        batch_op.drop_column("equal_pay_confirmed_by_user_id")
        batch_op.drop_column("equal_pay_confirmed_on")
