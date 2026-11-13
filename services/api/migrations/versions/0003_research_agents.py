"""A005 Competitor Analysis Agent and A006 Customer Persona Agent.

Revision ID: 0003
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO agents VALUES
          ('competitor-analysis','A005','Competitor Analysis Agent',3,'research',
           'Finds the businesses you compete with, reads their websites and compares them with you.',
           'read','0.1.0',TRUE),
          ('customer-persona','A006','Customer Persona Agent',3,'strategy',
           'Describes the people who buy from you, what they need and what message will reach them.',
           'read','0.1.0',TRUE);
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM agents WHERE slug IN ('competitor-analysis','customer-persona')")
