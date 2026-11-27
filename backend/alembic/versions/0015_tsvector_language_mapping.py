"""Fix chunks_tsvector_update(): map ISO 639-1 codes to Postgres text
search configuration names (D3.3 regression fix).

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-26

Migration 0009's trigger did `COALESCE(NEW.language, 'simple')::regconfig`
-- casting `chunks.language` directly to a Postgres `regconfig`. That
silently worked only because `language` was never actually populated
before today (D3.3 is the first code to set it) and always fell through
to the 'simple' default. The rest of the app stores language as an ISO
639-1 code ("en", "es" -- see app/ingestion/language.py, the bot config
`language` field, Passage.language_hint in the RAG v2 spec), but Postgres
has no search configuration literally named "en"; it has "english". The
previous version of this migration would have failed on the very next
real ingestion with `UndefinedObject: text search configuration "en"
does not exist` -- caught here before it ever reached a live document.
"""
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

_OLD_FUNCTION = """
CREATE OR REPLACE FUNCTION chunks_tsvector_update() RETURNS trigger AS $$
BEGIN
  NEW.tsvector :=
    setweight(to_tsvector(COALESCE(NEW.language, 'simple')::regconfig,
                          COALESCE(NEW.heading, '')), 'A')
    || setweight(to_tsvector(COALESCE(NEW.language, 'simple')::regconfig,
                             COALESCE(NEW.text, '')), 'B');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""

_NEW_FUNCTION = """
CREATE OR REPLACE FUNCTION chunks_tsvector_update() RETURNS trigger AS $$
DECLARE
  config regconfig;
BEGIN
  config := CASE NEW.language
    WHEN 'ar' THEN 'arabic'   WHEN 'hy' THEN 'armenian'  WHEN 'eu' THEN 'basque'
    WHEN 'ca' THEN 'catalan'  WHEN 'da' THEN 'danish'    WHEN 'nl' THEN 'dutch'
    WHEN 'en' THEN 'english'  WHEN 'fi' THEN 'finnish'   WHEN 'fr' THEN 'french'
    WHEN 'de' THEN 'german'   WHEN 'el' THEN 'greek'     WHEN 'hi' THEN 'hindi'
    WHEN 'hu' THEN 'hungarian' WHEN 'id' THEN 'indonesian' WHEN 'ga' THEN 'irish'
    WHEN 'it' THEN 'italian'  WHEN 'lt' THEN 'lithuanian' WHEN 'ne' THEN 'nepali'
    WHEN 'no' THEN 'norwegian' WHEN 'pt' THEN 'portuguese' WHEN 'ro' THEN 'romanian'
    WHEN 'ru' THEN 'russian'  WHEN 'sr' THEN 'serbian'   WHEN 'es' THEN 'spanish'
    WHEN 'sv' THEN 'swedish'  WHEN 'ta' THEN 'tamil'     WHEN 'tr' THEN 'turkish'
    WHEN 'yi' THEN 'yiddish'
    ELSE 'simple'
  END::regconfig;

  NEW.tsvector :=
    setweight(to_tsvector(config, COALESCE(NEW.heading, '')), 'A')
    || setweight(to_tsvector(config, COALESCE(NEW.text, '')), 'B');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""


def upgrade() -> None:
    op.execute(_NEW_FUNCTION)


def downgrade() -> None:
    op.execute(_OLD_FUNCTION)
