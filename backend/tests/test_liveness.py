from app.services.liveness_service import liveness_service


def test_count_blinks_detects_dip():
    ears = [0.30, 0.31, 0.30, 0.18, 0.19, 0.30, 0.31, 0.30]
    assert liveness_service._count_blinks(ears) >= 1


def test_count_blinks_still_face():
    assert liveness_service._count_blinks([0.30] * 12) == 0


def test_count_blinks_low_baseline_face():
    # Narrow eyes: baseline 0.22; a dip to 0.15 must still register.
    ears = [0.22, 0.22, 0.22, 0.15, 0.22]
    assert liveness_service._count_blinks(ears) == 1


def test_count_blinks_empty():
    assert liveness_service._count_blinks([]) == 0
