-- Runs once, on first initialisation of an empty Postgres data volume.
--
-- Its only job is creating the separate test database. The `vector` extension is enabled by
-- the first Alembic migration instead, so it exists identically on a laptop, in CI, and on
-- Neon — anything configured only here would be a step someone has to remember in production.
--
-- Tests get their own database so a `DROP TABLE` in a test fixture can never touch the data
-- you were developing against.

CREATE DATABASE careergraph_test;
