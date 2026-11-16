from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import obspy
import pytest
from obspy import Inventory, UTCDateTime
from obspy.core.inventory import Channel, Network, Station
from obspy.core.inventory.response import (
    CoefficientsTypeResponseStage,
    FIRResponseStage,
    InstrumentSensitivity,
    PolesZerosResponseStage,
    Response,
    ResponseListElement,
    ResponseListResponseStage,
)

from nrlx.io.resp import number, resp_time, write_resp

DATA_DIR = Path(__file__).parents[2] / "data"

# frequencies of the curves compared, below the Nyquist of 40 sps
FREQUENCIES = np.logspace(-3, np.log10(15.0), 200)


def read_resp(text: str) -> Inventory:
    return obspy.read_inventory(io.BytesIO(text.encode()), format="RESP")


def curve(inventory: Inventory) -> np.ndarray:
    response = inventory[0][0][0].response
    return response.get_evalresp_response_for_frequencies(FREQUENCIES)


def one_channel(response: Response, location: str = "00") -> Inventory:
    channel = Channel(
        "HHZ",
        location,
        0.0,
        0.0,
        0.0,
        0.0,
        sample_rate=100.0,
        response=response,
        start_date=UTCDateTime(2020, 3, 1, 12),
    )
    return Inventory([Network("XX", [Station("TST", 0.0, 0.0, 0.0, [channel])])])


def adc(sequence: int) -> CoefficientsTypeResponseStage:
    return CoefficientsTypeResponseStage(
        sequence,
        400000.0,
        1.0,
        "V",
        "COUNTS",
        "DIGITAL",
        numerator=[1.0],
        denominator=[],
        decimation_input_sample_rate=100.0,
        decimation_factor=1,
        decimation_offset=0,
        decimation_delay=0.0,
        decimation_correction=0.0,
    )


def sensor(sequence: int) -> PolesZerosResponseStage:
    return PolesZerosResponseStage(
        sequence,
        1500.0,
        1.0,
        "M/S",
        "V",
        "LAPLACE (RADIANS/SECOND)",
        1.0,
        zeros=[0j, 0j],
        poles=[-0.037 + 0.037j, -0.037 - 0.037j],
    )


@pytest.mark.parametrize("name", ["nrl_sts2_q330", "nrl_tellus_centaur"])
def test_resp_of_the_nrl_gives_the_curves_of_its_stationxml(name):
    stationxml = obspy.read_inventory(DATA_DIR / f"{name}.xml")
    service = obspy.read_inventory(DATA_DIR / f"{name}.resp", format="RESP")

    ours = read_resp(write_resp(stationxml))

    # exact against the stationxml, within the 6 digits of the service RESP
    assert np.allclose(curve(ours), curve(stationxml), rtol=1e-12, atol=0.0)
    assert np.allclose(curve(ours), curve(service), rtol=1e-5, atol=0.0)
    oursresponse = ours[0][0][0].response
    xmlresponse = stationxml[0][0][0].response
    assert len(oursresponse.response_stages) == len(xmlresponse.response_stages)
    assert (
        oursresponse.instrument_sensitivity.value
        == xmlresponse.instrument_sensitivity.value
    )


def test_resp_of_a_polynomial_has_the_fields_of_the_service():
    stationxml = obspy.read_inventory(DATA_DIR / "nrl_poly.xml")
    service = (DATA_DIR / "nrl_poly.resp").read_text()

    ours = write_resp(stationxml)

    # the values of the blockette 62 lines, the numbers as numbers
    def fields(text: str) -> list[list[str | float]]:
        rows = list()
        for line in text.splitlines():
            if line.startswith("B062"):
                values = line.split(":")[-1].split() if ":" in line else line.split()
                rows.append([to_float(value) for value in values])
        return rows

    assert fields(ours) == fields(service)
    [stage] = read_resp(ours)[0][0][0].response.response_stages
    assert stage.coefficients == [0.0, 1.0]


def to_float(value: str) -> str | float:
    try:
        converted: str | float = float(value)
    except ValueError:
        converted = value
    return converted


def test_resp_of_a_fir_stage():
    response = Response(
        instrument_sensitivity=InstrumentSensitivity(6e8, 1.0, "M/S", "COUNTS"),
        response_stages=[
            sensor(1),
            adc(2),
            FIRResponseStage(
                3,
                1.0,
                1.0,
                "COUNTS",
                "COUNTS",
                symmetry="EVEN",
                coefficients=[0.1, 0.2, 0.2],
                decimation_input_sample_rate=100.0,
                decimation_factor=1,
                decimation_offset=0,
                decimation_delay=0.0,
                decimation_correction=0.0,
            ),
        ],
    )
    inventory = one_channel(response)

    ours = read_resp(write_resp(inventory))

    [_, _, fir] = ours[0][0][0].response.response_stages
    assert isinstance(fir, FIRResponseStage)
    assert fir.symmetry == "EVEN"
    assert np.allclose(curve(ours), curve(inventory), rtol=1e-12, atol=0.0)


def test_resp_of_a_response_list_stage():
    elements = [
        ResponseListElement(frequency, 1.0 + frequency, 10.0 * frequency)
        for frequency in [0.1, 0.5, 1.0, 5.0, 10.0]
    ]
    response = Response(
        instrument_sensitivity=InstrumentSensitivity(8e5, 1.0, "M/S", "COUNTS"),
        response_stages=[
            ResponseListResponseStage(
                1, 1.0, 1.0, "M/S", "V", response_list_elements=elements
            ),
            adc(2),
        ],
    )

    ours = read_resp(write_resp(one_channel(response)))

    [stage, _] = ours[0][0][0].response.response_stages
    assert [
        (element.frequency, element.amplitude, element.phase)
        for element in stage.response_list_elements
    ] == [(element.frequency, element.amplitude, element.phase) for element in elements]


def test_resp_header_and_every_channel():
    stationxml = obspy.read_inventory(DATA_DIR / "nrl_sts2_q330.xml")
    channel = stationxml[0][0][0]
    channel.start_date = UTCDateTime(2020, 3, 1, 12)
    channel.end_date = None
    copies = [channel.copy() for _ in range(3)]
    for copy, code in zip(copies, ["HHZ", "HHN", "HHE"], strict=True):
        copy.code = code
    stationxml[0][0].channels = copies

    text = write_resp(stationxml)
    ours = read_resp(text)

    # each channel repeats its station header, read as a network of its own
    assert [
        channel.code for network in ours for station in network for channel in station
    ] == ["HHZ", "HHN", "HHE"]
    assert text.count("B050F03     Station:     YY") == 3
    assert "B052F22     Start date:  2020,061,12:00:00" in text
    assert "B052F23     End date:    No Ending Time" in text


def test_resp_writes_an_empty_location_as_question_marks():
    response = Response(
        instrument_sensitivity=InstrumentSensitivity(1500.0, 1.0, "M/S", "V"),
        response_stages=[sensor(1)],
    )

    text = write_resp(one_channel(response, location=""))

    assert "B052F03     Location:    ??" in text


def test_resp_refuses_a_channel_without_response():
    with pytest.raises(ValueError, match="XX.TST.00.HHZ has no response"):
        write_resp(one_channel(None))


def test_resp_refuses_an_unknown_transfer_function():
    stage = sensor(1)
    stage._pz_transfer_function_type = "UNKNOWN"
    response = Response(
        instrument_sensitivity=InstrumentSensitivity(1500.0, 1.0, "M/S", "V"),
        response_stages=[stage],
    )

    with pytest.raises(ValueError, match="Unknown poles and zeros transfer"):
        write_resp(one_channel(response))


@pytest.mark.parametrize("value", [1500.0, 3.4684e17, -0.037, 1 / 3, 2.0**-40, 0.0])
def test_numbers_keep_every_digit(value):
    assert float(number(value)) == value
    assert number(1500.0) == "+1.500000000000000E+03"


def test_resp_time():
    assert resp_time(UTCDateTime(1970, 1, 1)) == "1970,001,00:00:00"
    assert resp_time(None) == "No Ending Time"


def test_resp_time_keeps_the_ten_thousandths_of_a_second():
    assert resp_time(UTCDateTime(2022, 4, 22, 5, 53, 33, 749000)) == (
        "2022,112,05:53:33.7490"
    )
    assert resp_time(UTCDateTime(2022, 4, 22, 5, 53, 33, 50)) == "2022,112,05:53:33"


def test_resp_reads_back_a_start_with_a_fraction_of_a_second():
    inventory = one_channel(Response(response_stages=[sensor(1), adc(2)]))
    inventory[0][0][0].start_date = UTCDateTime(2022, 4, 22, 5, 53, 33, 749000)

    back = read_resp(write_resp(inventory))

    assert back[0][0][0].start_date == UTCDateTime(2022, 4, 22, 5, 53, 33, 749000)


def test_resp_leaves_out_a_sensitivity_without_value():
    response = Response(
        instrument_sensitivity=InstrumentSensitivity(None, None, "M/S", "COUNTS"),
        response_stages=[sensor(1), adc(2)],
    )

    text = write_resp(one_channel(response))

    # the gains of stages 1 and 2, no stage 0
    assert text.count("B058F03") == 2


def test_resp_leaves_out_the_gain_of_a_stage_without_one():
    first = sensor(1)
    first.stage_gain = None
    inventory = one_channel(
        Response(
            instrument_sensitivity=InstrumentSensitivity(1.0, 1.0, "M/S", "COUNTS"),
            response_stages=[first, adc(2)],
        )
    )

    text = write_resp(inventory)

    # the gains of stage 2 and of the channel, none for stage 1
    assert text.count("B058F03") == 2
    assert np.allclose(curve(read_resp(text)), curve(inventory))
