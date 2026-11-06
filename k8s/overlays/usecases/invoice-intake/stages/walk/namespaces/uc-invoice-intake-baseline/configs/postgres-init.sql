-- postgres-init: six databases and their roles on the one server (decisions/data-store.yaml postgres_databases, postgres_roles,
-- postgres_connection_limits). Idempotent: safe to re-run, and re-run before a restore because pg_dump carries no roles or grants.
\set ON_ERROR_STOP on

SELECT format('CREATE ROLE %I', r)
FROM unnest(ARRAY['invoice_working', 'invoice_episodic', 'temporal', 'gotrue', 'litellm', 'backup_reader', 'tenant_probe']) AS r
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = r) \gexec

ALTER ROLE invoice_working  LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 10 PASSWORD :'invoice_working_pw';
ALTER ROLE invoice_episodic LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 10 PASSWORD :'invoice_episodic_pw';
ALTER ROLE temporal         LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 50 PASSWORD :'temporal_pw';
ALTER ROLE gotrue           LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 5  PASSWORD :'gotrue_pw';
ALTER ROLE litellm          LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 10 PASSWORD :'litellm_pw';
ALTER ROLE backup_reader    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 2  PASSWORD :'backup_reader_pw';
ALTER ROLE tenant_probe     LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 1  PASSWORD :'tenant_probe_pw';

GRANT pg_read_all_data TO backup_reader;

SELECT format('CREATE DATABASE %I OWNER %I', d, o)
FROM (VALUES
  ('invoice_working', 'invoice_working'),
  ('invoice_episodic', 'invoice_episodic'),
  ('temporal', 'temporal'),
  ('temporal_visibility', 'temporal'),
  ('gotrue_auth', 'gotrue'),
  ('litellm', 'litellm')
) AS t(d, o)
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = d) \gexec

-- A role boundary means nothing while PUBLIC keeps the default CONNECT.
REVOKE CONNECT, TEMPORARY ON DATABASE invoice_working, invoice_episodic, temporal, temporal_visibility, gotrue_auth, litellm FROM PUBLIC;
GRANT CONNECT ON DATABASE invoice_working TO invoice_working;
GRANT CONNECT ON DATABASE invoice_episodic TO invoice_episodic;
GRANT CONNECT ON DATABASE temporal, temporal_visibility TO temporal;
GRANT CONNECT ON DATABASE gotrue_auth TO gotrue;
GRANT CONNECT ON DATABASE litellm TO litellm;
GRANT CONNECT ON DATABASE invoice_working, invoice_episodic, temporal, temporal_visibility, gotrue_auth, litellm TO backup_reader;
GRANT CONNECT ON DATABASE postgres TO tenant_probe;

\connect invoice_working
CREATE SCHEMA IF NOT EXISTS invoice_intake AUTHORIZATION invoice_working;

\connect invoice_episodic
CREATE SCHEMA IF NOT EXISTS invoice_intake AUTHORIZATION invoice_episodic;
