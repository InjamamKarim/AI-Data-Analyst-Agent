-- Second layer under the SQL keyword guard.
-- Replace the password before running. The application user must not own the tables.
CREATE USER readonly_user WITH PASSWORD 'change-me';
GRANT CONNECT ON DATABASE analytics TO readonly_user;
GRANT USAGE ON SCHEMA public TO readonly_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO readonly_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;
REVOKE CREATE ON SCHEMA public FROM readonly_user;
