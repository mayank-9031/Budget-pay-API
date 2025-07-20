"""remove_goals_table

Revision ID: 75e1abc456d9
Revises: a4e2f919b03d
Create Date: 2023-07-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '75e1abc456d9'
down_revision = 'add_notifications_table'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove foreign key constraints before dropping the table
    op.drop_constraint('goals_user_id_fkey', 'goals', type_='foreignkey')
    
    # Drop the goals table
    op.drop_table('goals')


def downgrade() -> None:
    # Recreate the goals table on downgrade
    op.create_table(
        'goals',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('target_amount', sa.Float(), nullable=False),
        sa.Column('deadline', sa.DateTime(), nullable=False),
        sa.Column('saved_amount', sa.Float(), default=0.0),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), default=None),
        sa.Column('updated_at', sa.DateTime(), default=None),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )