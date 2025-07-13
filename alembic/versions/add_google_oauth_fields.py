"""add_google_oauth_fields

Revision ID: add_google_oauth_fields
Revises: a4e2f919b03d
Create Date: 2024-07-01

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_google_oauth_fields'
down_revision = 'a4e2f919b03d'
branch_labels = None
depends_on = None


def upgrade():
    # Add Google OAuth fields to the users table
    op.add_column('users', sa.Column('google_id', sa.String(), nullable=True))
    op.add_column('users', sa.Column('google_access_token', sa.String(), nullable=True))
    op.add_column('users', sa.Column('google_refresh_token', sa.String(), nullable=True))
    op.add_column('users', sa.Column('google_token_expiry', sa.DateTime(), nullable=True))
    
    # Create a unique index on google_id
    op.create_index(op.f('ix_users_google_id'), 'users', ['google_id'], unique=True)


def downgrade():
    # Drop the Google OAuth fields from the users table
    op.drop_index(op.f('ix_users_google_id'), table_name='users')
    op.drop_column('users', 'google_token_expiry')
    op.drop_column('users', 'google_refresh_token')
    op.drop_column('users', 'google_access_token')
    op.drop_column('users', 'google_id') 