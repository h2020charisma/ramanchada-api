"""Guard tests for the study-level uuid surfaced by /db/query.

Regression context
------------------
A search hit can be a study, not just a substance. To open that study in the
AMBIT viewer (jtoxkit-react's ``documentUuid`` prop -> ``{ambitUrl}study/{uuid}``)
the client needs the study's OWN identity, ``document_uuid_s`` — one protocol
application.

``get_query_fields()`` used to request only ``study_name``/``study_domain`` for
study docs, so ``parse_solr_response`` (which reads ``{type_s}_uuid``) never had
a ``study_uuid`` to surface and every study hit came back with no uuid at all.
The client could then only link to the parent substance.

The trap is ``s_uuid_s``: study docs carry it too, but it is the PARENT
substance copied onto the study, so aliasing it as ``study_uuid`` would send
every study back to the substance viewer while looking like it worked.

Deterministic — no network, no live Solr.
"""
from rcapi.services import solr_query
from rcapi.services.query_service import parse_solr_response


def test_study_uuid_is_the_document_uuid(monkeypatch):
    """A study's uuid alias must be document_uuid_s (its own protocol application)."""
    monkeypatch.setattr(solr_query.config, "SOLR_DOCS", ["study"], raising=False)
    fields = solr_query.get_query_fields()

    assert "study_uuid:document_uuid_s" in fields


def test_study_uuid_is_not_the_parent_substance(monkeypatch):
    """s_uuid_s is the parent substance — aliasing it as study_uuid hides the study."""
    monkeypatch.setattr(solr_query.config, "SOLR_DOCS", ["study"], raising=False)
    fields = solr_query.get_query_fields()

    assert "study_uuid:s_uuid_s" not in fields


def test_study_carries_its_parent_substance(monkeypatch):
    """The viewer opens a study inside its substance, so the parent ships too."""
    monkeypatch.setattr(solr_query.config, "SOLR_DOCS", ["study"], raising=False)
    fields = solr_query.get_query_fields()

    assert "study_substance:s_uuid_s" in fields


def test_no_study_uuid_when_studies_are_not_served(monkeypatch):
    """The alias is scoped to the study branch, not emitted unconditionally."""
    monkeypatch.setattr(solr_query.config, "SOLR_DOCS", ["chemical"], raising=False)
    fields = solr_query.get_query_fields()

    assert "study_uuid" not in fields


def test_parse_solr_response_surfaces_study_uuid():
    """The alias reaches the client as item['uuid'] — the contract a viewer consumes."""
    response_data = {
        "response": {
            "docs": [
                {
                    "id": "NNRG-sub/a/NNRG-assay",
                    "type_s": "study",
                    "study_name": "Crystalline phase",
                    "study_domain": "some text value",
                    "study_uuid": "NRCR-2253d10c-4fd7-a7cc-317f-97e7ef16b3d1",
                    "study_substance": "NNRG-a51b2e58-4105-9643-3016-3f4b431171e2",
                }
            ]
        }
    }

    items = parse_solr_response(response_data, base_url="http://localhost/")

    assert len(items) == 1
    assert items[0]["uuid"] == "NRCR-2253d10c-4fd7-a7cc-317f-97e7ef16b3d1"
    assert items[0]["substance_uuid"] == "NNRG-a51b2e58-4105-9643-3016-3f4b431171e2"
    assert items[0]["type"] == "study"


def test_parse_solr_response_omits_uuid_when_absent():
    """A doc without the alias must not grow an empty uuid key."""
    response_data = {
        "response": {
            "docs": [
                {"id": "x", "type_s": "study", "study_name": "n", "study_domain": "d"}
            ]
        }
    }

    items = parse_solr_response(response_data, base_url="http://localhost/")

    assert "uuid" not in items[0]
