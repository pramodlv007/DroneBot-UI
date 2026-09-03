import math

import pytest

from app.dead_reckoning import DeadReckoningEstimator


def test_first_update_establishes_baseline_without_moving():
    est = DeadReckoningEstimator()
    x, y = est.update(yaw_rad=0.0, ground_speed_mps=2.0, timestamp_ms=1000)
    assert (x, y) == (0.0, 0.0)


def test_integrates_heading_and_speed_forward():
    est = DeadReckoningEstimator()
    est.update(yaw_rad=0.0, ground_speed_mps=1.0, timestamp_ms=0)  # baseline
    x, y = est.update(yaw_rad=0.0, ground_speed_mps=1.0, timestamp_ms=500)  # 0.5s @ 1 m/s east
    assert x == pytest.approx(0.5)
    assert y == pytest.approx(0.0)


def test_integrates_along_arbitrary_heading():
    est = DeadReckoningEstimator()
    est.update(yaw_rad=math.pi / 2, ground_speed_mps=2.0, timestamp_ms=0)  # baseline, heading north
    x, y = est.update(yaw_rad=math.pi / 2, ground_speed_mps=2.0, timestamp_ms=1000)  # 1s @ 2 m/s north
    assert x == pytest.approx(0.0, abs=1e-9)
    assert y == pytest.approx(2.0)


def test_seed_re_zeros_and_resets_dt_baseline():
    est = DeadReckoningEstimator()
    est.update(yaw_rad=0.0, ground_speed_mps=1.0, timestamp_ms=0)
    est.update(yaw_rad=0.0, ground_speed_mps=1.0, timestamp_ms=1000)
    assert est.x == pytest.approx(1.0)

    est.seed(5.0, 7.0)
    assert (est.x, est.y) == (5.0, 7.0)
    # Next update must not use the stale timestamp from before seeding to
    # compute a huge/garbage dt.
    x, y = est.update(yaw_rad=0.0, ground_speed_mps=1.0, timestamp_ms=1050)
    assert (x, y) == (5.0, 7.0)  # this call only establishes the new baseline


def test_ignores_negative_or_out_of_order_dt():
    est = DeadReckoningEstimator()
    est.update(yaw_rad=0.0, ground_speed_mps=1.0, timestamp_ms=1000)
    x, y = est.update(yaw_rad=0.0, ground_speed_mps=1.0, timestamp_ms=900)  # earlier timestamp
    assert (x, y) == (0.0, 0.0)


def test_ignores_absurdly_large_dt_gap():
    est = DeadReckoningEstimator()
    est.update(yaw_rad=0.0, ground_speed_mps=1.0, timestamp_ms=0)
    # A 5-second gap between samples shouldn't fling the estimate 5 meters
    # in one jump — treat it as a bad/missing sample instead.
    x, y = est.update(yaw_rad=0.0, ground_speed_mps=1.0, timestamp_ms=5000)
    assert (x, y) == (0.0, 0.0)
