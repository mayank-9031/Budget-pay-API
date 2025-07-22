"""add_is_fixed_to_categories

Revision ID: add_is_fixed_to_categories
Revises: 75e1abc456d9
Create Date: 2023-06-20 08:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_is_fixed_to_categories'
down_revision = '75e1abc456d9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('categories', sa.Column('is_fixed', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('categories', 'is_fixed') 