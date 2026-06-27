"""Guard tests for SOLR_DOCS <-> served-collection consistency.

Regression context
------------------
Every ``/db/query`` result is filtered by ``type_s`` via
``solr_query.solr_doc_filter()``, which is built from ``config.SOLR_DOCS``.
``/db/download`` (solr2json) does NOT apply that filter.

If a config serves a collection whose documents carry a ``type_s`` that is
missing from ``SOLR_DOCS``, those documents become invisible to ``/db/query``
(``numFound:0``) even though they exist in Solr and ``/db/download`` still
returns them. This silently broke the prediction viewer when ``prediction``
was dropped from ``SOLR_DOCS`` while the ``vega`` collection was still served:
the viewer resolves chemical -> prediction items through ``/db/query`` and got
nothing back.

These tests are deterministic and need no network or live Solr.
"""
import glob
import os

import pytest

from rcapi.config.app_config import AppConfig

CONFIG_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "src", "configs")
)

# A served collection implies the ``type_s`` its documents carry. If a config
# lists the collection under SOLR_COLLECTIONS, SOLR_DOCS must allow that type,
# otherwise /db/query hides every document in it.
COLLECTION_REQUIRED_DOCS = {
    "vega": "prediction",   # VEGA QSAR predictions -> type_s:prediction
    "dsstox": "chemical",   # DSSTox chemicals      -> type_s:chemical
}


def _shipped_config_files():
    return sorted(glob.glob(os.path.join(CONFIG_DIR, "config*.yaml")))


@pytest.mark.parametrize(
    "config_path", _shipped_config_files(), ids=os.path.basename
)
def test_solr_docs_cover_served_collections(config_path):
    """Each shipped config must list the doc type for every collection it serves."""
    config = AppConfig.from_yaml(config_path)
    served = {c.name for c in config.SOLR_COLLECTIONS.collections}
    docs = set(config.SOLR_DOCS)

    for collection, required_type in COLLECTION_REQUIRED_DOCS.items():
        if collection in served:
            assert required_type in docs, (
                f"{os.path.basename(config_path)} serves the '{collection}' "
                f"collection but SOLR_DOCS is missing '{required_type}'. "
                f"/db/query would filter out all '{required_type}' documents "
                f"(numFound:0) while /db/download still returns them."
            )


def test_solr_doc_filter_emits_each_configured_type(monkeypatch):
    """solr_doc_filter() must turn SOLR_DOCS into an inclusive type_s clause."""
    from rcapi.services import solr_query

    monkeypatch.setattr(
        solr_query.config, "SOLR_DOCS", ["prediction", "chemical"], raising=False
    )
    assert solr_query.solr_doc_filter() == 'type_s:("prediction" OR "chemical")'


def test_solr_doc_filter_defaults_to_study_when_empty(monkeypatch):
    """An empty SOLR_DOCS falls back to study (never an empty type_s clause)."""
    from rcapi.services import solr_query

    monkeypatch.setattr(solr_query.config, "SOLR_DOCS", [], raising=False)
    assert solr_query.solr_doc_filter() == 'type_s:("study")'
