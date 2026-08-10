"""add tasks.snoozed_until + tasks.source_mail_message_id

Grundlage fuer die Reaktion auf automatisch aus Mails erzeugte Tasks
(Terminierungs-Agent, Schritt 3 des Ausbauplans):
- snoozed_until: "spaeter erinnern" fuer POST /tasks/{id}/snooze -
  Task-Liste blendet Zukuenftiges standardmaessig aus, ohne den Task
  wirklich zu schliessen.
- source_mail_message_id: Rueckverweis auf die Mail, aus der ein Task
  automatisch entstand (services/mail_sync.py) - fuer Nachvollziehbarkeit,
  ohne einen zweiten parallelen Weg zur Activity zu schaffen (MailMessage
  hat bereits created_activity_id).

Revision ID: d8f3a2c6e910
Revises: c4e8a1f7b920
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d8f3a2c6e910"
down_revision: str | None = "c4e8a1f7b920"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLite kann eine Fremdschluessel-Constraint nicht per plain ALTER TABLE
    # nachtraeglich hinzufuegen - batch_alter_table umgeht das (auf Postgres
    # ein direktes ALTER TABLE, gleiches Muster wie ec9beff2cbaa).
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("source_mail_message_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_tasks_source_mail_message_id_mail_messages",
            "mail_messages",
            ["source_mail_message_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_tasks_snoozed_until", "tasks", ["snoozed_until"])


def downgrade() -> None:
    op.drop_index("ix_tasks_snoozed_until", table_name="tasks")
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_constraint("fk_tasks_source_mail_message_id_mail_messages", type_="foreignkey")
        batch_op.drop_column("source_mail_message_id")
        batch_op.drop_column("snoozed_until")
