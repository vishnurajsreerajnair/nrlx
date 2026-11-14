from __future__ import annotations

from pathlib import Path

import obspy
import pytest
from obspy.core.inventory.response import (
    CoefficientsTypeResponseStage,
    FIRResponseStage,
    InstrumentSensitivity,
    PolesZerosResponseStage,
    PolynomialResponseStage,
    Response,
    ResponseListElement,
    ResponseListResponseStage,
    ResponseStage,
)

from nrlx.core.gain import response_amplitude, stage_amplitude

DATA_DIR = Path(__file__).parents[2] / "data"


def evalresp(stage: ResponseStage, frequency: float, sensitivity: float) -> float:
    """Amplitude of a single stage computed by obspy's evalresp, in a channel whose
    sensitivity is at the frequency sensitivity"""
    response = Response(
        response_stages=[stage],
        instrument_sensitivity=InstrumentSensitivity(
            stage.stage_gain, sensitivity, stage.input_units, stage.output_units
        ),
    )
    return abs(response.get_evalresp_response_for_frequencies([frequency], "DEF")[0])


STAGES = {
    # the normalization factors slightly off, used as written
    "poles and zeros in rad/s": PolesZerosResponseStage(
        1,
        1500.0,
        1.0,
        "M/S",
        "V",
        "LAPLACE (RADIANS/SECOND)",
        1.0,
        zeros=[0j, 0j],
        poles=[-0.037 + 0.037j, -0.037 - 0.037j, -100 + 0j],
        normalization_factor=100.0,
    ),
    "poles and zeros in Hz": PolesZerosResponseStage(
        1,
        1500.0,
        1.0,
        "M/S",
        "V",
        "LAPLACE (HERTZ)",
        1.0,
        zeros=[0j, 0j],
        poles=[-0.00589 + 0.00589j, -0.00589 - 0.00589j, -15.9 + 0j],
        normalization_factor=15.9,
    ),
    "digital poles and zeros": PolesZerosResponseStage(
        1,
        1.0,
        1.0,
        "COUNTS",
        "COUNTS",
        "DIGITAL (Z-TRANSFORM)",
        1.0,
        zeros=[0.9 + 0j],
        poles=[0.5 + 0j],
        normalization_factor=5.0,
        decimation_input_sample_rate=100.0,
        decimation_factor=1,
        decimation_offset=0,
        decimation_delay=0.0,
        decimation_correction=0.0,
    ),
    # a FIR summing to 0.5: evalresp scales it to its gain at 0 Hz
    "coefficients FIR": CoefficientsTypeResponseStage(
        1,
        3.0,
        0.0,
        "COUNTS",
        "COUNTS",
        "DIGITAL",
        numerator=[0.1, 0.15, 0.15, 0.1],
        denominator=[],
        decimation_input_sample_rate=100.0,
        decimation_factor=1,
        decimation_offset=0,
        decimation_delay=0.0,
        decimation_correction=0.0,
    ),
    # a FIR 0.1 % from normalized: used as written
    "coefficients FIR almost normalized": CoefficientsTypeResponseStage(
        1,
        1.0,
        0.0,
        "COUNTS",
        "COUNTS",
        "DIGITAL",
        numerator=[0.25, 0.25, 0.25, 0.251],
        denominator=[],
        decimation_input_sample_rate=100.0,
        decimation_factor=1,
        decimation_offset=0,
        decimation_delay=0.0,
        decimation_correction=0.0,
    ),
    # a symmetric FIR and a filter with denominator: as written
    "symmetric FIR even": FIRResponseStage(
        1,
        3.0,
        0.0,
        "COUNTS",
        "COUNTS",
        symmetry="EVEN",
        coefficients=[0.1, 0.15],
        decimation_input_sample_rate=100.0,
        decimation_factor=1,
        decimation_offset=0,
        decimation_delay=0.0,
        decimation_correction=0.0,
    ),
    "symmetric FIR odd": FIRResponseStage(
        1,
        1.0,
        0.0,
        "COUNTS",
        "COUNTS",
        symmetry="ODD",
        coefficients=[0.1, 0.2, 0.4],
        decimation_input_sample_rate=100.0,
        decimation_factor=1,
        decimation_offset=0,
        decimation_delay=0.0,
        decimation_correction=0.0,
    ),
    "filter with denominator": CoefficientsTypeResponseStage(
        1,
        3.0,
        0.0,
        "COUNTS",
        "COUNTS",
        "DIGITAL",
        numerator=[0.1, 0.15],
        denominator=[1.0, -0.25],
        decimation_input_sample_rate=100.0,
        decimation_factor=1,
        decimation_offset=0,
        decimation_delay=0.0,
        decimation_correction=0.0,
    ),
    "gain only": ResponseStage(1, 8.0, 1.0, "V", "V"),
    "response list": ResponseListResponseStage(
        1,
        1.0,
        1.0,
        "M/S",
        "V",
        response_list_elements=[
            ResponseListElement(frequency, 1.0 + frequency, 10.0 * frequency)
            for frequency in [0.1, 0.5, 1.0, 5.0, 10.0]
        ],
    ),
}


@pytest.mark.parametrize("name", list(STAGES))
@pytest.mark.parametrize("frequency", [0.2, 0.5, 3.0, 8.0])
def test_stage_amplitude_is_evalresp(name, frequency):
    stage = STAGES[name]
    sensitivity = stage.stage_gain_frequency

    assert stage_amplitude(stage, frequency, sensitivity) == pytest.approx(
        evalresp(stage, frequency, sensitivity), rel=1e-12
    )


@pytest.mark.parametrize("name", list(STAGES))
@pytest.mark.parametrize("frequency", [0.2, 3.0])
def test_stage_amplitude_is_evalresp_renormalized_elsewhere(name, frequency):
    # the channel sensitivity at another frequency: evalresp lets the gain win
    stage = STAGES[name]

    assert stage_amplitude(stage, frequency, 2.0) == pytest.approx(
        evalresp(stage, frequency, 2.0), rel=1e-12
    )


def test_response_amplitude_is_the_sensitivity_of_a_consistent_response():
    response = obspy.read_inventory(DATA_DIR / "nrl_sts2_q330.xml")[0][0][0].response
    sensitivity = response.instrument_sensitivity

    amplitude = response_amplitude(response.response_stages, sensitivity.frequency)

    assert amplitude == pytest.approx(sensitivity.value, rel=1e-5)


def test_a_normalization_that_contradicts_the_gain_depends_on_the_frequency():
    response = obspy.read_inventory(DATA_DIR / "nrl_tellus_centaur.xml")[0][0][0]
    response = response.response
    sensitivity = response.instrument_sensitivity
    sensor = response.response_stages[0]

    # the Tellus factor normalizes its stage to 0.99861: used as written at the
    # sensor's frequency, while the gain wins at the 20.75 Hz of the service
    normalization = sensor.normalization_frequency
    written = stage_amplitude(sensor, normalization, normalization)
    amplitude = response_amplitude(response.response_stages, sensitivity.frequency)

    assert written / sensor.stage_gain == pytest.approx(0.998607, rel=1e-5)
    assert amplitude == pytest.approx(sensitivity.value, rel=1e-5)


def test_polynomial_stage_has_no_amplitude():
    stage = PolynomialResponseStage(
        1, None, None, "PA", "V", 0.0, 1.0, -2000.0, 2000.0, 0.01, [0.0, 1.0]
    )

    with pytest.raises(ValueError, match="no transfer function"):
        stage_amplitude(stage, 1.0, 1.0)


def test_digital_stage_needs_its_input_rate():
    stage = CoefficientsTypeResponseStage(
        2, 1.0, 0.0, "COUNTS", "COUNTS", "DIGITAL", numerator=[1.0], denominator=[]
    )

    with pytest.raises(ValueError, match="Stage 2 is digital but has no input"):
        stage_amplitude(stage, 1.0, 1.0)


def test_response_list_outside_its_frequencies():
    with pytest.raises(ValueError, match="outside the response list"):
        stage_amplitude(STAGES["response list"], 20.0, 1.0)
