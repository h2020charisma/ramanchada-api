import pytest
from rcapi.config.app_config import SolrCollectionSettings, SolrCollectionEntry


@pytest.fixture
def settings():
    return SolrCollectionSettings(
        default="charisma",
        collections=[
            SolrCollectionEntry(name="charisma", description="Default collection", roles=["public"]),
            SolrCollectionEntry(name="chem", description="Chemistry collection", roles=["public"]),
            SolrCollectionEntry(name="tox", description="Toxicology collection", roles=["private"]),
        ]
    )


root = "http://localhost:8983/solr"


def test_no_data_source(settings):
    url, coll, dropped = settings.get_url(root, None)
    assert url == f"{root}/charisma/select"
    assert coll is None


def test_empty_data_source(settings):
    url, coll, dropped = settings.get_url(root, set())
    assert url == f"{root}/charisma/select"
    assert coll is None


def test_invalid_data_source(settings):
    url, coll, dropped = settings.get_url(root, {"invalid"})
    assert url == f"{root}/charisma/select"
    assert coll is None


def test_single_valid_data_source_default(settings):
    url, coll, _ = settings.get_url(root, {"charisma"})
    assert url == f"{root}/charisma/select"
    assert coll is None


def test_single_valid_data_source_non_default(settings):
    url, coll, _ = settings.get_url(root, {"chem"})
    assert url == f"{root}/chem/select"
    assert coll is None


def test_multiple_valid_with_default(settings):
    url, coll, _ = settings.get_url(root, {"charisma", "chem", "tox"})
    assert url == f"{root}/charisma/select"
    assert coll == "charisma,chem,tox"


def test_multiple_valid_without_default(settings):
    url, coll, _ = settings.get_url(root, {"chem", "tox"})
    assert url == f"{root}/chem/select"
    assert coll == "chem,tox"


def test_multiple_valid_with_drop(settings):
    url, coll, dropped = settings.get_url(
        root, {"charisma", "chem", "tox"}, True)
    assert url == f"{root}/charisma/select"
    assert coll == "charisma,chem"
    assert dropped