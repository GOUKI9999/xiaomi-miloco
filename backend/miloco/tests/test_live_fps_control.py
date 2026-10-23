"""Live view frame-rate selection, auto degrade, perception intake and IDR cadence."""
from __future__ import annotations

from types import SimpleNamespace

import miloco.miot.ws as ws_module
import miloco.perception.collect.camera_adapter as adapter_module
import numpy as np
import pytest
from miloco.miot import transcoder as transcoder_module
from miloco.miot.transcoder import KEYFRAME_INTERVAL_S, H264LiveEncoder
from miloco.miot.ws import _LiveRateState, live_frame_interval_ms, resolve_live_fps


@pytest.fixture
def camera_settings(monkeypatch):
    settings = SimpleNamespace(camera=SimpleNamespace(live_default_fps=5, live_max_fps=20))
    monkeypatch.setattr(ws_module, "get_settings", lambda: settings)
    return settings


def test_resolve_live_fps_defaults_and_clamps(camera_settings):
    assert resolve_live_fps(None) == 5
    assert resolve_live_fps(0) == 5
    assert resolve_live_fps(3) == 3
    assert resolve_live_fps(60) == 20
    camera_settings.camera.live_max_fps = 3
    assert resolve_live_fps(None) == 3


def test_live_frame_interval_ms():
    assert live_frame_interval_ms(5) == 200
    assert live_frame_interval_ms(1) == 1000
    assert live_frame_interval_ms(20) == 50


def _feed(state, start, seconds, fps, drop_every):
    """Feed frames at fps for the given seconds; drop_every=N drops each Nth frame, 0 none."""
    changes = []
    n = int(seconds * fps)
    for i in range(n):
        dropped = bool(drop_every) and i % drop_every == 0
        change = state.note_frame(dropped, start + i / fps)
        if change:
            changes.append((change, state.current_fps))
    return changes, start + n / fps


def test_sustained_drops_halve_rate_down_to_one_fps():
    state = _LiveRateState(target_fps=20, current_fps=20)
    changes, t = _feed(state, 1000.0, 11, 20, drop_every=2)
    assert changes == [("degraded", 10)]
    changes, t = _feed(state, t, 11, 10, drop_every=2)
    assert changes == [("degraded", 5)]
    for _ in range(5):
        _, t = _feed(state, t, 11, 5, drop_every=1)
    assert state.current_fps == 1


def test_light_drops_do_not_degrade():
    state = _LiveRateState(target_fps=10, current_fps=10)
    changes, _ = _feed(state, 1000.0, 30, 10, drop_every=5)
    assert changes == []
    assert state.current_fps == 10


def test_rate_recovers_only_after_a_long_quiet_period():
    state = _LiveRateState(target_fps=20, current_fps=20)
    _, t = _feed(state, 1000.0, 11, 20, drop_every=2)
    assert state.current_fps == 10
    changes, t = _feed(state, t, 9 * 60, 10, drop_every=0)
    assert changes == []
    changes, t = _feed(state, t, 2 * 60, 10, drop_every=0)
    assert changes == [("restored", 20)]


def test_restore_backoff_doubles_after_each_failed_restore():
    state = _LiveRateState(target_fps=20, current_fps=20)
    _, t = _feed(state, 1000.0, 11, 20, drop_every=2)
    assert state.restore_wait == ws_module._LIVE_RESTORE_INITIAL_S
    _, t = _feed(state, t, 11 * 60, 10, drop_every=0)
    assert state.current_fps == 20
    _, t = _feed(state, t, 11, 20, drop_every=2)
    assert state.current_fps == 10
    assert state.restore_wait == 2 * ws_module._LIVE_RESTORE_INITIAL_S
    for _ in range(5):
        state.last_restore = t
        state.current_fps = 20
        _, t = _feed(state, t, 11, 20, drop_every=2)
    assert state.restore_wait == ws_module._LIVE_RESTORE_MAX_S


def test_recorder_requests_max_rate_while_attached(camera_settings):
    mgr = ws_module.MIoTVideoStreamManager()
    tag = "cam.0"
    mgr._camera_connect_map[tag] = {"u": {"1": SimpleNamespace(live_fps=5)}}
    assert mgr._requested_live_fps(tag) == 5
    mgr._camera_recorders[tag] = [object()]
    assert mgr._requested_live_fps(tag) == 20
    mgr._camera_recorders.pop(tag)
    mgr._camera_connect_map.pop(tag)
    assert mgr._requested_live_fps(tag) == 5


def test_perception_gap_follows_engine_input_fps(monkeypatch):
    def settings(inp):
        return SimpleNamespace(perception=SimpleNamespace(engine={"input": inp}))

    monkeypatch.setattr(adapter_module, "get_settings", lambda: settings({"fps": 3, "omni_fps": 1}))
    assert adapter_module._perception_frame_gap_ms() == 300
    monkeypatch.setattr(adapter_module, "get_settings", lambda: settings({"fps": 1, "omni_fps": 1}))
    assert adapter_module._perception_frame_gap_ms() == 900
    monkeypatch.setattr(adapter_module, "get_settings", lambda: settings({}))
    assert adapter_module._perception_frame_gap_ms() == 0


def test_encoder_forces_idr_by_time(monkeypatch):
    clock = {"t": 100.0}
    monkeypatch.setattr(transcoder_module.time, "monotonic", lambda: clock["t"])
    enc = H264LiveEncoder(gop=300)
    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    keys = []
    for i in range(12):
        clock["t"] = 100.0 + i * 0.5
        packets = enc._encode_sync(frame, pts_ms=i)
        keys.append(any(k for _, k in packets))
    step = int(KEYFRAME_INTERVAL_S / 0.5)
    assert keys == [i % step == 0 for i in range(12)]
