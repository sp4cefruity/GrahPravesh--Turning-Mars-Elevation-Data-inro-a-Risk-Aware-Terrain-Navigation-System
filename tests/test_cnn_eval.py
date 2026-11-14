"""Metric helpers for the CNN keep or drop run (specs/01-perception.md, CNN experiment)."""

import numpy as np
import pytest

from odyssey.perception.cnn_eval import expected_calibration_error, macro_f1


def test_ece_is_zero_when_probabilities_match_frequencies():
    p = np.array([0.0] * 50 + [1.0] * 50)
    y = np.array([0] * 50 + [1] * 50)
    assert expected_calibration_error(p, y) == pytest.approx(0.0)


def test_ece_catches_an_overconfident_wrong_model():
    assert expected_calibration_error(np.full(100, 0.9), np.zeros(100, dtype=int)) == pytest.approx(0.9)


def test_ece_catches_a_constant_half():
    y = np.array([1] * 100)
    assert expected_calibration_error(np.full(100, 0.5), y) == pytest.approx(0.5)


def test_macro_f1_averages_only_classes_that_exist_in_the_labels():
    y = np.array([0, 0, 1, 1])
    pred = np.array([0, 0, 1, 0])
    f1, per = macro_f1(y, pred, k=5)
    assert per[0] == pytest.approx(0.8) and per[1] == pytest.approx(2 / 3)
    assert np.isnan(per[2:]).all()
    assert f1 == pytest.approx((0.8 + 2 / 3) / 2)
