from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from rcapi.api import convertor, hsds_dataset
from rcapi.main import app
from rcapi.services import convertor_service
from rcapi.services.hsds_endpoint import reject_hsds_endpoint_override


client = TestClient(app)


@pytest.mark.parametrize(
    "value",
    [
        "http://example.test/file.nxs",
        "https://user:password@example.test:8443/file.nxs?query#fragment",
        "HTTP://example.test/file.nxs",
        "hTtPs://example.test/file.nxs",
        "http+unix://%2Ftmp%2Fhsds.sock/file.nxs",
    ],
)
def test_reject_hsds_endpoint_override_rejects_endpoint_urls(value):
    with pytest.raises(ValueError, match="invalid HSDS domain"):
        reject_hsds_endpoint_override(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "/RRUF/example.nxs",
        "/RRUF/example.nxs#/entry/spectrum",
        "/PROJECT/café\u00a050%_EtOH@[lab]:1?.nxs",
        "RRUF/example.nxs",
        "//example.test/file.nxs",
        " http://example.test/file.nxs",
        "hdf5://RRUF/example.nxs",
        "ftp://example.test/file.nxs",
        "https%3A%2F%2Fexample.test%2Ffile.nxs",
        "/RRUF/./example.nxs",
        "/RRUF/../example.nxs",
        "/RRUF//example.nxs",
        "/RRUF/example.nxs/",
        "/RRUF\\example.nxs",
        "/RRUF/%2e%2e/example.nxs",
        "/RRUF/example.cha",
        "/RRUF/example.chaold",
        "/RRUF/example.NXS",
        "/RRUF/example\x00.nxs",
        "/" + "a" * 4096 + ".nxs",
    ],
)
def test_reject_hsds_endpoint_override_does_not_validate_other_values(value):
    assert reject_hsds_endpoint_override(value) is None


def test_download_rejects_invalid_domain_before_h5pyd(monkeypatch):
    open_file = Mock(side_effect=AssertionError("h5pyd.File must not be called"))
    monkeypatch.setattr(convertor.h5pyd, "File", open_file)

    response = client.get(
        "/db/download",
        params={"what": "h5", "domain": "https://example.test/file.nxs"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid HSDS domain"}
    open_file.assert_not_called()


def test_download_passes_non_endpoint_domain_to_h5pyd_unchanged(monkeypatch):
    remote_file = Mock()
    remote_file.__enter__ = Mock(return_value=Mock())
    remote_file.__exit__ = Mock(return_value=False)
    open_file = Mock(return_value=remote_file)
    monkeypatch.setattr(convertor.h5pyd, "File", open_file)
    monkeypatch.setattr(convertor, "recursive_copy", Mock())

    response = client.get(
        "/db/download",
        params={
            "what": "h5",
            "domain": "/PROJECT/café 50%_EtOH.nxs#/ endpoint 50% /signal#raw",
        },
    )

    assert response.status_code == 200
    open_file.assert_called_once_with(
        "/PROJECT/café 50%_EtOH.nxs#/ endpoint 50% /signal#raw",
        mode="r",
        api_key=None,
    )


def test_legacy_reader_rejects_invalid_domain_before_h5pyd(monkeypatch):
    open_file = Mock(side_effect=AssertionError("h5pyd.File must not be called"))
    monkeypatch.setattr(hsds_dataset.h5pyd, "File", open_file)

    with pytest.raises(ValueError, match="invalid HSDS domain"):
        hsds_dataset.read_cha(
            "https://example.test/file.nxs",
            {"annotation": [], "datasets": []},
        )

    open_file.assert_not_called()


def test_unused_knnquery_rejects_invalid_domain_before_h5pyd(monkeypatch):
    open_file = Mock(side_effect=AssertionError("h5pyd.File must not be called"))
    monkeypatch.setattr(convertor_service.h5pyd, "File", open_file)

    with pytest.raises(ValueError, match="invalid HSDS domain"):
        convertor_service.knnquery("https://example.test/file.nxs")

    open_file.assert_not_called()
