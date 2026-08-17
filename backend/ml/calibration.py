"""Validation-based threshold calibration for Recalce anomaly models.

IsolationForest remains unsupervised during fitting. This module uses labelled
synthetic validation data only to select the score cutoff applied after fitting.
The selected cutoff maximizes precision while meeting a data-dependent recall
safety floor.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import ceil, sqrt

import numpy as np
from sklearn.metrics import precision_recall_curve


@dataclass(frozen=True)
class CalibrationResult:
    """A score cutoff and the validation metrics that selected it."""

    score_threshold: float
    recall_floor: float
    precision: float
    recall: float
    f1: float
    alert_rate: float
    validation_anomalies: int
    validation_rows: int

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def validation_fraction(labels: np.ndarray) -> float:
    """Choose a validation share that contains roughly sqrt(positive) anomalies.

    This avoids a fixed validation percentage. The training portion remains
    larger than the validation portion whenever the data contains enough
    labelled anomalies to calibrate a score threshold.
    """
    positive_count = int(np.asarray(labels, dtype=int).sum())
    if positive_count < 2:
        raise ValueError(
            "At least two labelled anomalies are required for validation calibration."
        )

    validation_positives = int(ceil(sqrt(positive_count)))
    return min(0.5, validation_positives / positive_count)


def recall_safety_floor(labels: np.ndarray) -> float:
    """Require validation recall high enough to miss at most one anomaly.

    The floor is derived from the available validation anomalies instead of a
    fixed percentage. For example, 20 validation anomalies require 95 percent
    recall, while 40 require 97.5 percent recall.
    """
    positive_count = int(np.asarray(labels, dtype=int).sum())
    if positive_count < 2:
        raise ValueError(
            "At least two validation anomalies are required to derive a recall floor."
        )
    return (positive_count - 1) / positive_count


def select_precision_first_threshold(
    labels: np.ndarray,
    anomaly_scores: np.ndarray,
) -> CalibrationResult:
    """Select the most precise score cutoff that satisfies the recall floor.

    `anomaly_scores` must increase as a row becomes more anomalous. Every
    possible precision-recall threshold is evaluated. Among thresholds meeting
    the safety floor, precision is the primary objective, then lower alert rate,
    then F1. This directly addresses finance-team alert fatigue without allowing
    the calibrated threshold to miss more than one validation anomaly.
    """
    y_true = np.asarray(labels, dtype=int)
    scores = np.asarray(anomaly_scores, dtype=float)
    if len(y_true) != len(scores):
        raise ValueError("Labels and anomaly scores must have the same length.")
    if not np.isfinite(scores).all():
        raise ValueError("Anomaly scores must be finite for threshold calibration.")

    floor = recall_safety_floor(y_true)
    precision, recall, thresholds = precision_recall_curve(y_true, scores)
    candidates: list[CalibrationResult] = []

    # `precision` and `recall` have one extra point without a corresponding
    # threshold, so only iterate over indices present in `thresholds`.
    for index, threshold in enumerate(thresholds):
        candidate_precision = float(precision[index])
        candidate_recall = float(recall[index])
        if candidate_recall < floor:
            continue

        predicted = scores >= threshold
        alert_rate = float(predicted.mean())
        denominator = candidate_precision + candidate_recall
        f1 = (
            0.0
            if denominator == 0.0
            else 2 * candidate_precision * candidate_recall / denominator
        )
        candidates.append(
            CalibrationResult(
                score_threshold=float(threshold),
                recall_floor=float(floor),
                precision=candidate_precision,
                recall=candidate_recall,
                f1=float(f1),
                alert_rate=alert_rate,
                validation_anomalies=int(y_true.sum()),
                validation_rows=len(y_true),
            )
        )

    if not candidates:
        raise RuntimeError("No validation score threshold satisfied the recall safety floor.")

    return sorted(
        candidates,
        key=lambda result: (
            -result.precision,
            result.alert_rate,
            -result.f1,
            -result.score_threshold,
        ),
    )[0]


def apply_score_threshold(model, score_threshold: float) -> None:
    """Configure an IsolationForest instance so predict() uses this cutoff.

    IsolationForest predicts an anomaly when `score_samples(X) < offset_`.
    Calibration uses the inverse score (`-score_samples`) so higher scores are
    more anomalous. Setting `offset_` preserves the calibrated threshold when
    the model is serialized and later scored through `model.predict()`.
    """
    model.offset_ = -float(score_threshold)
