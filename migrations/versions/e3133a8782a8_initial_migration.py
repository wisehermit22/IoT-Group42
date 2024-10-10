"""Initial migration

Revision ID: e3133a8782a8
Revises: 
Create Date: 2024-10-10 13:44:00.325408

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e3133a8782a8'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('device_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('consumption_limit', sa.Integer(), nullable=True),
    sa.Column('lockout_timer', sa.Integer(), nullable=True),
    sa.Column('inventory_count', sa.Integer(), nullable=True),
    sa.Column('lock_status', sa.Boolean(), nullable=True),
    sa.Column('consumption_count', sa.Integer(), nullable=True),
    sa.Column('lockout_end_time', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('device_settings')
    # ### end Alembic commands ###
