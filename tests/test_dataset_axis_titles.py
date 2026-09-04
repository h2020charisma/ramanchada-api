"""Tests for the axis titles ``/db/dataset`` serves alongside the dense
vectors.

``read_solr_study4dataset`` used to hardcode ``ytitle = "intensity [a.u.]"``
on both branches, which mislabelled every non-Raman vector (a dose-response
or calibration curve indexed into ``dense_a512``/``dense_b512`` is not an
intensity). The indexer now writes what it knows about the axes --
``unit_s``, ``x_name_s``, ``x_unit_s`` -- onto the same Solr document as the
vectors, so a plot is renderable without joining to the conditions child
document. These tests pin that:

  * a labelled document produces titles built from those fields,
  * a document carrying neither name nor unit produces an empty title
    (the frontend drops the label rather than showing a wrong one),
  * the ``SOLR_VECTOR`` branch, which really is a Raman spectrum resampled
    onto the fixed wavenumber grid, keeps its own correct titles.

Units are passed through exactly as indexed -- no LaTeX rewriting here.

No live Solr: ``read_solr_study4dataset`` is driven with a synthetic
response, and the follow-up parameters query it makes is stubbed out.
"""
import asyncio
from unittest.mock import patch

import pytest

from rcapi.api.hsds_dataset import axis_title, read_solr_study4dataset


DIM = 512


class _EmptyResponse:
    """Stands in for the httpx response of the params lookup
    read_solr_study4dataset makes after building the dataset -- that query
    is irrelevant here and must not reach a real Solr.
    """

    def json(self):
        return {"response": {"docs": []}}

    async def aclose(self):
        pass


async def _fake_solr_query_get(*args, **kwargs):
    return _EmptyResponse()


def _pad(values):
    """A short vector zero-padded to the fixed 512 length Solr stores."""
    return list(values) + [0.0] * (DIM - len(values))


def _read(doc):
    """Run read_solr_study4dataset over a single synthetic Solr doc and
    return the one dataset it builds.
    """
    response_data = {"response": {"docs": [doc]}}
    with patch("rcapi.api.hsds_dataset.solr_query_get", _fake_solr_query_get):
        result = asyncio.run(
            read_solr_study4dataset(
                "/DOMAIN/assay.nxs#/entry/data",
                response_data,
                True,
                # data_source defaults to a FastAPI Query sentinel, which is
                # only resolved to a real value when the endpoint is called
                # through the framework -- pass it explicitly here.
                data_source=None,
            )
        )
    return result["datasets"][0]


def _doc(**extra):
    doc = {
        "name_s": "SampleA",
        "reference_s": "investigation",
        "reference_owner_s": "owner",
        "document_uuid_s": "uuid-1",
    }
    doc.update(extra)
    return doc


@pytest.mark.parametrize(
    "name,unit,expected",
    [
        ("Concentration", "ug/mL", "Concentration [ug/mL]"),
        ("Concentration", None, "Concentration"),
        (None, "%", "[%]"),
        (None, None, ""),
        # Whitespace-only is as good as absent -- an all-blank title would
        # still reserve axis margin in the plot for nothing.
        ("   ", "  ", ""),
    ],
)
def test_axis_title_composition(name, unit, expected):
    assert axis_title(name, unit) == expected


def test_dense_vectors_are_labelled_from_the_document():
    """A dose-response curve: the y unit is the endpoint's own (%), and the
    x-axis is the condition the indexer picked, with its unit.
    """
    dataset = _read(
        _doc(
            dense_a512=_pad([0.0, 10.0, 100.0]),
            dense_b512=_pad([99.0, 71.0, 29.0]),
            unit_s="%",
            x_name_s="Concentration",
            x_unit_s="ug/mL",
        )
    )

    assert dataset["xtitle"] == "Concentration [ug/mL]"
    assert dataset["ytitle"] == "[%]"
    assert dataset["value"][0][:3] == [0.0, 10.0, 100.0]
    assert dataset["value"][1][:3] == [99.0, 71.0, 29.0]


def test_dense_vectors_without_units_get_no_title():
    """A document indexed before the unit fields existed (or one whose
    source declared no units) must not be given a guessed label -- an empty
    title is what tells the frontend to draw no axis label at all.
    """
    dataset = _read(
        _doc(
            dense_a512=_pad([1.0, 2.0, 3.0]),
            dense_b512=_pad([4.0, 5.0, 6.0]),
        )
    )

    assert dataset["xtitle"] == ""
    assert dataset["ytitle"] == ""


def test_dense_vectors_with_unit_but_no_axis_name():
    """A dense-resampled spectrum: its axis is positional, so the indexer
    reports a unit but no name.
    """
    dataset = _read(
        _doc(
            dense_a512=_pad([100.0, 200.0]),
            dense_b512=_pad([7.0, 8.0]),
            unit_s="a.u.",
            x_unit_s="cm-1",
        )
    )

    assert dataset["xtitle"] == "[cm-1]"
    assert dataset["ytitle"] == "[a.u.]"


def test_solr_vector_branch_keeps_raman_titles():
    """SOLR_VECTOR is a Raman spectrum resampled onto the fixed wavenumber
    search grid, so its titles are known and must survive untouched --
    including when the document also carries unit fields.
    """
    from rcapi.api.hsds_dataset import SOLR_VECTOR

    dataset = _read(
        _doc(
            **{
                SOLR_VECTOR: _pad([1.0, 2.0, 3.0]),
                "unit_s": "%",
                "x_name_s": "Concentration",
                "x_unit_s": "ug/mL",
            }
        )
    )

    assert dataset["xtitle"] == r"wavenumber [$\mathrm{cm}^{-1}$]"
    assert dataset["ytitle"] == "intensity [a.u.]"
