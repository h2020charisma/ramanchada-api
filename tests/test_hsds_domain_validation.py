from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from rcapi.api import convertor, hsds_dataset
from rcapi.main import app
from rcapi.services import convertor_service
from rcapi.services.hsds_domain import (
    MAX_HSDS_DOMAIN_LENGTH,
    validate_hsds_file_domain,
)


client = TestClient(app)


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("/RRUF/example.nxs", "/RRUF/example.nxs"),
        (
            "/CHARISMA_STUDY_PEAK_FITTING/Figure3 (Neon)/S10.nxs",
            "/CHARISMA_STUDY_PEAK_FITTING/Figure3 (Neon)/S10.nxs",
        ),
        ("/RRUF/example.nxs#/entry/spectrum", "/RRUF/example.nxs"),
        (
            "/PROJECT/café\u00a050%_EtOH@[lab]:1?.nxs",
            "/PROJECT/café\u00a050%_EtOH@[lab]:1?.nxs",
        ),
        (
            "/PROJECT/ sample /50%_EtOH%ZZ.nxs",
            "/PROJECT/ sample /50%_EtOH%ZZ.nxs",
        ),
        (
            "/RRUF/example.nxs#/ endpoint 50% /café#raw",
            "/RRUF/example.nxs",
        ),
        (
            "/RRUF/example.nxs#/" + "x" * (MAX_HSDS_DOMAIN_LENGTH + 1),
            "/RRUF/example.nxs",
        ),
        (
            "/" + "a" * (MAX_HSDS_DOMAIN_LENGTH - 5) + ".nxs",
            "/" + "a" * (MAX_HSDS_DOMAIN_LENGTH - 5) + ".nxs",
        ),
    ],
)
def test_validate_hsds_file_domain_accepts_product_paths(reference, expected):
    assert validate_hsds_file_domain(reference) == expected


@pytest.mark.parametrize(
    "reference",
    [
        "",
        "RRUF/example.nxs",
        "//example.test/file.nxs",
        "http://example.test/file.nxs",
        "https://example.test/file.nxs",
        "HTTP://example.test/file.nxs",
        " http://example.test/file.nxs",
        "hdf5://RRUF/example.nxs",
        "http+unix://socket/file.nxs",
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
        "/" + "a" * MAX_HSDS_DOMAIN_LENGTH + ".nxs",
    ],
)
def test_validate_hsds_file_domain_rejects_ambiguous_paths(reference):
    with pytest.raises(ValueError, match="invalid HSDS domain"):
        validate_hsds_file_domain(reference)


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


def test_download_passes_only_file_domain_to_h5pyd(monkeypatch):
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
        "/PROJECT/café 50%_EtOH.nxs",
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


def test_legacy_reader_preserves_chaold_suffix(monkeypatch):
    remote_file = Mock()
    remote_file.__enter__ = Mock(return_value=Mock())
    remote_file.__exit__ = Mock(return_value=False)
    open_file = Mock(return_value=remote_file)
    monkeypatch.setattr(hsds_dataset.h5pyd, "File", open_file)
    monkeypatch.setattr(
        hsds_dataset,
        "get_file_annotations",
        Mock(return_value=(None, None)),
    )

    result = {"annotation": [], "datasets": []}
    assert hsds_dataset.read_cha(
        "/legacy/café 50%_EtOH.chaold#/ignored",
        result,
    ) == result
    open_file.assert_called_once_with(
        "/legacy/café 50%_EtOH.chaold",
        api_key=None,
    )


def test_unused_knnquery_rejects_invalid_domain_before_h5pyd(monkeypatch):
    open_file = Mock(side_effect=AssertionError("h5pyd.File must not be called"))
    monkeypatch.setattr(convertor_service.h5pyd, "File", open_file)

    with pytest.raises(ValueError, match="invalid HSDS domain"):
        convertor_service.knnquery("https://example.test/file.nxs")

    open_file.assert_not_called()
