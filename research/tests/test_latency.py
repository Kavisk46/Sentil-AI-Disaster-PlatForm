import time

from research.core.latency import LatencyRecorder


def test_measure_records_a_real_non_negative_duration() -> None:
    recorder = LatencyRecorder()
    with recorder.measure("stage_a"):
        time.sleep(0.001)

    assert len(recorder.timings) == 1
    assert recorder.timings[0].stage == "stage_a"
    assert recorder.timings[0].duration_ms >= 0.0


def test_measure_records_stages_in_call_order() -> None:
    recorder = LatencyRecorder()
    with recorder.measure("first"):
        pass
    with recorder.measure("second"):
        pass

    assert [timing.stage for timing in recorder.timings] == ["first", "second"]


def test_total_ms_sums_every_recorded_stage() -> None:
    recorder = LatencyRecorder()
    with recorder.measure("a"):
        pass
    with recorder.measure("b"):
        pass

    assert recorder.total_ms == sum(timing.duration_ms for timing in recorder.timings)


def test_as_dict_maps_stage_to_duration() -> None:
    recorder = LatencyRecorder()
    with recorder.measure("only_stage"):
        pass

    result = recorder.as_dict()

    assert set(result.keys()) == {"only_stage"}
    assert result["only_stage"] == recorder.timings[0].duration_ms


def test_a_stage_that_never_runs_never_appears() -> None:
    """A stage that isn't measured must never be fabricated with a
    synthetic duration — it simply isn't in the recorder at all."""
    recorder = LatencyRecorder()
    with recorder.measure("only_this_one"):
        pass

    assert "hazard_assessment" not in recorder.as_dict()
