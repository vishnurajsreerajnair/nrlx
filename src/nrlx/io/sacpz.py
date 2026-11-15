"""Reading of SACPZ text, which obspy writes but does not read back"""

from __future__ import annotations


def read_sacpz(
    text: str,
) -> list[tuple[str, list[complex], list[complex], float, float | None]]:
    """Channels of a SACPZ text, in the order of the text

    Each channel is a block of comments (* NETWORK, * STATION, * LOCATION,
    * CHANNEL, and * SAMPLE RATE as obspy and the IRIS service write it), then
    ZEROS n, POLES n and CONSTANT. As SAC defines it, a block lists fewer zeros or
    poles than its count when the others are at the origin.

    Args:
        text: SACPZ text.

    Returns:
        the SEED id NET.STA.LOC.CHA, the zeros and poles in rad/s, the constant
        and the sample rate (None without its comment) of each channel.

    Raises:
        ValueError: if a line is not a number pair where one is expected, a
            block lists more values than its count, or a block has no CONSTANT.


    """
    channels = list()
    network = station = location = channel = ""
    zeros: list[complex] = list()
    poles: list[complex] = list()
    zero_count = pole_count = 0
    section = ""
    sample_rate: float | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        match line.split():
            case []:
                pass
            case ["*", "NETWORK", ":", *code]:
                network = "".join(code)
            case ["*", "STATION", ":", *code]:
                station = "".join(code)
            case ["*", "LOCATION", ":", *code]:
                location = "".join(code)
            case ["*", "CHANNEL", ":", *code]:
                channel = "".join(code)
            case ["*", "SAMPLE", "RATE", ":", "None"]:
                # obspy's comment for a channel without a rate
                sample_rate = None
            case ["*", "SAMPLE", "RATE", ":", value]:
                sample_rate = float(value)
            case [comment, *_] if comment.startswith("*"):
                pass
            case ["ZEROS", total]:
                section, zero_count, zeros = "zeros", int(total), list()
            case ["POLES", total]:
                section, pole_count, poles = "poles", int(total), list()
            case ["CONSTANT", value] if section:
                # the zeros and poles not listed are at the origin
                zeros += [0j] * (zero_count - len(zeros))
                poles += [0j] * (pole_count - len(poles))
                channels.append(
                    (
                        f"{network}.{station}.{location}.{channel}",
                        zeros,
                        poles,
                        float(value),
                        sample_rate,
                    )
                )
                section, sample_rate = "", None
            case [real, imaginary] if section:
                values = zeros if section == "zeros" else poles
                count = zero_count if section == "zeros" else pole_count
                if len(values) >= count:
                    raise ValueError(
                        f"Line {number}: more {section} than the {count} announced."
                    )
                values.append(complex(float(real), float(imaginary)))
            case _:
                raise ValueError(f"Line {number} is not SACPZ: {line.strip()}")
    if section:
        raise ValueError("The last SACPZ block has no CONSTANT.")

    return channels
