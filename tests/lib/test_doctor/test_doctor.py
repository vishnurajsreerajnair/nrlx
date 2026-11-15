from __future__ import annotations

import copy
from pathlib import Path

import obspy
import pytest
from obspy.core.inventory.response import Response

from nrlx.core.convert import check_frequencies
from nrlx.core.doctor import (
    check_amplitude,
    check_chains,
    check_codes,
    check_nominal_curve,
    check_nominal_kind,
    check_poles,
    check_poles_zeros,
    check_sacpz,
    stage_changes,
)
from nrlx.core.gain import response_amplitude
from nrlx.io.inventory import evalresp_values

DATA_DIR = Path(__file__).parents[2] / "data"

# the STS-2 + Q330 channel of the service, at 40 sps
STS2_Q330 = obspy.read_inventory(DATA_DIR / "nrl_sts2_q330.xml")[0][0][0].response


def sts2_q330() -> Response:
    """A copy of the STS-2 + Q330 channel, to change"""
    return copy.deepcopy(STS2_Q330)


def severities(findings: list[tuple[str, str]]) -> list[str]:
    """The severities of the findings, in order"""
    return [severity for severity, _ in findings]


def problems(findings: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """The warnings and errors of the findings"""
    return [
        (severity, message)
        for severity, message in findings
        if severity in ("warning", "error")
    ]


# tier 2: amplitude


def test_a_consistent_channel_passes_every_check():
    response = sts2_q330()

    findings = (
        check_amplitude(response, 40.0)
        + check_chains(response, 40.0)
        + check_poles(response)
    )

    assert set(severities(findings)) == {"ok"}
    assert ("ok", "units m/s -> V -> V -> count -> count") in findings


def test_a_stated_sensitivity_off_its_stages_is_an_error():
    response = sts2_q330()
    response.instrument_sensitivity.value *= 2.0

    [(severity, message)] = problems(check_amplitude(response, 40.0))

    assert severity == "error"
    assert message.startswith(
        "stated 5.2819e+09 at 8.49583 Hz, the stages give 2.64095e+09 (x2)"
    )


def test_a_channel_without_sensitivity_is_an_error():
    response = sts2_q330()
    response.instrument_sensitivity = None

    assert check_amplitude(response, 40.0) == [
        ("error", "no sensitivity and no polynomial")
    ]


def test_a_normalization_factor_off_its_gain_is_a_warning():
    response = sts2_q330()
    response.response_stages[0].normalization_factor *= 0.5
    response.instrument_sensitivity.value = response_amplitude(
        response.response_stages, response.instrument_sensitivity.frequency
    )

    [(severity, message)] = problems(check_amplitude(response, 40.0))

    assert severity == "warning"
    assert message.startswith("stage 1: the normalization factor gives x0.5 ")


def test_a_sensitivity_out_of_the_flat_band_or_above_nyquist_is_a_warning():
    response = sts2_q330()
    sensitivity = response.instrument_sensitivity
    sensitivity.frequency = 0.0005
    sensitivity.value = response_amplitude(response.response_stages, 0.0005)

    [(_, low)] = problems(check_amplitude(response, 40.0))
    sensitivity.frequency = 25.0
    sensitivity.value = response_amplitude(response.response_stages, 25.0)
    [(_, high)] = problems(check_amplitude(response, 40.0))

    assert "the sensitivity is out of its flat band" in low
    assert "at or above the Nyquist frequency of 40 sps" in high


def test_a_fir_not_summing_to_1_is_a_warning():
    response = sts2_q330()
    fir = response.response_stages[3]
    fir.numerator = [0.9 * coefficient for coefficient in fir.numerator]
    response.instrument_sensitivity.value = response_amplitude(
        response.response_stages, response.instrument_sensitivity.frequency
    )

    [(severity, message)] = problems(check_amplitude(response, 40.0))

    assert severity == "warning"
    assert "stage 4: the FIR coefficients sum to 0.9, not 1" in message


def test_a_polynomial_has_no_sensitivity_to_check():
    response = obspy.read_inventory(DATA_DIR / "nrl_poly.xml")[0][0][0].response

    assert severities(check_amplitude(response, None)) == ["info"]


# tier 2: chains


def test_a_unit_break_and_no_counts_are_errors():
    response = sts2_q330()
    response.response_stages[2].input_units = "mV"
    response.response_stages[3].output_units = "V"

    found = problems(check_chains(response, 40.0))

    assert found[0] == ("error", "units break: stage 3 takes mV after V")
    assert ("error", "the last stage gives V, not counts") in found
    assert ("error", "sensitivity in M/S -> COUNT, the stages in M/S -> V") in found


def test_stages_not_numbered_1_to_n_are_an_error():
    response = sts2_q330()
    response.response_stages[3].stage_sequence_number = 7

    assert ("error", "stages numbered [1, 2, 3, 7], not 1 to N") in problems(
        check_chains(response, 40.0)
    )


def test_a_digital_stage_without_decimation_is_an_error():
    response = sts2_q330()
    response.response_stages[3].decimation_input_sample_rate = None

    assert ("error", "digital stages without decimation: 4") in problems(
        check_chains(response, 40.0)
    )


def test_a_rate_break_is_a_warning_and_a_wrong_channel_rate_an_error():
    # the ADC stage says 4000 sps and the next FIR takes 40, as NRL files do
    response = sts2_q330()
    response.response_stages[2].decimation_input_sample_rate = 4000.0

    found = problems(check_chains(response, 40.0))
    wrong_rate = problems(check_chains(sts2_q330(), 100.0))

    assert found == [
        (
            "warning",
            "rates break: stage 4 takes 40 sps after 4000 (evalresp takes each "
            "stage at its own rate)",
        )
    ]
    assert wrong_rate == [("error", "the decimations give 40 sps, the channel 100")]


# tier 2: poles


def test_a_pole_with_the_wrong_sign_is_an_error():
    # the poles of the REFTEK RT131B-01 in the NRL, +30300 and +58900 rad/s
    found = check_poles_zeros([], [complex(30300), complex(58900)], False, "stage 1")

    assert found == [("error", "stage 1: unstable poles 30300+0j, 58900+0j")]


def test_an_analog_pole_typed_digital_is_an_error():
    # the DC filter of the DTCC SmartSolo in the NRL: -2 pi rad/s as a Z transform
    found = check_poles_zeros([0j], [complex(-6.28318)], True, "stage 7")

    assert found == [("error", "stage 7: unstable poles -6.28318+0j")]
    assert check_poles_zeros([0j], [complex(0.999975)], True, "stage 7") == [
        ("ok", "stage 7: 1 poles, all stable")
    ]


def test_a_zero_on_a_pole_is_a_warning():
    found = check_poles_zeros([0j, -1.0 + 0j], [-1.0 + 1e-9j], False, "stage 1")

    assert found[1] == ("warning", "stage 1: zeros cancel the poles -1+1e-09j")


def test_check_poles_skips_the_gain_only_stages():
    assert check_poles(sts2_q330()) == [("ok", "stage 1: 11 poles, all stable")]


def test_check_sacpz_checks_the_constant():
    found = check_sacpz([0j, 0j], [-0.037 + 0.037j, -0.037 - 0.037j], -1.0)

    assert severities(found) == ["ok", "error", "info"]
    assert found[1] == ("error", "CONSTANT -1 is not above 0")


# tier 2: codes


@pytest.mark.parametrize(
    ("code", "rate", "units", "expected"),
    [
        ("HHZ", 100.0, "m/s", ["ok", "ok"]),
        ("BHZ", 100.0, "m/s", ["warning", "ok"]),
        ("HNZ", 100.0, "m/s", ["ok", "warning"]),
        ("HDF", 100.0, "Pa", ["ok", "ok"]),
        ("XYZ", None, None, ["info", "info"]),
    ],
)
def test_check_codes_against_the_seed_norm(code, rate, units, expected):
    assert severities(check_codes(code, rate, units)) == expected


def test_check_codes_says_what_the_norm_gives():
    [band, instrument] = check_codes("BNZ", 100.0, "m/s")

    assert band == ("warning", "band B for 100 sps: the SEED norm gives H or E")
    assert instrument == (
        "warning",
        "instrument N is an accelerometer, in M/S**2 or M/SEC**2, not M/S",
    )


# tier 3


def nominal_findings(response: Response) -> list[tuple[str, str]]:
    """Tier 3 findings of a response against the STS-2 + Q330 channel at 40 sps"""
    frequencies = check_frequencies(40.0)

    return check_nominal_kind(response, STS2_Q330, 40.0, 40.0) + check_nominal_curve(
        frequencies,
        evalresp_values(response, frequencies),
        evalresp_values(STS2_Q330, frequencies),
    )


def test_the_nominal_itself_passes():
    findings = nominal_findings(sts2_q330())

    assert set(severities(findings)) == {"ok"}
    assert stage_changes(STS2_Q330.response_stages, STS2_Q330.response_stages) == []


def test_a_calibrated_gain_is_a_warning_with_the_stage_that_changed():
    response = sts2_q330()
    response.response_stages[0].stage_gain *= 1.02
    response.instrument_sensitivity.value *= 1.02

    [(severity, message)] = problems(nominal_findings(response))

    assert severity == "warning"
    assert message.startswith("amplitude +2% from the nominal at ")
    assert stage_changes(response.response_stages, STS2_Q330.response_stages) == [
        "stage 1: gain 1530 for 1500"
    ]


def test_a_pole_of_the_wrong_sign_is_a_phase_warning():
    response = sts2_q330()
    stage = response.response_stages[0]
    stage.poles = [complex(-pole.real, pole.imag) for pole in stage.poles]

    found = problems(nominal_findings(response))

    assert [severity for severity, _ in found] == ["warning"]
    assert found[0][1].startswith("phase ")
    assert stage_changes(response.response_stages, STS2_Q330.response_stages) == [
        "stage 1: poles and zeros"
    ]


def test_another_rate_input_or_sensor_is_an_error():
    response = sts2_q330()
    response.response_stages[0].input_units = "M/S**2"
    response.response_stages[0].poles = response.response_stages[0].poles[:-1]

    found = check_nominal_kind(response, STS2_Q330, 100.0, 40.0)

    assert found == [
        ("error", "input in M/S**2, the nominal in M/S"),
        ("error", "100 sps, the nominal 40 sps"),
        (
            "error",
            "sensor poles and zeros: LAPLACE (RADIANS/SECOND), 10 poles, 6 zeros; "
            "the nominal: LAPLACE (RADIANS/SECOND), 11 poles, 6 zeros",
        ),
    ]


def test_stage_changes_names_the_stages_that_differ():
    response = sts2_q330()
    fir = response.response_stages[3]
    fir.numerator = [0.5 * coefficient for coefficient in fir.numerator]
    fir.decimation_factor = 2

    assert stage_changes(response.response_stages[:-1], STS2_Q330.response_stages) == [
        "3 stages, the nominal 4"
    ]
    assert stage_changes(response.response_stages, STS2_Q330.response_stages) == [
        "stage 4: coefficients, decimation"
    ]
