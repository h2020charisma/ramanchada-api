import pytest
from fastapi import HTTPException
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
    """An unserved source is refused, not quietly swapped for the default.

    Answering with the default collection returned another collection's data
    under the name the caller asked for, which is indistinguishable from that
    collection being empty.
    """
    with pytest.raises(HTTPException) as excinfo:
        settings.get_url(root, {"invalid"})
    assert excinfo.value.status_code == 403
    assert "invalid" in excinfo.value.detail


def test_private_data_source_without_token_asks_for_signin(settings):
    """A known-but-private source is a session problem: say so with 401."""
    with pytest.raises(HTTPException) as excinfo:
        settings.get_url(root, {"tox"}, drop_private=True)
    assert excinfo.value.status_code == 401
    assert "tox" in excinfo.value.detail


def test_anonymous_cannot_tell_private_from_nonexistent(settings):
    """No enumeration oracle: both answers must be identical to a stranger.

    If a private collection answered 401 while an unknown name answered 403,
    probing names would reveal which collections this deployment holds.
    """
    with pytest.raises(HTTPException) as private:
        settings.get_url(root, {"tox"}, drop_private=True)
    with pytest.raises(HTTPException) as unknown:
        settings.get_url(root, {"no-such-collection"}, drop_private=True)

    assert private.value.status_code == unknown.value.status_code == 401
    # Only the caller's own input differs; the wording must not
    assert private.value.detail.replace("tox", "X") == \
        unknown.value.detail.replace("no-such-collection", "X")


def test_private_data_source_with_token_is_served(settings):
    """With a token the same private source resolves normally."""
    url, coll, _ = settings.get_url(root, {"tox"}, drop_private=False)
    assert url == f"{root}/tox/select"
    assert coll == "tox"


def test_partially_valid_data_sources_still_serve_the_valid_ones(settings):
    """One unserved name among several does not fail the whole request."""
    url, coll, dropped = settings.get_url(root, {"charisma", "invalid"})
    assert url == f"{root}/charisma/select"
    assert coll == "charisma"
    assert dropped is True


def test_single_valid_data_source_default(settings):
    url, coll, _ = settings.get_url(root, {"charisma"})
    assert url == f"{root}/charisma/select"
    assert coll is "charisma"


def test_single_valid_data_source_non_default(settings):
    url, coll, _ = settings.get_url(root, {"chem"})
    assert url == f"{root}/chem/select"
    assert coll is "chem"


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