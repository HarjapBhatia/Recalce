"""
app/services/anomaly_service.py
---------------------------------
Loads pre-trained IsolationForest models and scores transactions for anomalies.

Architecture
------------
Two separate models are maintained because matched and unmatched records have
different feature sets (different column counts), and a single IsolationForest
instance expects a fixed input shape:

  model_matched.pkl   -- 6 features: amount, hour_of_day, day_of_week,
                          merchant_freq, fee_ratio, settle_delay
  model_unmatched.pkl -- 5 features: amount, hour_of_day, day_of_week,
                          merchant_freq, amount_zscore

Both models are loaded exactly once per Celery worker process at startup via
the `worker_process_init` signal in app/core/celery_app.py. They are then
shared across all task invocations within that process. Loading once avoids
the 50-100ms disk read penalty on every batch.

Threshold handling
------------------
The IsolationForest models were calibrated during training using
ml/calibration.py. The calibration stored the optimal score cutoff directly
into `model.offset_` via `apply_score_threshold()`. This means calling
`model.predict(X)` already uses the calibrated threshold without any
additional configuration here. We expose `predict_matched()` and
`predict_unmatched()` which return +1 (normal) or -1 (anomaly) per row,
and `score_matched()` / `score_unmatched()` which return the raw float scores
for logging and debugging purposes.
"""

import logging
from pathlib import Path

import joblib
import numpy as np

logger = logging.getLogger(__name__)

# Anchor model discovery to the backend package, not the caller's working
# directory. This works from both the repository root and backend/.
_MODEL_DIR = Path(__file__).resolve().parents[2] / "ml" / "models"

_model_matched = None
_model_unmatched = None


def load_models() -> None:
    """
    Deserialize both IsolationForest models from disk into module-level globals.

    This must be called once before any scoring functions are used. The Celery
    worker calls this via the worker_process_init signal in celery_app.py.
    FastAPI workers do not call this because the upload endpoint itself does
    not score records -- scoring is deferred entirely to the Celery ml_triage
    task.

    Raises FileNotFoundError if the model files are missing from ml/models/.
    """
    global _model_matched, _model_unmatched

    matched_path = _MODEL_DIR / "model_matched.pkl"
    unmatched_path = _MODEL_DIR / "model_unmatched.pkl"

    if not matched_path.exists():
        raise FileNotFoundError(
            f"Matched model not found at {matched_path}. "
            "Run `python ml/train.py` from the backend directory to train and save the models."
        )
    if not unmatched_path.exists():
        raise FileNotFoundError(
            f"Unmatched model not found at {unmatched_path}. "
            "Run `python ml/train.py` from the backend directory to train and save the models."
        )

    _model_matched = joblib.load(matched_path)
    _model_unmatched = joblib.load(unmatched_path)
    logger.info("ML models loaded from %s", _MODEL_DIR)


def _assert_loaded() -> None:
    """Raise RuntimeError if load_models() has not been called yet."""
    if _model_matched is None or _model_unmatched is None:
        raise RuntimeError(
            "Anomaly models are not loaded. "
            "Ensure load_models() is called at worker startup."
        )


def predict_matched(features: np.ndarray) -> np.ndarray:
    """
    Classify matched records using the calibrated matched model.

    Returns an integer array of shape (n_samples,) where:
      -1 means the record is flagged as an anomaly
      +1 means the record appears normal

    The IsolationForest.predict() method applies the score threshold that was
    baked into model.offset_ during training calibration, so no manual
    threshold comparison is needed here.
    """
    _assert_loaded()
    return _model_matched.predict(features)


def predict_unmatched(features: np.ndarray) -> np.ndarray:
    """
    Classify unmatched internal ledger records using the calibrated unmatched model.

    Returns an integer array of shape (n_samples,) where:
      -1 means the record is flagged as an anomaly
      +1 means the record appears normal
    """
    _assert_loaded()
    return _model_unmatched.predict(features)


def score_matched(features: np.ndarray) -> list[float]:
    """
    Return raw anomaly scores for matched records.

    Lower scores indicate more anomalous records. These are the raw
    score_samples values, not predictions. Useful for logging and debugging
    when you want to see how close a record is to the decision boundary.
    """
    _assert_loaded()
    return _model_matched.score_samples(features).tolist()


def score_unmatched(features: np.ndarray) -> list[float]:
    """
    Return raw anomaly scores for unmatched records.

    Lower scores indicate more anomalous records.
    """
    _assert_loaded()
    return _model_unmatched.score_samples(features).tolist()
