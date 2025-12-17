-- =============================================================================
-- Demo Service - Cloud SQL Schema
-- =============================================================================
-- Database: demodb (PostgreSQL 15)
-- Schema: configurable via :schema_name psql variable
--
-- This script creates all required tables and functions for the demo-service
-- to work with Clerk authentication.
--
-- Usage:
--   1. Connect to Cloud SQL:
--      gcloud sql connect demo-db --user=demo_user --database=demodb
--
--   2. Run this script with default schema (test):
--      \i /path/to/schema-cloud-sql.sql
--
--   3. Run with custom schema name:
--      psql -v schema_name='production' -f schema-cloud-sql.sql
--
--   Or via psql command line:
--      PGPASSWORD=xxx psql -h /cloudsql/PROJECT:REGION:INSTANCE -U demo_user -d demodb \
--        -v schema_name='test' -f schema-cloud-sql.sql
--
-- Author: Odiseo Team
-- Updated: 2025-12-17
-- =============================================================================

-- =============================================================================
-- SCHEMA CONFIGURATION
-- =============================================================================
-- Set default schema name if not provided via -v schema_name='xxx'
-- This can be overridden by passing -v schema_name='your_schema' to psql
\set ON_ERROR_STOP on

-- Default schema name (matches SCHEMA_NAME in env.production for Cloud SQL)
-- Override with: psql -v schema_name='production' -f schema-cloud-sql.sql
\if :{?schema_name}
  -- schema_name was provided via command line
\else
  \set schema_name 'test'
\endif

\echo 'Using schema:' :schema_name

-- Create schema if not exists
CREATE SCHEMA IF NOT EXISTS :schema_name;

-- Set search path
SET search_path TO :schema_name, public;

-- =============================================================================
-- EXTENSIONS
-- =============================================================================
-- Enable required extensions (must be done as superuser or via Cloud SQL console)
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- TABLE: demo_users
-- =============================================================================
-- Main users table with Clerk integration fields
-- Supports multiple auth providers: email, google, apple, facebook, github, clerk

CREATE TABLE IF NOT EXISTS :schema_name.demo_users (
    id SERIAL PRIMARY KEY,
    email CITEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    display_name TEXT,
    auth_provider VARCHAR(50) NOT NULL DEFAULT 'email',
    oauth_provider_id TEXT,
    password_hash TEXT,
    is_email_verified BOOLEAN NOT NULL DEFAULT false,
    email_verified_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT false,
    is_suspended BOOLEAN NOT NULL DEFAULT false,
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    suspended_at TIMESTAMPTZ,
    suspended_reason TEXT,
    deleted_at TIMESTAMPTZ,
    preferred_language VARCHAR(10) DEFAULT 'en',
    timezone VARCHAR(100) DEFAULT 'UTC',
    registration_source VARCHAR(50) DEFAULT 'web',
    registration_ip INET,
    last_login_at TIMESTAMPTZ,
    last_login_ip INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Clerk-specific fields
    clerk_user_id VARCHAR(255) UNIQUE,
    clerk_session_id VARCHAR(255),
    clerk_metadata JSONB,
    last_clerk_sync_at TIMESTAMPTZ,

    -- Migration fields (for transitioning legacy users to Clerk)
    migration_status VARCHAR(50) DEFAULT 'pending',
    force_clerk_migration BOOLEAN DEFAULT true,
    migration_completed_at TIMESTAMPTZ,
    migration_error TEXT,

    -- Constraints
    CONSTRAINT chk_auth_provider CHECK (
        auth_provider IN ('email', 'google', 'apple', 'facebook', 'github', 'clerk')
    ),
    CONSTRAINT chk_preferred_language CHECK (
        preferred_language IN ('es', 'en', 'fr', 'de', 'it', 'pt', 'ar')
    ),
    CONSTRAINT chk_migration_status CHECK (
        migration_status IN ('pending', 'in_progress', 'completed', 'failed', 'skipped')
    )
);

-- Indexes for demo_users
CREATE INDEX IF NOT EXISTS idx_demo_users_email ON :schema_name.demo_users(LOWER(email::TEXT));
CREATE INDEX IF NOT EXISTS idx_demo_users_clerk_id ON :schema_name.demo_users(clerk_user_id) WHERE clerk_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_demo_users_clerk_session ON :schema_name.demo_users(clerk_session_id) WHERE clerk_session_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_demo_users_active ON :schema_name.demo_users(is_active, is_deleted) WHERE is_active = true AND is_deleted = false;

-- =============================================================================
-- TABLE: demo_usage
-- =============================================================================
-- Token bucket tracking for rate limiting (5000 tokens/day per user)

CREATE TABLE IF NOT EXISTS :schema_name.demo_usage (
    id BIGSERIAL PRIMARY KEY,
    user_key VARCHAR(255) NOT NULL UNIQUE,
    tokens_consumed INTEGER NOT NULL DEFAULT 0,
    requests_count INTEGER NOT NULL DEFAULT 0,
    last_reset TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_blocked BOOLEAN NOT NULL DEFAULT false,
    blocked_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_timezone VARCHAR(50) DEFAULT 'UTC',

    -- Constraints
    CONSTRAINT chk_demo_tokens_range CHECK (tokens_consumed >= 0 AND tokens_consumed <= 100000),
    CONSTRAINT chk_demo_requests_range CHECK (requests_count >= 0)
);

-- Indexes for demo_usage
CREATE INDEX IF NOT EXISTS idx_demo_usage_user_key ON :schema_name.demo_usage(user_key);
CREATE INDEX IF NOT EXISTS idx_demo_usage_blocked_until ON :schema_name.demo_usage(blocked_until) WHERE is_blocked = true;

-- =============================================================================
-- TABLE: demo_audit_log
-- =============================================================================
-- Audit trail for all demo requests (security and compliance)

CREATE TABLE IF NOT EXISTS :schema_name.demo_audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_key VARCHAR(255),
    ip_address INET,
    client_fingerprint VARCHAR(255),
    request_input TEXT,
    response_length INTEGER,
    tokens_used INTEGER,
    is_blocked BOOLEAN NOT NULL DEFAULT false,
    block_reason VARCHAR(255),
    abuse_score DOUBLE PRECISION DEFAULT 0.0,
    action_taken VARCHAR(50) NOT NULL DEFAULT 'allowed',
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT chk_demo_audit_tokens CHECK (tokens_used >= 0 OR tokens_used IS NULL),
    CONSTRAINT chk_demo_audit_response_length CHECK (response_length >= 0 OR response_length IS NULL),
    CONSTRAINT chk_demo_audit_abuse_score CHECK (abuse_score >= 0.0 AND abuse_score <= 1.0),
    CONSTRAINT chk_demo_audit_action CHECK (
        action_taken IN ('allowed', 'captcha_required', 'rate_limited', 'blocked', 'logged_only')
    )
);

-- Indexes for demo_audit_log
CREATE INDEX IF NOT EXISTS idx_demo_audit_log_user_key ON :schema_name.demo_audit_log(user_key, created_at DESC) WHERE user_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_demo_audit_log_timestamp ON :schema_name.demo_audit_log(created_at DESC);

-- =============================================================================
-- TABLE: conversation_sessions
-- =============================================================================
-- Chat sessions for conversation history

CREATE TABLE IF NOT EXISTS :schema_name.conversation_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_email VARCHAR(255),
    session_id VARCHAR(255) NOT NULL UNIQUE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    current_agent VARCHAR(50),
    metadata JSONB DEFAULT '{}',
    archived BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT chk_current_agent CHECK (
        current_agent IS NULL OR current_agent IN ('sales', 'booking', 'general')
    )
);

-- Indexes for conversation_sessions
CREATE INDEX IF NOT EXISTS idx_conv_sessions_session_id ON :schema_name.conversation_sessions(session_id);
CREATE INDEX IF NOT EXISTS idx_conv_sessions_customer_email ON :schema_name.conversation_sessions(customer_email) WHERE customer_email IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_conv_sessions_last_activity ON :schema_name.conversation_sessions(last_activity_at DESC);

-- =============================================================================
-- TABLE: conversation_messages
-- =============================================================================
-- Individual chat messages within sessions

CREATE TABLE IF NOT EXISTS :schema_name.conversation_messages (
    id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES :schema_name.conversation_sessions(id) ON DELETE CASCADE,
    user_id INTEGER,
    role VARCHAR(20) NOT NULL,
    agent_name VARCHAR(50),
    intent VARCHAR(50),
    message_text TEXT NOT NULL,
    tool_calls JSONB,
    response_time_ms INTEGER,
    token_count INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT chk_message_role CHECK (role IN ('user', 'model')),
    CONSTRAINT chk_message_intent CHECK (
        intent IS NULL OR intent IN ('sales', 'booking', 'general')
    )
);

-- Indexes for conversation_messages
CREATE INDEX IF NOT EXISTS idx_conv_messages_session_id ON :schema_name.conversation_messages(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conv_messages_role ON :schema_name.conversation_messages(role);
CREATE INDEX IF NOT EXISTS idx_conv_messages_user_created ON :schema_name.conversation_messages(user_id, created_at DESC) WHERE user_id IS NOT NULL;

-- =============================================================================
-- FUNCTIONS: Trigger Functions
-- =============================================================================
-- NOTE: Functions are created in the schema but reference tables with explicit
-- schema prefix. This ensures they work correctly regardless of search_path.

-- Update timestamp function for demo_users
CREATE OR REPLACE FUNCTION :schema_name.update_demo_users_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Update timestamp function for conversation_sessions
CREATE OR REPLACE FUNCTION :schema_name.update_memory_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- FUNCTIONS: Clerk User Management
-- =============================================================================
-- IMPORTANT: These functions use dynamic SQL with current_schema() to resolve
-- table names at runtime. This allows them to work with any schema name.

-- JIT (Just-In-Time) user provisioning from Clerk
-- NOTE: This function uses explicit schema reference via set search_path
CREATE OR REPLACE FUNCTION :schema_name.upsert_clerk_user(
    p_clerk_user_id VARCHAR(255),
    p_email CITEXT,
    p_full_name TEXT,
    p_clerk_metadata JSONB,
    p_clerk_session_id VARCHAR(255) DEFAULT NULL
)
RETURNS TABLE(user_id INTEGER, is_new_user BOOLEAN, user_email CITEXT)
LANGUAGE plpgsql
AS $$
DECLARE
    v_user_id INTEGER;
    v_is_new BOOLEAN;
    v_schema_name TEXT;
BEGIN
    -- Get the schema this function belongs to
    v_schema_name := (SELECT nspname FROM pg_namespace WHERE oid = (
        SELECT pronamespace FROM pg_proc WHERE proname = 'upsert_clerk_user'
        AND pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = current_schema())
    ));

    -- Fallback to current_schema if not found
    IF v_schema_name IS NULL THEN
        v_schema_name := current_schema();
    END IF;

    -- Try to find existing user by Clerk ID
    EXECUTE format('SELECT id FROM %I.demo_users WHERE clerk_user_id = $1', v_schema_name)
    INTO v_user_id
    USING p_clerk_user_id;

    IF v_user_id IS NOT NULL THEN
        -- Update existing Clerk user
        EXECUTE format('
            UPDATE %I.demo_users
            SET
                full_name = $1,
                clerk_metadata = $2,
                clerk_session_id = COALESCE($3, clerk_session_id),
                last_clerk_sync_at = NOW(),
                last_login_at = NOW(),
                updated_at = NOW()
            WHERE id = $4
        ', v_schema_name)
        USING p_full_name, p_clerk_metadata, p_clerk_session_id, v_user_id;

        v_is_new := false;
    ELSE
        -- Check if user exists by email (legacy user migrating)
        EXECUTE format('SELECT id FROM %I.demo_users WHERE email = $1', v_schema_name)
        INTO v_user_id
        USING p_email;

        IF v_user_id IS NOT NULL THEN
            -- Link Clerk ID to existing user (migration)
            EXECUTE format('
                UPDATE %I.demo_users
                SET
                    clerk_user_id = $1,
                    clerk_metadata = $2,
                    clerk_session_id = $3,
                    auth_provider = ''clerk'',
                    is_email_verified = true,
                    is_active = true,
                    migration_status = ''completed'',
                    migration_completed_at = NOW(),
                    last_clerk_sync_at = NOW(),
                    last_login_at = NOW(),
                    updated_at = NOW()
                WHERE id = $4
            ', v_schema_name)
            USING p_clerk_user_id, p_clerk_metadata, p_clerk_session_id, v_user_id;

            v_is_new := false;
        ELSE
            -- Create new Clerk user
            EXECUTE format('
                INSERT INTO %I.demo_users (
                    email,
                    full_name,
                    auth_provider,
                    clerk_user_id,
                    clerk_metadata,
                    clerk_session_id,
                    is_email_verified,
                    is_active,
                    migration_status,
                    migration_completed_at,
                    last_clerk_sync_at,
                    last_login_at,
                    registration_source,
                    created_at,
                    updated_at
                ) VALUES (
                    $1, $2, ''clerk'', $3, $4, $5,
                    true, true, ''completed'', NOW(), NOW(), NOW(),
                    ''clerk_oauth'', NOW(), NOW()
                )
                RETURNING id
            ', v_schema_name)
            INTO v_user_id
            USING p_email, p_full_name, p_clerk_user_id, p_clerk_metadata, p_clerk_session_id;

            v_is_new := true;
        END IF;
    END IF;

    -- Return user info
    RETURN QUERY
    SELECT v_user_id, v_is_new, p_email;
END;
$$;

-- Update Clerk session ID
CREATE OR REPLACE FUNCTION :schema_name.update_clerk_session(
    p_clerk_user_id VARCHAR(255),
    p_session_id VARCHAR(255)
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_updated INTEGER;
    v_schema_name TEXT := current_schema();
BEGIN
    EXECUTE format('
        UPDATE %I.demo_users
        SET
            clerk_session_id = $1,
            last_login_at = NOW(),
            updated_at = NOW()
        WHERE clerk_user_id = $2
    ', v_schema_name)
    USING p_session_id, p_clerk_user_id;

    GET DIAGNOSTICS v_updated = ROW_COUNT;

    RETURN (v_updated > 0);
END;
$$;

-- Soft delete user (idempotent)
CREATE OR REPLACE FUNCTION :schema_name.soft_delete_clerk_user(
    p_clerk_user_id VARCHAR(255)
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_user_exists BOOLEAN;
    v_schema_name TEXT := current_schema();
BEGIN
    -- Check if user exists
    EXECUTE format('
        SELECT EXISTS(
            SELECT 1 FROM %I.demo_users
            WHERE clerk_user_id = $1
        )
    ', v_schema_name)
    INTO v_user_exists
    USING p_clerk_user_id;

    -- Return false if user doesn't exist
    IF NOT v_user_exists THEN
        RETURN false;
    END IF;

    -- Update user to soft delete (idempotent)
    EXECUTE format('
        UPDATE %I.demo_users
        SET
            is_deleted = true,
            is_active = false,
            deleted_at = COALESCE(deleted_at, NOW()),
            updated_at = NOW()
        WHERE clerk_user_id = $1
        AND is_deleted = false
    ', v_schema_name)
    USING p_clerk_user_id;

    -- Return true if user exists
    RETURN true;
END;
$$;

-- Update session activity when new message is inserted
-- IMPORTANT: Uses current_schema() for Cloud SQL compatibility
CREATE OR REPLACE FUNCTION :schema_name.update_session_activity()
RETURNS TRIGGER AS $$
DECLARE
    v_schema_name TEXT := current_schema();
BEGIN
    EXECUTE format('
        UPDATE %I.conversation_sessions
        SET last_activity_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = $1
    ', v_schema_name)
    USING NEW.session_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- TRIGGERS
-- =============================================================================

-- Drop existing triggers if they exist
DROP TRIGGER IF EXISTS trg_demo_users_updated_at ON :schema_name.demo_users;
DROP TRIGGER IF EXISTS trg_update_conv_sessions_timestamp ON :schema_name.conversation_sessions;
DROP TRIGGER IF EXISTS trg_update_session_activity ON :schema_name.conversation_messages;

-- Create triggers
CREATE TRIGGER trg_demo_users_updated_at
    BEFORE UPDATE ON :schema_name.demo_users
    FOR EACH ROW
    EXECUTE FUNCTION :schema_name.update_demo_users_updated_at();

CREATE TRIGGER trg_update_conv_sessions_timestamp
    BEFORE UPDATE ON :schema_name.conversation_sessions
    FOR EACH ROW
    EXECUTE FUNCTION :schema_name.update_memory_timestamp();

CREATE TRIGGER trg_update_session_activity
    AFTER INSERT ON :schema_name.conversation_messages
    FOR EACH ROW
    EXECUTE FUNCTION :schema_name.update_session_activity();

-- =============================================================================
-- GRANT PERMISSIONS
-- =============================================================================
-- Grant permissions to the demo_user

GRANT USAGE ON SCHEMA :schema_name TO demo_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA :schema_name TO demo_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA :schema_name TO demo_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA :schema_name TO demo_user;

-- Grant permissions for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA :schema_name GRANT ALL PRIVILEGES ON TABLES TO demo_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA :schema_name GRANT ALL PRIVILEGES ON SEQUENCES TO demo_user;

-- =============================================================================
-- VERIFICATION
-- =============================================================================
-- Verify all tables were created
SELECT
    table_name,
    (SELECT COUNT(*) FROM information_schema.columns c WHERE c.table_schema = :'schema_name' AND c.table_name = t.table_name) as column_count
FROM information_schema.tables t
WHERE table_schema = :'schema_name' AND table_type = 'BASE TABLE'
ORDER BY table_name;

-- Verify all functions were created
SELECT routine_name, routine_type
FROM information_schema.routines
WHERE routine_schema = :'schema_name'
ORDER BY routine_name;

\echo 'Schema' :schema_name 'created successfully!'

-- =============================================================================
-- END OF SCHEMA
-- =============================================================================
