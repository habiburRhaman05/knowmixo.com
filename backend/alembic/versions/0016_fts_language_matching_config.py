"""Fix FTS query/index text-search-config mismatch (D3.4 correctness fix).

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-26

migration 0015 mapped chunks.language (ISO 639-1) to a Postgres text
search config ('en' -> 'english', etc.) ONLY inside the chunks_tsvector_update
trigger that builds the STORED tsvector. The hybrid retrieval query
(app/chat/rag_v2/stages/retrieve.py, D3.4) queried that stored,
per-language-stemmed tsvector with a hardcoded `plainto_tsquery('simple',
...)` on the query side. Since 'english' config stems words ("policy" ->
"polici") and 'simple' does not, the two sides' lexemes frequently never
overlap -- `tsvector @@ tsquery` silently returns zero matches for very
ordinary English queries. Caught by
test/api/test_hybrid_retrieval.py::test_fts_matches_contribute_even_with_a_neutral_query_vector
before this ever reached a real chat request.

Fix: extract the ISO-to-regconfig mapping into one SQL function so both
the trigger (storage side) and the retrieval query (query side) use the
IDENTICAL config per chunk -- no second, divergent copy of the mapping.
"""
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

_MAPPING_FUNCTION = """
CREATE OR REPLACE FUNCTION chunks_language_to_tsconfig(lang text) RETURNS regconfig AS $$
  SELECT CASE lang
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
  END::regconfig
$$ LANGUAGE sql IMMUTABLE
"""

_NEW_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION chunks_tsvector_update() RETURNS trigger AS $$
DECLARE
  config regconfig;
BEGIN
  config := chunks_language_to_tsconfig(NEW.language);
  NEW.tsvector :=
    setweight(to_tsvector(config, COALESCE(NEW.heading, '')), 'A')
    || setweight(to_tsvector(config, COALESCE(NEW.text, '')), 'B');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""

_OLD_TRIGGER_FUNCTION = """
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
    op.execute(_MAPPING_FUNCTION)
    op.execute(_NEW_TRIGGER_FUNCTION)


def downgrade() -> None:
    op.execute(_OLD_TRIGGER_FUNCTION)
    op.execute("DROP FUNCTION IF EXISTS chunks_language_to_tsconfig(text)")
