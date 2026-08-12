from __future__ import annotations
from pathlib import Path

class SirajAudioDurationError(RuntimeError):
    pass

_MPEG1_L3_BITRATES = (
    0, 32, 40, 48, 56, 64, 80, 96,
    112, 128, 160, 192, 224, 256, 320, 0,
)
_MPEG2_L3_BITRATES = (
    0, 8, 16, 24, 32, 40, 48, 56,
    64, 80, 96, 112, 128, 144, 160, 0,
)
_BASE_SAMPLE_RATES = (44100, 48000, 32000)

def _synchsafe(value: bytes) -> int:
    if len(value) != 4 or any(byte & 0x80 for byte in value):
        raise SirajAudioDurationError("INVALID_ID3_SYNCHSAFE")
    return (
        (value[0] << 21)
        | (value[1] << 14)
        | (value[2] << 7)
        | value[3]
    )

def _skip_id3v2(data: bytes) -> int:
    if len(data) < 10 or data[:3] != b"ID3":
        return 0
    size = _synchsafe(data[6:10])
    footer = 10 if (data[5] & 0x10) else 0
    return min(len(data), 10 + size + footer)

def _frame_info(header: int):
    if (header & 0xFFE00000) != 0xFFE00000:
        return None

    version_bits = (header >> 19) & 0b11
    layer_bits = (header >> 17) & 0b11
    bitrate_index = (header >> 12) & 0b1111
    sample_index = (header >> 10) & 0b11
    padding = (header >> 9) & 0b1

    if version_bits == 0b01 or layer_bits != 0b01:
        return None
    if bitrate_index in (0, 15) or sample_index == 3:
        return None

    if version_bits == 0b11:
        bitrate = _MPEG1_L3_BITRATES[bitrate_index]
        sample_rate = _BASE_SAMPLE_RATES[sample_index]
        samples_per_frame = 1152
        frame_length = int(
            (144000 * bitrate) // sample_rate + padding
        )
    elif version_bits == 0b10:
        bitrate = _MPEG2_L3_BITRATES[bitrate_index]
        sample_rate = _BASE_SAMPLE_RATES[sample_index] // 2
        samples_per_frame = 576
        frame_length = int(
            (72000 * bitrate) // sample_rate + padding
        )
    else:
        bitrate = _MPEG2_L3_BITRATES[bitrate_index]
        sample_rate = _BASE_SAMPLE_RATES[sample_index] // 4
        samples_per_frame = 576
        frame_length = int(
            (72000 * bitrate) // sample_rate + padding
        )

    if bitrate <= 0 or sample_rate <= 0 or frame_length < 24:
        return None

    return frame_length, samples_per_frame, sample_rate

def mp3_duration_seconds(path: Path) -> float:
    path = Path(path)
    if not path.is_file():
        raise SirajAudioDurationError(
            "AUDIO_FILE_NOT_FOUND:" + str(path)
        )

    data = path.read_bytes()
    if len(data) < 128:
        raise SirajAudioDurationError(
            "AUDIO_FILE_TOO_SMALL:" + str(path)
        )

    position = _skip_id3v2(data)
    total_seconds = 0.0
    frame_count = 0
    first_frame_seen = False

    while position + 4 <= len(data):
        header = int.from_bytes(
            data[position:position + 4],
            "big",
        )
        info = _frame_info(header)
        if info is None:
            position += 1
            continue

        frame_length, samples_per_frame, sample_rate = info
        frame_end = position + frame_length
        if frame_end > len(data):
            break

        if not first_frame_seen and frame_end + 4 <= len(data):
            next_header = int.from_bytes(
                data[frame_end:frame_end + 4],
                "big",
            )
            if _frame_info(next_header) is None:
                position += 1
                continue

        first_frame_seen = True
        frame_count += 1
        total_seconds += samples_per_frame / float(sample_rate)
        position = frame_end

    if frame_count < 2 or total_seconds <= 0:
        raise SirajAudioDurationError(
            "MP3_FRAMES_NOT_FOUND:" + str(path)
        )
    return round(total_seconds, 3)

def probe_audio_duration_seconds(path: Path) -> float | None:
    path = Path(path)
    try:
        if path.suffix.lower() == ".mp3":
            return mp3_duration_seconds(path)
    except (OSError, SirajAudioDurationError):
        return None
    return None
