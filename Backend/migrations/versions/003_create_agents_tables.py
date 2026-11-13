"""create agents and agent_activity tables

Revision ID: 003_agents
Revises: 002_connections
Create Date: 2025-01-XX

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003_agents'
down_revision: Union[str, None] = '002_connections'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Agents table
    op.create_table(
        'agents',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('agent_id', sa.String(length=128), nullable=False, unique=True, index=True),
        sa.Column('owner_wallet', sa.String(length=64), nullable=False, index=True),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('permissions', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='active'),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_agents'))
    )
    op.create_index(op.f('ix_agent_id'), 'agents', ['agent_id'], unique=True)
    op.create_index(op.f('ix_owner_wallet'), 'agents', ['owner_wallet'], unique=False)
    
    # Agent activity table
    op.create_table(
        'agent_activity',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('agent_id', sa.String(length=128), nullable=False, index=True),
        sa.Column('activity_type', sa.String(length=64), nullable=False),
        sa.Column('endpoint', sa.String(length=256), nullable=False),
        sa.Column('method', sa.String(length=16), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=False),
        sa.Column('request_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('response_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_agent_activity'))
    )
    op.create_index(op.f('ix_agent_activity_created_at'), 'agent_activity', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_agent_activity_created_at'), table_name='agent_activity')
    op.drop_table('agent_activity')
    
    op.drop_index(op.f('ix_owner_wallet'), table_name='agents')
    op.drop_index(op.f('ix_agent_id'), table_name='agents')
    op.drop_table('agents')
