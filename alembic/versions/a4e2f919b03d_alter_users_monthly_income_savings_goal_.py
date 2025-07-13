"""alter_users_monthly_income_savings_goal

Revision ID: a4e2f919b03d
Revises: 
Create Date: 2023-12-01

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a4e2f919b03d'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Alter monthly_income and savings_goal_amount columns to use String type
    op.alter_column('users', 'monthly_income', type_=sa.String(), nullable=True)
    op.alter_column('users', 'savings_goal_amount', type_=sa.String(), nullable=True)


def downgrade():
    # Revert back to original types (assuming they were numeric)
    op.alter_column('users', 'monthly_income', type_=sa.Numeric(), nullable=True)
    op.alter_column('users', 'savings_goal_amount', type_=sa.Numeric(), nullable=True)
