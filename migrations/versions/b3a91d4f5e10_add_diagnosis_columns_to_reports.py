"""add diagnosis_patient, diagnosis_clinical, diagnosis_technical columns to reports

Revision ID: b3a91d4f5e10
Revises: 7ea86d35c5c9
Create Date: 2026-05-02 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3a91d4f5e10'
down_revision = '7ea86d35c5c9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('reports', schema=None) as batch_op:
        batch_op.add_column(sa.Column('diagnosis_patient', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('diagnosis_clinical', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('diagnosis_technical', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('reports', schema=None) as batch_op:
        batch_op.drop_column('diagnosis_technical')
        batch_op.drop_column('diagnosis_clinical')
        batch_op.drop_column('diagnosis_patient')
