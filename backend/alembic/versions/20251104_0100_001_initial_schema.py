"""Initial schema with all entities

Revision ID: 001
Revises:
Create Date: 2025-11-04 01:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create ENUM types
    op.execute("CREATE TYPE subscription_tier AS ENUM ('basic', 'professional', 'enterprise')")
    op.execute("CREATE TYPE website_status AS ENUM ('pending_approval', 'active', 'paused', 'failed')")
    op.execute("CREATE TYPE stock_status AS ENUM ('in_stock', 'out_of_stock', 'limited_availability', 'unknown')")
    op.execute("CREATE TYPE extraction_method AS ENUM ('url_pattern_amazon', 'url_pattern_shopify', 'url_pattern_generic', 'html_opengraph', 'html_schema', 'none')")
    op.execute("CREATE TYPE crawl_status AS ENUM ('pending', 'running', 'success', 'partial_success', 'failed')")
    op.execute("CREATE TYPE webhook_status AS ENUM ('pending', 'success', 'failed', 'retrying', 'exhausted')")
    op.execute("CREATE TYPE crawl_trigger AS ENUM ('scheduled', 'manual', 'discovery', 'retry')")

    # Create clients table
    op.create_table(
        'clients',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('subscription_tier', sa.Enum('basic', 'professional', 'enterprise', name='subscription_tier'), nullable=False, server_default='basic'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.text('TRUE')),
        sa.Column('webhook_secret_current', sa.String(64), nullable=False),
        sa.Column('webhook_secret_previous', sa.String(64), nullable=True),
        sa.Column('secret_rotation_expires_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('max_websites', sa.Integer, nullable=False, server_default='20'),
        sa.Column('max_products_per_website', sa.Integer, nullable=False, server_default='100'),
    )
    op.create_index('idx_clients_email', 'clients', ['email'], unique=True)
    op.create_index('idx_clients_active', 'clients', ['is_active'], postgresql_where=sa.text('is_active = TRUE'))

    # Create api_keys table
    op.create_table(
        'api_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('client_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('clients.id', ondelete='CASCADE'), nullable=False),
        sa.Column('key_hash', sa.String(60), nullable=False, unique=True),
        sa.Column('key_prefix', sa.String(16), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('last_used_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('invalidated_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('permissions_scope', postgresql.JSONB, nullable=False, server_default='["read", "write"]'),
    )
    op.create_index('idx_api_keys_hash', 'api_keys', ['key_hash'], unique=True)
    op.create_index('idx_api_keys_client_active', 'api_keys', ['client_id'], postgresql_where=sa.text('invalidated_at IS NULL'))
    op.create_index('idx_api_keys_prefix', 'api_keys', ['key_prefix'])

    # Create monitored_websites table
    op.create_table(
        'monitored_websites',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('client_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('clients.id', ondelete='CASCADE'), nullable=False),
        sa.Column('base_url', sa.String(2048), nullable=False),
        sa.Column('seed_urls', postgresql.JSONB, nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('status', sa.Enum('pending_approval', 'active', 'paused', 'failed', name='website_status'), nullable=False, server_default='pending_approval'),
        sa.Column('crawl_frequency_minutes', sa.Integer, nullable=False, server_default='1440'),
        sa.Column('price_change_threshold_pct', sa.Numeric(5, 2), nullable=False, server_default='1.00'),
        sa.Column('retention_days', sa.Integer, nullable=False, server_default='90'),
        sa.Column('discovered_products_pending', postgresql.JSONB, nullable=True),
        sa.Column('approved_product_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('last_successful_crawl_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('last_crawl_status', sa.String(50), nullable=True),
        sa.Column('webhook_endpoint_url', sa.String(2048), nullable=True),
        sa.Column('webhook_enabled', sa.Boolean, nullable=False, server_default=sa.text('TRUE')),
        sa.Column('consecutive_failures', sa.Integer, nullable=False, server_default='0'),
    )
    op.create_index('idx_websites_client', 'monitored_websites', ['client_id'])
    op.create_index('idx_websites_status', 'monitored_websites', ['status'], postgresql_where=sa.text("status = 'active'"))
    op.create_index('idx_websites_next_crawl', 'monitored_websites', ['last_successful_crawl_at', 'crawl_frequency_minutes'])

    # Create products table
    op.create_table(
        'products',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('website_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('monitored_websites.id', ondelete='CASCADE'), nullable=False),
        sa.Column('original_url', sa.String(2048), nullable=False),
        sa.Column('normalized_url', sa.String(2048), nullable=False),
        sa.Column('extracted_product_id', sa.String(255), nullable=True),
        sa.Column('extraction_method', sa.Enum('url_pattern_amazon', 'url_pattern_shopify', 'url_pattern_generic', 'html_opengraph', 'html_schema', 'none', name='extraction_method'), nullable=False),
        sa.Column('product_name', sa.Text, nullable=False),
        sa.Column('current_price', sa.Numeric(12, 2), nullable=True),
        sa.Column('current_currency', sa.String(3), nullable=False, server_default='USD'),
        sa.Column('current_stock_status', sa.Enum('in_stock', 'out_of_stock', 'limited_availability', 'unknown', name='stock_status'), nullable=False),
        sa.Column('last_crawled_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.text('TRUE')),
        sa.Column('delisted_at', sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index('idx_products_website_normalized_url', 'products', ['website_id', 'normalized_url'], unique=True)
    op.create_index('idx_products_website_active', 'products', ['website_id'], postgresql_where=sa.text('is_active = TRUE'))
    op.create_index('idx_products_extracted_id', 'products', ['website_id', 'extracted_product_id'], postgresql_where=sa.text('extracted_product_id IS NOT NULL'))
    op.create_index('idx_products_last_crawled', 'products', ['last_crawled_at'])

    # Create product_history table (partitioned by month)
    op.execute("""
        CREATE TABLE product_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            website_id UUID NOT NULL REFERENCES monitored_websites(id) ON DELETE CASCADE,
            crawl_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
            price NUMERIC(12, 2),
            currency VARCHAR(3) NOT NULL,
            stock_status stock_status NOT NULL,
            price_changed BOOLEAN NOT NULL DEFAULT FALSE,
            stock_changed BOOLEAN NOT NULL DEFAULT FALSE,
            price_change_pct NUMERIC(6, 2),
            raw_crawl_data JSONB NOT NULL,
            crawl_log_id UUID NOT NULL
        ) PARTITION BY RANGE (crawl_timestamp)
    """)

    # Create initial partitions for current month and next 3 months
    op.execute("""
        CREATE TABLE product_history_2025_11 PARTITION OF product_history
        FOR VALUES FROM ('2025-11-01') TO ('2025-12-01')
    """)
    op.execute("""
        CREATE TABLE product_history_2025_12 PARTITION OF product_history
        FOR VALUES FROM ('2025-12-01') TO ('2026-01-01')
    """)
    op.execute("""
        CREATE TABLE product_history_2026_01 PARTITION OF product_history
        FOR VALUES FROM ('2026-01-01') TO ('2026-02-01')
    """)
    op.execute("""
        CREATE TABLE product_history_2026_02 PARTITION OF product_history
        FOR VALUES FROM ('2026-02-01') TO ('2026-03-01')
    """)

    # Create indexes on partitioned table
    op.create_index('idx_product_history_product_time', 'product_history', ['product_id', 'crawl_timestamp'], postgresql_ops={'crawl_timestamp': 'DESC'})
    op.create_index('idx_product_history_website_time', 'product_history', ['website_id', 'crawl_timestamp'], postgresql_ops={'crawl_timestamp': 'DESC'})
    op.create_index('idx_product_history_changes', 'product_history', ['product_id'], postgresql_where=sa.text('price_changed = TRUE OR stock_changed = TRUE'))
    op.execute("CREATE INDEX idx_product_history_raw_data ON product_history USING GIN(raw_crawl_data jsonb_path_ops)")

    # Create crawl_execution_logs table
    op.create_table(
        'crawl_execution_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('website_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('monitored_websites.id', ondelete='CASCADE'), nullable=False),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('completed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('status', sa.Enum('pending', 'running', 'success', 'partial_success', 'failed', name='crawl_status'), nullable=False),
        sa.Column('products_processed', sa.Integer, nullable=False, server_default='0'),
        sa.Column('changes_detected', sa.Integer, nullable=False, server_default='0'),
        sa.Column('errors_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('error_details', postgresql.JSONB, nullable=True),
        sa.Column('retry_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('triggered_by', sa.Enum('scheduled', 'manual', 'discovery', 'retry', name='crawl_trigger'), nullable=False),
        sa.Column('duration_seconds', sa.Integer, nullable=True),
    )
    op.create_index('idx_crawl_logs_website', 'crawl_execution_logs', ['website_id', 'started_at'], postgresql_ops={'started_at': 'DESC'})
    op.create_index('idx_crawl_logs_status', 'crawl_execution_logs', ['status', 'started_at'], postgresql_ops={'started_at': 'DESC'})
    op.create_index('idx_crawl_logs_errors', 'crawl_execution_logs', ['website_id'], postgresql_where=sa.text("status = 'failed'"))

    # Add FK constraint for crawl_log_id in product_history (after crawl_execution_logs table exists)
    op.execute("""
        ALTER TABLE product_history
        ADD CONSTRAINT fk_product_history_crawl_log
        FOREIGN KEY (crawl_log_id) REFERENCES crawl_execution_logs(id) ON DELETE CASCADE
    """)

    # Create webhook_delivery_logs table
    op.create_table(
        'webhook_delivery_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('product_history_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('website_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('monitored_websites.id', ondelete='CASCADE'), nullable=False),
        sa.Column('target_url', sa.String(2048), nullable=False),
        sa.Column('payload', postgresql.JSONB, nullable=False),
        sa.Column('signature', sa.String(128), nullable=False),
        sa.Column('timestamp_header', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('attempt_number', sa.Integer, nullable=False, server_default='1'),
        sa.Column('delivery_timestamp', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('http_status_code', sa.Integer, nullable=True),
        sa.Column('status', sa.Enum('pending', 'success', 'failed', 'retrying', 'exhausted', name='webhook_status'), nullable=False),
        sa.Column('response_body', sa.Text, nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('next_retry_at', sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index('idx_webhook_logs_website_status', 'webhook_delivery_logs', ['website_id', 'status', 'delivery_timestamp'], postgresql_ops={'delivery_timestamp': 'DESC'})
    op.create_index('idx_webhook_logs_retry', 'webhook_delivery_logs', ['next_retry_at'], postgresql_where=sa.text("status = 'retrying'"))
    op.create_index('idx_webhook_logs_product_history', 'webhook_delivery_logs', ['product_history_id'])

    # Create product_statistics table (aggregated data)
    op.create_table(
        'product_statistics',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('period_start', sa.Date, nullable=False),
        sa.Column('period_end', sa.Date, nullable=False),
        sa.Column('min_price', sa.Numeric(12, 2), nullable=True),
        sa.Column('max_price', sa.Numeric(12, 2), nullable=True),
        sa.Column('avg_price', sa.Numeric(12, 2), nullable=True),
        sa.Column('price_changes_count', sa.Integer, nullable=False),
        sa.Column('stock_out_days', sa.Integer, nullable=False),
        sa.Column('total_snapshots', sa.Integer, nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('idx_product_stats_product_period', 'product_statistics', ['product_id', 'period_start'], unique=True)
    op.create_index('idx_product_stats_period', 'product_statistics', ['period_start'], postgresql_ops={'period_start': 'DESC'})

    # Create materialized view for latest product state
    op.execute("""
        CREATE MATERIALIZED VIEW product_latest_state AS
        SELECT DISTINCT ON (product_id)
            product_id,
            price,
            stock_status,
            crawl_timestamp
        FROM product_history
        ORDER BY product_id, crawl_timestamp DESC
    """)
    op.create_index('idx_product_latest_state', 'product_latest_state', ['product_id'], unique=True)


def downgrade() -> None:
    # Drop materialized view
    op.execute("DROP MATERIALIZED VIEW IF EXISTS product_latest_state")

    # Drop tables in reverse order
    op.drop_table('product_statistics')
    op.drop_table('webhook_delivery_logs')
    op.drop_table('crawl_execution_logs')
    op.execute("DROP TABLE IF EXISTS product_history CASCADE")
    op.drop_table('products')
    op.drop_table('monitored_websites')
    op.drop_table('api_keys')
    op.drop_table('clients')

    # Drop ENUM types
    op.execute("DROP TYPE IF EXISTS crawl_trigger")
    op.execute("DROP TYPE IF EXISTS webhook_status")
    op.execute("DROP TYPE IF EXISTS crawl_status")
    op.execute("DROP TYPE IF EXISTS extraction_method")
    op.execute("DROP TYPE IF EXISTS stock_status")
    op.execute("DROP TYPE IF EXISTS website_status")
    op.execute("DROP TYPE IF EXISTS subscription_tier")
