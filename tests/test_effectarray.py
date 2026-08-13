"""Tests for the dose-response EffectArray conversion.

Covers the shared converter ``convertor_service.to_effectarrays`` and the
``POST /dataset/convert?format=effectarray`` endpoint, which converts an AMBIT
``Substances`` payload into plottable arrays in-memory and streams JSON back (no
NeXus file, no background task).

The conversion itself is pyambit's ``ProtocolApplication.convert_effectrecords2array``;
these tests assert the authoritative behaviour we rely on for charting:
  * studies are keyed by ``document_uuid`` (= papp.uuid),
  * records split by the non-numeric conditions, so each ``Treatment`` value
    (exposure / positive control / negative control) becomes its own array,
  * ``CONCENTRATION`` conditions become the axis, results become the signal with
    SD error bars.
"""
import json
import os

from fastapi.testclient import TestClient
from pyambit.datamodel import Substances

from rcapi.main import app
from rcapi.services.convertor_service import to_effectarrays

client = TestClient(app)

FIXTURE = os.path.join(
    os.path.dirname(__file__), "resources", "api", "dose_response_ambit.json"
)


def _load_substances():
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def _by_treatment(arrays):
    return {a["conditions"].get("Treatment"): a for a in arrays}


def test_to_effectarrays_splits_controls_and_builds_concentration_axis():
    subs = Substances(**_load_substances())
    out = to_effectarrays(subs)

    assert len(out) == 1
    study = out[0]
    assert study["document_uuid"] == "NNRG-doc-aaaa-bbbb-cccc-dddddddddddd"
    assert study["error"] is None

    arrays = study["arrays"]
    # one array per Treatment value: exposure + the two controls, each distinct
    by_t = _by_treatment(arrays)
    assert set(by_t) == {"exposure", "positive control", "negative control"}

    # the dosed series carries the concentration axis and the response signal + SD
    exposure = by_t["exposure"]
    assert list(exposure["axes"].keys()) == ["CONCENTRATION"]
    conc = exposure["axes"]["CONCENTRATION"]
    assert conc["unit"] == "ug/mL"
    assert conc["values"] == [0.1, 1.0, 10.0, 100.0]

    sig = exposure["signal"]
    assert sig["unit"] == "%"
    assert sig["values"] == [98.0, 80.0, 55.0, 20.0]
    assert sig["errQualifier"] == "SD"
    assert sig["errorValue"] == [2.0, 3.0, 4.0, 5.0]

    # controls are their own single-point arrays (shown distinctly on the chart)
    assert by_t["positive control"]["signal"]["values"] == [8.0]
    assert by_t["negative control"]["signal"]["values"] == [100.0]


def test_dose_axis_is_bridged_to_concentration():
    # ECOTOX-style study whose dose axis is "DOSE" (not CONCENTRATION). The backend bridge
    # renames it so pyambit builds the curve; the resulting array must carry a CONCENTRATION axis.
    subs = Substances(**{
        "substance": [{
            "name": "DOSE-axis fixture",
            "study": [{
                "uuid": "NNRG-dose-1",
                "protocol": {"topcategory": "ECOTOX",
                             "category": {"code": "EC_ALGAETOX_SECTION", "title": "Algae"},
                             "endpoint": "FRESHWATER TOXICITY", "guideline": ["SOP"]},
                "citation": {"owner": "USP", "title": "ref", "year": "2016"},
                "effects": [
                    {"endpoint": "EC50", "result": {"loValue": 1.48, "unit": "mg/l"},
                     "conditions": {"DOSE": {"loValue": 0.1, "unit": "mg/l"}, "Treatment": "exposure"}},
                    {"endpoint": "EC50", "result": {"loValue": 43.0, "unit": "mg/l"},
                     "conditions": {"DOSE": {"loValue": 1.0, "unit": "mg/l"}, "Treatment": "exposure"}},
                    {"endpoint": "EC50", "result": {"loValue": 50.5, "unit": "mg/l"},
                     "conditions": {"DOSE": {"loValue": 10.0, "unit": "mg/l"}, "Treatment": "exposure"}},
                ],
            }],
        }],
    })
    out = to_effectarrays(subs)
    arrays = out[0]["arrays"]
    assert arrays, "expected at least one converted array"
    assert any("CONCENTRATION" in (a.get("axes") or {}) for a in arrays)


def test_convert_endpoint_effectarray_streams_json_no_file():
    resp = client.post(
        "/dataset/convert", params={"format": "effectarray"}, json=_load_substances()
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "datasets" in body
    datasets = body["datasets"]
    assert len(datasets) == 1
    assert datasets[0]["document_uuid"] == "NNRG-doc-aaaa-bbbb-cccc-dddddddddddd"
    # 3 arrays = exposure curve + 2 distinct controls
    assert len(datasets[0]["arrays"]) == 3
    treatments = {a["conditions"].get("Treatment") for a in datasets[0]["arrays"]}
    assert treatments == {"exposure", "positive control", "negative control"}
