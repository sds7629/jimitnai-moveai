-- platform-infra: extension bootstrap
-- Runs once, on first container startup, via postgres' docker-entrypoint-initdb.d
-- convention. File name prefix (001-) controls execution order relative to
-- 002-schema.sql / 003-seed-scenarios.sql / 004-permissions.sql.

CREATE EXTENSION IF NOT EXISTS vector;
