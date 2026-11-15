from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

import obspy
import pytest
from obspy import UTCDateTime
from obspy.core.inventory.response import (
    InstrumentSensitivity,
    PolesZerosResponseStage,
    Response,
)

from nrlx.core.convert import pz_amplitude
from nrlx.io.inventory import (
    label_channels,
    placeholder_inventory,
    read_channels,
    read_part,
    read_stationxml,
    set_coordinates,
    split_channels,
    verify_written,
    write_inventory,
)
from nrlx.io.sacpz import read_sacpz

DATA_DIR = Path(__file__).parents[2] / "data"


def test_label_channels_copies_the_channel_for_each_code(make_stationxml):
    response = read_stationxml(make_stationxml("ZZZ"))

    labelled = label_channels(
        response,
        "XY",
        "TST",
        "10",
        ["HHZ", "hhn", "X1"],
        datetime(2026, 1, 1),
        datetime(2027, 1, 1),
    )

    [network] = labelled
    [station] = network
    assert (network.code, station.code) == ("XY", "TST")
    # the codes as given, even outside the SEED norm
    assert [channel.code for channel in station] == ["HHZ", "hhn", "X1"]
    assert {channel.location_code for channel in station} == {"10"}
    assert station.total_number_of_channels == 3
    assert [channel.start_date for channel in station] == [UTCDateTime(2026, 1, 1)] * 3
    assert [channel.end_date for channel in station] == [UTCDateTime(2027, 1, 1)] * 3
    assert station.start_date == UTCDateTime(2026, 1, 1)
    assert network.end_date == UTCDateTime(2027, 1, 1)
    # the same response on each channel, the service answer unchanged
    sensitivities = {
        channel.response.instrument_sensitivity.value for channel in station
    }
    assert sensitivities == {1500.0}
    assert [channel.code for channel in response[0][0]] == ["ZZZ"]


def test_label_channels_keeps_the_placeholders_not_given(make_stationxml):
    response = read_stationxml(make_stationxml("ZZZ"))

    labelled = label_channels(response, None, None, None, [], None, None)

    [network] = labelled
    [station] = network
    [channel] = station
    assert (network.code, station.code, channel.code) == ("XY", "MYSTN", "ZZZ")


def test_label_channels_allows_an_empty_location(make_stationxml):
    labelled = label_channels(
        read_stationxml(make_stationxml("ZZZ")), None, None, "", ["HHZ"], None, None
    )

    assert labelled[0][0][0].location_code == ""


def test_set_coordinates_places_the_station_and_its_channels(make_stationxml):
    response = label_channels(
        read_stationxml(make_stationxml("ZZZ")),
        None,
        None,
        None,
        ["EHZ", "EHN"],
        None,
        None,
    )

    placed = set_coordinates(response, 49.096, -8.432, 112.0, 25.0)

    station = placed[0][0]
    assert (station.latitude, station.longitude, station.elevation) == (
        49.096,
        -8.432,
        112.0,
    )
    assert [
        (channel.latitude, channel.longitude, channel.elevation, channel.depth)
        for channel in station
    ] == [(49.096, -8.432, 112.0, 25.0), (49.096, -8.432, 112.0, 25.0)]
    assert response[0][0].latitude == 0.0


def test_read_part_of_a_single_channel():
    expected = obspy.read_inventory(DATA_DIR / "nrl_sts2_q330.xml")[0][0][0].response

    response = read_part(DATA_DIR / "nrl_sts2_q330.xml")
    from_resp = read_part(DATA_DIR / "nrl_sts2_q330.resp")

    assert response == expected
    assert len(from_resp.response_stages) == len(expected.response_stages)


def test_read_part_picks_a_channel_by_its_seed_id(tmp_path, make_stationxml):
    path = tmp_path / "two.xml"
    inventory = read_stationxml(make_stationxml("HHZ"))
    inventory = label_channels(inventory, None, None, "00", ["HHZ", "HHN"], None, None)
    inventory[0][0][1].response.response_stages[0].stage_gain = 750.0
    inventory.write(str(path), format="STATIONXML")

    response = read_part(path, "XY.MYSTN.00.HHN")

    assert response.response_stages[0].stage_gain == 750.0
    with pytest.raises(LookupError, match="2 channels or epochs"):
        read_part(path)
    with pytest.raises(LookupError, match=r"No channel XY.MYSTN.00.BHZ .*HHN, "):
        read_part(path, "XY.MYSTN.00.BHZ")


def test_read_part_refuses_what_obspy_cannot_read(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("not a response")

    with pytest.raises(ValueError, match="Unknown format"):
        read_part(path)
    with pytest.raises(FileNotFoundError):
        read_part(tmp_path / "missing.xml")


def test_placeholder_inventory_has_the_shape_of_the_service():
    service = obspy.read_inventory(DATA_DIR / "nrl_part_centaur.xml")
    response = service[0][0][0].response

    inventory = placeholder_inventory(response, 100.0)

    [network] = inventory
    [station] = network
    [channel] = station
    expected = service[0][0][0]
    assert (network.code, station.code) == (service[0].code, service[0][0].code)
    assert (channel.code, channel.location_code) == (
        expected.code,
        expected.location_code,
    )
    assert channel.start_date == expected.start_date
    assert channel.sample_rate == 100.0
    assert channel.response is response


def test_read_channels_keeps_every_channel_or_one(station_xml):
    every = read_channels(station_xml)
    one = read_channels(station_xml, "XY.T13.00.HHN")

    assert [cha.code for cha in every[0][0]] == ["HHZ", "HHN", "HHE"]
    assert [cha.code for cha in one[0][0]] == ["HHN"]


def test_read_channels_merges_the_stations_obspy_splits_in_resp(station_xml, tmp_path):
    resp = write_inventory(read_channels(station_xml), tmp_path / "st.resp", "resp")

    [network] = read_channels(resp)

    [station] = network
    assert [cha.code for cha in station] == ["HHZ", "HHN", "HHE"]


def test_read_channels_unknown_seed_id_lists_the_channels(station_xml):
    with pytest.raises(LookupError, match=r"No channel XY.T13.00.BHZ in .*HHE"):
        read_channels(station_xml, "XY.T13.00.BHZ")


def test_read_channels_unknown_format(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("not a response")

    with pytest.raises(ValueError, match="Cannot read"):
        read_channels(path)


def test_read_channels_reads_dataless_seed(dataless_seed):
    inventory = read_channels(dataless_seed)

    [channel] = inventory[0][0]
    assert len(channel.response.response_stages) == 4


def test_split_channels_names_each_inventory_by_its_seed_id(station_xml):
    parts = split_channels(read_channels(station_xml))

    assert [seedid for seedid, _ in parts] == [
        "XY.T13.00.HHZ",
        "XY.T13.00.HHN",
        "XY.T13.00.HHE",
    ]
    assert [len(single[0][0]) for _, single in parts] == [1, 1, 1]


def test_stationxml_to_resp_and_back_reads_back_the_same(station_xml, tmp_path):
    inventory = read_channels(station_xml)
    resp = write_inventory(inventory, tmp_path / "station.resp", "resp")
    notes = verify_written(inventory, resp, "resp")
    again = read_channels(resp)
    xml = write_inventory(again, tmp_path / "again.xml", "stationxml")

    assert notes == []
    assert verify_written(again, xml, "stationxml") == []
    assert read_channels(xml)[0][0][0].response.instrument_sensitivity.value == (
        inventory[0][0][0].response.instrument_sensitivity.value
    )


def test_dataless_seed_to_stationxml_reads_back_the_same(dataless_seed, tmp_path):
    inventory = read_channels(dataless_seed)
    xml = write_inventory(inventory, tmp_path / "station.xml", "stationxml")

    assert verify_written(inventory, xml, "stationxml") == []


def test_polynomial_to_resp_reads_back_the_same(tmp_path):
    # obspy reads the polynomial of RESP as a stage 0
    inventory = read_channels(DATA_DIR / "nrl_poly.xml")
    resp = write_inventory(inventory, tmp_path / "poly.resp", "resp")

    assert verify_written(inventory, resp, "resp") == []


def test_verify_written_fails_on_a_file_that_reads_back_different(
    station_xml, tmp_path
):
    inventory = read_channels(station_xml, "XY.T13.00.HHZ")
    resp = write_inventory(inventory, tmp_path / "station.resp", "resp")
    text = resp.read_text()
    resp.write_text(text.replace("+1.500000000000000E+03", "+1.501000000000000E+03", 1))

    with pytest.raises(ValueError, match="XY.T13.00.HHZ reads back 6.7e-04"):
        verify_written(inventory, resp, "resp")


def test_sacpz_notes_what_it_drops(station_xml, tmp_path):
    inventory = read_channels(station_xml, "XY.T13.00.HHZ")
    pz = write_inventory(inventory, tmp_path / "station.pz", "sacpz")

    [note] = verify_written(inventory, pz, "sacpz")

    assert note.startswith(
        "XY.T13.00.HHZ: SACPZ keeps stage 1 and the overall sensitivity, and drops "
        "the other 3 stages: within "
    )
    assert note.endswith("at 16 Hz")


def test_sacpz_refuses_a_channel_without_poles_and_zeros(tmp_path):
    inventory = read_channels(DATA_DIR / "nrl_poly.xml")

    with pytest.raises(ValueError, match="SACPZ holds only .* not XX.YY.00.ZZZ"):
        write_inventory(inventory, tmp_path / "poly.pz", "sacpz")
    assert not (tmp_path / "poly.pz").exists()


def test_write_inventory_refuses_a_channel_without_response(station_xml, tmp_path):
    inventory = read_channels(station_xml, "XY.T13.00.HHE")
    inventory[0][0][0].response = None

    with pytest.raises(ValueError, match="No response to write for XY.T13.00.HHE"):
        write_inventory(inventory, tmp_path / "station.xml", "stationxml")


def test_read_channels_gives_the_rate_obspy_rounds_to_zero_in_resp(tmp_path):
    inventory = read_channels(DATA_DIR / "nrl_sts2_q330.xml")
    channel = inventory[0][0][0]
    # the last decimation from 0.4 to 0.1 sps: obspy reads round(0.1) = 0
    last = channel.response.response_stages[-1]
    last.decimation_input_sample_rate, last.decimation_factor = 0.4, 4
    channel.sample_rate = 0.1
    resp = write_inventory(inventory, tmp_path / "slow.resp", "resp")

    assert obspy.read_inventory(str(resp))[0][0][0].sample_rate == 0
    assert read_channels(resp)[0][0][0].sample_rate == pytest.approx(0.1)


def geophone(frequency: float) -> obspy.Inventory:
    """A 4.5 Hz geophone normalized at 100 Hz, its sensitivity at a frequency"""
    corner = 2 * math.pi * 4.5
    stage = PolesZerosResponseStage(
        stage_sequence_number=1,
        stage_gain=28.8,
        stage_gain_frequency=100.0,
        input_units="M/S",
        output_units="V",
        pz_transfer_function_type="LAPLACE (RADIANS/SECOND)",
        normalization_frequency=100.0,
        zeros=[0j, 0j],
        poles=[
            complex(-0.7 * corner, 0.714 * corner),
            complex(-0.7 * corner, -0.714 * corner),
        ],
        normalization_factor=1.0,
    )
    stage.normalization_factor = stage.calculate_normalization_factor()
    response = Response(
        instrument_sensitivity=InstrumentSensitivity(28.8, 100.0, "M/S", "V"),
        response_stages=[stage],
    )
    response.recalculate_overall_sensitivity(frequency)
    return placeholder_inventory(response, None)


def test_sacpz_constant_is_right_when_the_sensitivity_is_not_at_a0(tmp_path):
    inventory = geophone(0.1)
    response = inventory[0][0][0].response
    pz = write_inventory(inventory, tmp_path / "geophone.pz", "sacpz")

    [(_, zeros, poles, constant, _)] = read_sacpz(pz.read_text())

    frequencies = [0.1, 1.0, 4.5, 10.0, 100.0]
    whole = response.get_evalresp_response_for_frequencies(frequencies, output="DISP")
    written = [pz_amplitude(zeros, poles, constant, f) for f in frequencies]
    assert written == pytest.approx([abs(value) for value in whole], rel=1e-5)
    # obspy alone writes A0 at 100 Hz times the sensitivity at 0.1 Hz
    first = response.response_stages[0]
    assert constant != pytest.approx(
        first.normalization_factor * response.instrument_sensitivity.value, rel=0.01
    )
    # the inventory given is not changed
    assert first.normalization_frequency == 100.0
    [note] = verify_written(inventory, pz, "sacpz")
    assert "within 0.00%" in note


def test_sacpz_refuses_a_digital_first_poles_and_zeros(tmp_path):
    inventory = geophone(1.0)
    first = inventory[0][0][0].response.response_stages[0]
    first.pz_transfer_function_type = "DIGITAL (Z-TRANSFORM)"

    with pytest.raises(ValueError, match="analog poles and zeros"):
        write_inventory(inventory, tmp_path / "digital.pz", "sacpz")
