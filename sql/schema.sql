-- Multi-Region IAM Demo Schema
-- This schema demonstrates CockroachDB's multi-region capabilities with an IAM use case

DROP DATABASE IF EXISTS iam_demo CASCADE;
CREATE DATABASE iam_demo;

-- Configure multi-region database
-- These regions should match your CockroachDB cluster configuration
-- Update these to match your actual cluster regions
ALTER DATABASE iam_demo SET PRIMARY REGION = "aws-us-east-1";
\set errexit=false
ALTER DATABASE iam_demo ADD REGION "aws-us-east-2";
ALTER DATABASE iam_demo ADD REGION "aws-us-west-2";
\set errexit=true

-- Set survival goal to survive a region failure
ALTER DATABASE iam_demo SURVIVE REGION FAILURE;

USE iam_demo;

-- =============================================================================
-- GLOBAL TABLES - Fast reads everywhere, slower writes (consensus required)
-- =============================================================================

-- Users table - stores user account information
-- GLOBAL because user data needs to be readable quickly from any region
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username STRING NOT NULL UNIQUE,
    email STRING NOT NULL,
    password_hash STRING NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    last_login TIMESTAMPTZ,
    status STRING DEFAULT 'active',
    INDEX users_username_idx (username),
    INDEX users_email_idx (email)
) LOCALITY GLOBAL;

-- Roles table - stores role definitions and permissions
-- GLOBAL because roles/permissions need to be consistent across all regions
CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_name STRING NOT NULL UNIQUE,
    description STRING,
    permissions JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    INDEX roles_name_idx (role_name)
) LOCALITY GLOBAL;

-- User roles mapping - associates users with roles
-- GLOBAL for fast permission checks from any region
CREATE TABLE user_roles (
    user_id UUID NOT NULL,
    role_id UUID NOT NULL,
    assigned_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, role_id),
    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_role FOREIGN KEY (role_id) REFERENCES roles (id) ON DELETE CASCADE
) LOCALITY GLOBAL;

-- User behavior profiles - stores learned behavior patterns as vectors
-- GLOBAL because user profiles need to be accessible from any region for anomaly detection
-- Vector dimensions (8D):
--   1. Hour of day (0-1)
--   2. Day of week (0-1)
--   3. Region consistency (0-1)
--   4. Time since last login (log-scaled, 0-1)
--   5. Session duration pattern (0-1)
--   6. Login frequency (0-1)
--   7. Recent failure rate (0-1)
--   8. Activity level (0-1)
CREATE TABLE user_behavior_profiles (
    user_id UUID PRIMARY KEY,
    behavior_vector VECTOR(8) NOT NULL,
    profile_type STRING DEFAULT 'static', -- 'static' or 'learned'
    sample_count INT DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT fk_profile_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) LOCALITY GLOBAL;

-- Create vector index for fast similarity search
CREATE INDEX user_behavior_vector_idx ON user_behavior_profiles
    USING HNSW (behavior_vector vector_cosine_ops);

-- Alternative index syntax (if above doesn't work):
-- CREATE INDEX user_behavior_vector_idx ON user_behavior_profiles
--     USING HNSW (behavior_vector) WITH (distance='cosine');

-- =============================================================================
-- REGIONAL TABLES - Fast reads/writes in primary region
-- =============================================================================

-- Sessions table - tracks active user sessions
-- REGIONAL because sessions are typically managed in one region
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    region STRING NOT NULL,
    login_time TIMESTAMPTZ NOT NULL,
    logout_time TIMESTAMPTZ,
    status STRING DEFAULT 'active',
    ip_address STRING,
    user_agent STRING,
    INDEX sessions_user_idx (user_id),
    INDEX sessions_status_idx (status),
    CONSTRAINT fk_session_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) LOCALITY REGIONAL BY TABLE IN PRIMARY REGION;

-- =============================================================================
-- REGIONAL BY ROW TABLES - Each row stored in its home region
-- =============================================================================

-- Audit logs table - tracks all user actions
-- REGIONAL BY ROW so each region's audit logs stay local for fast writes
-- CockroachDB automatically adds crdb_region column
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    session_id UUID,
    action STRING NOT NULL,
    resource STRING,
    result STRING DEFAULT 'success',
    timestamp TIMESTAMPTZ DEFAULT now(),
    metadata JSONB,
    INDEX audit_user_idx (user_id),
    INDEX audit_session_idx (session_id),
    INDEX audit_timestamp_idx (timestamp)
) LOCALITY REGIONAL BY ROW;

-- Login anomalies table - tracks detected anomalous login behavior
-- REGIONAL BY ROW so each region's anomaly data stays local
-- CockroachDB automatically adds crdb_region column
CREATE TABLE login_anomalies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    session_id UUID NOT NULL,
    anomaly_score FLOAT NOT NULL,
    current_vector VECTOR(8),
    profile_vector VECTOR(8),
    detected_at TIMESTAMPTZ DEFAULT now(),
    anomaly_details JSONB,
    INDEX anomaly_user_idx (user_id),
    INDEX anomaly_score_idx (anomaly_score),
    INDEX anomaly_timestamp_idx (detected_at),
    CONSTRAINT fk_anomaly_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_anomaly_session FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
) LOCALITY REGIONAL BY ROW;
