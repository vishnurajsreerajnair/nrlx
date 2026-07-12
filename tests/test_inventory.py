from __future__ import annotations

import importlib.util

import pytest

from nrlx.exceptions import NrlxError
from nrlx.inventory import inventory_from_stationxml

_OBSPY_INSTALLED = importlib.util.find_spec("obspy") is not None


@pytest.mark.skipif(_OBSPY_INSTALLED, reason="obspy is installed here")
def test_converters_without_obspy_give_install_hint():
    with pytest.raises(NrlxError, match=r"nrlx\[obspy\]"):
        inventory_from_stationxml(b"<FDSNStationXML/>")
