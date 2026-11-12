-- Local/dev bootstrap. Runs once when the Postgres container is first created.
-- app    = schema owner, used only for migrations
-- gc_app = runtime role used by the API; NOT an owner, NO BYPASSRLS, so Row-Level Security applies.
CREATE ROLE gc_app LOGIN PASSWORD 'gc_app' NOSUPERUSER NOBYPASSRLS;
CREATE EXTENSION IF NOT EXISTS vector;
