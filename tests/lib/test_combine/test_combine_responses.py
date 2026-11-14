from __future__ import annotations

import io
from pathlib import Path

import obspy
import pytest
from obspy import Inventory
from obspy.core.inventory import Channel, Network, Station
from obspy.core.inventory.response import (
    PolesZerosResponseStage,
    PolynomialResponseStage,
    Response,
    ResponseStage,
)

from nrlx.core.combine import (
    combine_responses,
    datalogger_stages,
    output_rate,
    sensitivity_frequency,
    sensor_stages,
)
from nrlx.core.gain import response_amplitude

DATA_DIR = Path(__file__).parents[2] / "data"


def read(name: str) -> Response:
    return obspy.read_inventory(DATA_DIR / f"{name}.xml")[0][0][0].response


def written(response: Response) -> Response:
    """The response written to StationXML and read back, as a user gets it"""
    channel = Channel("HHZ", "", 0.0, 0.0, 0.0, 0.0, response=response)
    inventory = Inventory([Network("XX", [Station("STA", 0.0, 0.0, 0.0, [channel])])])
    buffer = io.BytesIO()
    inventory.write(buffer, format="STATIONXML")
    buffer.seek(0)
    return obspy.read_inventory(buffer)[0][0][0].response


def signature(response: Response) -> list[tuple[object, ...]]:
    """What makes two cascades of stages the same"""
    return [
        (
            type(stage).__name__,
            stage.stage_gain,
            stage.input_units.upper(),
            stage.output_units.upper(),
            len(getattr(stage, "numerator", None) or []),
            stage.decimation_factor,
        )
        for stage in response.response_stages
    ]


@pytest.mark.parametrize(
    ("sensor", "datalogger", "service"),
    [
        ("nrl_part_sts2", "nrl_part_q330hr", "nrl_sts2_q330"),
        ("nrl_part_tellus", "nrl_part_centaur", "nrl_tellus_centaur"),
        ("nrl_part_ea120", "nrl_part_centaur", "nrl_ea120_centaur"),
    ],
)
def test_combine_gives_the_stages_of_the_service(sensor, datalogger, service):
    combined, _ = combine_responses(read(sensor), read(datalogger))

    assert signature(combined) == signature(read(service))


@pytest.mark.parametrize(
    ("sensor", "datalogger"),
    [
        ("nrl_part_sts2", "nrl_part_q330hr"),
        ("nrl_part_tellus", "nrl_part_centaur"),
        ("nrl_part_ea120", "nrl_part_centaur"),
        ("nrl_part_tellus", "nrl_part_dm24"),
    ],
)
def test_combined_sensitivity_is_the_one_obspy_deconvolves_with(sensor, datalogger):
    combined, _ = combine_responses(read(sensor), read(datalogger))
    sensitivity = combined.instrument_sensitivity

    back = written(combined)
    amplitude = abs(
        back.get_evalresp_response_for_frequencies([sensitivity.frequency], "DEF")[0]
    )

    assert amplitude == pytest.approx(sensitivity.value, rel=1e-6)


def test_combine_corrects_a_normalization_that_contradicts_the_gain():
    sensor = read("nrl_part_ea120")
    service = read("nrl_ea120_centaur")

    combined, notes = combine_responses(sensor, read("nrl_part_centaur"))

    # the Eentec factor is half of what its gain says; the gain wins
    assert notes == [
        "stage 1: normalization factor corrected by x1.99876, so that the stage is "
        "its gain 0.5099 at 1 Hz"
    ]
    frequency = service.instrument_sensitivity.frequency
    assert response_amplitude(combined.response_stages, frequency) == pytest.approx(
        service.instrument_sensitivity.value, rel=1e-5
    )
    assert sensor.response_stages[0].normalization_factor == pytest.approx(
        read("nrl_part_ea120").response_stages[0].normalization_factor
    )


def test_combine_sensitivity_at_the_frequency_of_the_sensor():
    combined, notes = combine_responses(
        read("nrl_part_tellus"), read("nrl_part_centaur")
    )

    assert combined.instrument_sensitivity.frequency == 5.0
    assert combined.instrument_sensitivity.input_units == "m/s"
    assert combined.instrument_sensitivity.output_units == "count"
    assert [stage.stage_sequence_number for stage in combined.response_stages] == list(
        range(1, 7)
    )
    assert len(notes) == 1


def test_combine_fills_an_empty_input_unit():
    combined, notes = combine_responses(read("nrl_part_sts2"), read("nrl_part_dm24"))

    assert "datalogger stage 1: empty input unit set to V" in notes
    assert combined.response_stages[1].input_units == "V"


def test_combine_takes_the_sensor_and_the_datalogger_out_of_whole_channels():
    channel = read("nrl_tellus_centaur")

    combined, _ = combine_responses(channel, read("nrl_part_q330hr"))
    again, _ = combine_responses(read("nrl_part_sts2"), channel)

    assert signature(combined)[0] == signature(read("nrl_part_tellus"))[0]
    assert signature(combined)[1:] == signature(read("nrl_part_q330hr"))
    assert signature(again) == signature(read("nrl_part_sts2")) + signature(
        read("nrl_part_centaur")
    )


def test_combine_of_a_polynomial_sensor():
    combined, _ = combine_responses(read("nrl_poly"), read("nrl_part_centaur"))

    # the counts back to pascals: the linear coefficient over the datalogger gain
    gain = 400000.0
    assert combined.instrument_sensitivity is None
    assert combined.instrument_polynomial.coefficients == pytest.approx(
        [0.0, 1.0 / gain], rel=1e-12
    )
    assert combined.instrument_polynomial.output_units == "count"
    assert isinstance(combined.response_stages[0], PolynomialResponseStage)


def test_combine_refuses_units_that_do_not_chain():
    sensor = Response(
        response_stages=[
            PolesZerosResponseStage(
                1, 1500.0, 1.0, "M/S", "mV", "LAPLACE (RADIANS/SECOND)", 1.0, [], []
            )
        ]
    )

    with pytest.raises(ValueError, match="the sensor gives mV, the datalogger takes V"):
        combine_responses(sensor, read("nrl_part_centaur"))


def test_sensor_and_datalogger_need_a_voltage():
    digital = Response(response_stages=[ResponseStage(1, 1.0, 0.0, "COUNTS", "COUNTS")])

    with pytest.raises(ValueError, match="no stage with a voltage output"):
        sensor_stages(digital)
    with pytest.raises(ValueError, match="no stage with a voltage input"):
        datalogger_stages(digital)


def test_sensitivity_frequency_is_capped_by_the_output_rate():
    stages = read("nrl_part_sts2").response_stages

    kept, none = sensitivity_frequency(stages, 100.0)
    capped, notes = sensitivity_frequency(stages, 1.0)

    assert (kept, none) == (1.0, [])
    assert capped == pytest.approx(0.1)
    assert notes == [
        "sensitivity at 0.1 Hz, a tenth of the 1 sps output, instead of the "
        "sensor's 1 Hz"
    ]


def test_output_rate():
    assert output_rate(read("nrl_part_centaur").response_stages) == 100.0
    assert output_rate(read("nrl_part_sts2").response_stages) is None
