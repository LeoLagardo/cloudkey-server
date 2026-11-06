"""add_booking_engine_fields_to_room_types_and_rate_plans

Revision ID: 37797c5a715a
Revises: 1dda0401dd4b
Create Date: 2026-11-06 21:17:13.866411

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '37797c5a715a'
down_revision: Union[str, None] = '1dda0401dd4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('rate_plan_rates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('occupancy', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('extra_adult_price', sa.Numeric(precision=12, scale=2), nullable=True))
        batch_op.add_column(sa.Column('extra_child_price', sa.Numeric(precision=12, scale=2), nullable=True))

    with op.batch_alter_table('rate_plans', schema=None) as batch_op:
        batch_op.add_column(sa.Column('meal_plan', sa.Text(), server_default='EP', nullable=False))
        batch_op.add_column(sa.Column('no_of_meals', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('color_code', sa.String(length=7), server_default='#4F46E5', nullable=False))
        batch_op.add_column(sa.Column('extra_adult_rate', sa.Numeric(precision=12, scale=2), server_default='0.00', nullable=False))
        batch_op.add_column(sa.Column('extra_child_rate', sa.Numeric(precision=12, scale=2), server_default='0.00', nullable=False))
        batch_op.add_column(sa.Column('is_public_booking_engine', sa.Boolean(), server_default=sa.true(), nullable=False))
        batch_op.add_column(sa.Column('public_badge', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('included_perks', sa.JSON(), server_default='[]', nullable=False))
        batch_op.add_column(sa.Column('photos', sa.JSON(), server_default='[]', nullable=False))
        batch_op.add_column(sa.Column('public_sort_order', sa.Integer(), server_default='0', nullable=False))

    with op.batch_alter_table('reservation_room_rates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('occupancy', sa.Integer(), server_default='1', nullable=False))

    with op.batch_alter_table('room_types', schema=None) as batch_op:
        batch_op.add_column(sa.Column('photos', sa.JSON(), server_default='[]', nullable=False))
        batch_op.add_column(sa.Column('amenities', sa.JSON(), server_default='[]', nullable=False))
        batch_op.add_column(sa.Column('size_sq_ft', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('size_sqm', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('bed_config', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('view_type', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('subtitle', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('badge', sa.String(length=50), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('room_types', schema=None) as batch_op:
        batch_op.drop_column('badge')
        batch_op.drop_column('subtitle')
        batch_op.drop_column('view_type')
        batch_op.drop_column('bed_config')
        batch_op.drop_column('size_sqm')
        batch_op.drop_column('size_sq_ft')
        batch_op.drop_column('amenities')
        batch_op.drop_column('photos')

    with op.batch_alter_table('reservation_room_rates', schema=None) as batch_op:
        batch_op.drop_column('occupancy')

    with op.batch_alter_table('rate_plans', schema=None) as batch_op:
        batch_op.drop_column('public_sort_order')
        batch_op.drop_column('photos')
        batch_op.drop_column('included_perks')
        batch_op.drop_column('public_badge')
        batch_op.drop_column('is_public_booking_engine')
        batch_op.drop_column('extra_child_rate')
        batch_op.drop_column('extra_adult_rate')
        batch_op.drop_column('color_code')
        batch_op.drop_column('no_of_meals')
        batch_op.drop_column('meal_plan')

    with op.batch_alter_table('rate_plan_rates', schema=None) as batch_op:
        batch_op.drop_column('extra_child_price')
        batch_op.drop_column('extra_adult_price')
        batch_op.drop_column('occupancy')
