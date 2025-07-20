"""add notifications table

Revision ID: add_notifications_table
Revises: add_notifications_table
Create Date: 2024-07-19

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_notifications_table'
down_revision = 'add_google_oauth_fields'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'notifications',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String, nullable=False),
        sa.Column('message', sa.String, nullable=False),
        sa.Column('type', sa.String, nullable=False),
        sa.Column('status', sa.String, nullable=False),
        sa.Column('category_id', sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey('categories.id', ondelete='SET NULL'), nullable=True),
        sa.Column('is_read', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )

def downgrade():
    op.drop_table('notifications')