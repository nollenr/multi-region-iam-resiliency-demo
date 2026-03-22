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
