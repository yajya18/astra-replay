from __future__ import annotations

import pytest

from app.config import get_settings
from app.errors import PipelineError
from app.pipeline.ingest import parse_probe, target_size, validate_probe
from app.pipeline.motion import adaptive_threshold, find_idle_spans, smooth_curve
from app.pipeline.types import ProbeInfo


def _probe(**overrides: object) -> dict[str, object]:
    video = {
        "codec_type": "video",
        "codec_name": "hevc",
        "width": 1920,
        "height": 1080,
        "r_frame_rate": "30/1",
        "avg_frame_rate": "30/1",
    }
    video.update(overrides)
    return {
        "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "42.5"},
        "streams": [video, {"codec_type": "audio", "codec_name": "aac"}],
    }


def test_parse_probe_reads_rotation_and_vfr() -> None:
    data = _probe(side_data_list=[{"rotation": -90}], avg_frame_rate="2400/100")
    info = parse_probe(data, 1000)
    assert info.rotation == 270
    assert info.variable_frame_rate is True
    assert info.has_audio is True
    assert info.codec == "hevc"
    assert info.duration == pytest.approx(42.5)


def test_parse_probe_rejects_non_video_formats() -> None:
    data = {"format": {"format_name": "tty", "duration": "3"}, "streams": [{"codec_type": "video"}]}
    with pytest.raises(PipelineError) as err:
        parse_probe(data, 10)
    assert err.value.code == "not_a_video"


def test_parse_probe_rejects_audio_only() -> None:
    data = _probe()
    data["streams"] = [{"codec_type": "audio"}]  # type: ignore[index]
    with pytest.raises(PipelineError):
        parse_probe(data, 10)


def test_target_size_upright_and_never_upscaled() -> None:
    portrait = ProbeInfo(duration=10, width=1920, height=1080, rotation=90)
    assert target_size(portrait, 720) == (404, 720)
    small = ProbeInfo(duration=10, width=640, height=360)
    assert target_size(small, 720) == (640, 360)


def test_validate_limits_have_clear_messages() -> None:
    s = get_settings()
    with pytest.raises(PipelineError, match="up to 10 minutes"):
        validate_probe(ProbeInfo(duration=900, width=10, height=10), s)
    with pytest.raises(PipelineError, match="at least 5 seconds"):
        validate_probe(ProbeInfo(duration=2, width=10, height=10), s)
    with pytest.raises(PipelineError, match="MB"):
        validate_probe(
            ProbeInfo(duration=20, width=10, height=10, size_bytes=s.max_upload_bytes + 1), s
        )


def test_smooth_curve_preserves_length() -> None:
    out = smooth_curve([0, 0, 10, 0, 0], 3)
    assert len(out) == 5
    assert out[2] == pytest.approx(10 / 3)


def test_idle_spans_need_minimum_length() -> None:
    fps = 4.0
    values = [5.0] * 8 + [0.0] * 16 + [5.0] * 8 + [0.0] * 4 + [5.0] * 4
    times = [i / fps for i in range(len(values))]
    spans = find_idle_spans(times, values, threshold=1.0, min_s=3.0, step=1 / fps)
    assert len(spans) == 1
    assert spans[0].start == pytest.approx(2.0)
    assert spans[0].end == pytest.approx(6.0)


def test_adaptive_threshold_relative_to_video() -> None:
    s = get_settings()
    busy = [10.0 + (i % 5) for i in range(100)]
    calm = [0.0] * 30 + [10.0] * 70
    assert adaptive_threshold(busy, s) <= 0.5 * 12.0
    assert adaptive_threshold(calm, s) >= 0.15
