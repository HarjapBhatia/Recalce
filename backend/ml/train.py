"""
ml/train.py
-----------
Train two IsolationForest models on the generated training data.

Two separate models because matched and unmatched feature sets
have different dimensionality (different number of columns).

Usage:
  python ml/train.py

Outputs:
  ml/models/model_matched.pkl
  ml/models/model_unmatched.pkl
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.model_selection import train_test_split
from dotenv import load_dotenv

from ml.calibration import (
    apply_score_threshold,
    select_precision_first_threshold,
    validation_fraction,
)
from ml.features import matched_features, unmatched_features

load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR / "ml" / "data"
MODELS_DIR = BACKEND_DIR / "ml" / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

RANDOM_STATE = 42
ANOMALY_BUCKETS = {"anomaly"}
DATABASE_RULE_BUCKETS = {"duplicate", "ambiguous"}


def _simple_waterfall(ledger: pd.DataFrame, bank: pd.DataFrame):
    """
    Simplified in-memory waterfall for training data only.
    Returns (matched_df, unmatched_ledger_df).

    Not the production DB-backed implementation — just enough to
    produce matched/unmatched splits for feature engineering.
    """
    bank_idx = set(bank["bank_reference_id"].tolist())

    matched_rows = []
    unmatched_rows = []

    for _, row in ledger.iterrows():
        txn_id = row["transaction_id"]
        if txn_id in bank_idx:
            bank_row = bank[bank["bank_reference_id"] == txn_id].iloc[0]
            fee = float(row["amount"]) - float(bank_row["deposit_amount"])
            # Rough settle delay (days between timestamp and settlement_date)
            ts = pd.to_datetime(row["timestamp"])
            sd = pd.to_datetime(bank_row["settlement_date"])
            delay = max(0, (sd.date() - ts.date()).days)
            matched_rows.append({
                "transaction_id":      txn_id,
                "amount":              row["amount"],
                "timestamp":           row["timestamp"],
                "merchant_id":         row["merchant_id"],
                "fee_deducted":        max(0.0, fee),
                "settlement_delay_days": delay,
            })
        else:
            unmatched_rows.append(row.to_dict())

    matched_df   = pd.DataFrame(matched_rows)
    unmatched_df = pd.DataFrame(unmatched_rows) if unmatched_rows else pd.DataFrame(
        columns=["transaction_id", "amount", "timestamp", "merchant_id"]
    )
    return matched_df, unmatched_df


def _labels_and_eligibility(
    ground_truth: pd.DataFrame, transaction_ids: pd.Series
) -> tuple[np.ndarray, pd.Series]:
    """Return anomaly labels and rows not resolved by deterministic rules."""
    gt = ground_truth.set_index("transaction_id")
    labels = transaction_ids.map(
        lambda transaction_id: int(gt.at[transaction_id, "bucket"] in ANOMALY_BUCKETS)
    ).to_numpy(dtype=int)

    if "ml_eligible" in gt.columns:
        eligible = transaction_ids.map(gt["ml_eligible"]).fillna(False).astype(bool)
    else:
        eligible = transaction_ids.map(
            lambda transaction_id: gt.at[transaction_id, "bucket"]
            not in DATABASE_RULE_BUCKETS
        ).astype(bool)
    return labels, eligible


def _estimator_candidates(n_rows: int) -> list[int]:
    """Scale the tree-count search space with the current training population."""
    base = max(1, int(np.ceil(np.sqrt(n_rows))))
    return sorted({base, base * 2, base * 3})


def _fit_and_calibrate(
    X: np.ndarray, y: np.ndarray, model_name: str
) -> tuple[IsolationForest, dict]:
    """Fit unsupervised candidates and select a precision-first score cutoff."""
    if int(y.sum()) < 2:
        raise ValueError(
            f"{model_name} needs at least two ML-eligible anomaly rows for calibration."
        )

    X_train, X_validation, y_train, y_validation = train_test_split(
        X,
        y,
        test_size=validation_fraction(y),
        random_state=RANDOM_STATE,
        stratify=y,
    )

    candidates = []
    for n_estimators in _estimator_candidates(len(X_train)):
        candidate = IsolationForest(
            n_estimators=n_estimators,
            contamination="auto",
            random_state=RANDOM_STATE,
        )
        candidate.fit(X_train)
        calibration = select_precision_first_threshold(
            y_validation, -candidate.score_samples(X_validation)
        )
        candidates.append((candidate, calibration, n_estimators))
        print(
            f"[train] {model_name}: n={n_estimators}, "
            f"precision={calibration.precision:.3f}, "
            f"recall={calibration.recall:.3f}, "
            f"alert_rate={calibration.alert_rate:.3f}"
        )

    _, best_calibration, best_n_estimators = sorted(
        candidates,
        key=lambda item: (
            -item[1].precision,
            item[1].alert_rate,
            -item[1].f1,
            item[2],
        ),
    )[0]

    # Refit on all ML-eligible data without labels. Labels are used only to
    # calibrate the score cutoff, never to fit IsolationForest.
    final_model = IsolationForest(
        n_estimators=best_n_estimators,
        contamination="auto",
        random_state=RANDOM_STATE,
    )
    final_model.fit(X)
    final_calibration = select_precision_first_threshold(
        y_validation, -final_model.score_samples(X_validation)
    )
    apply_score_threshold(final_model, final_calibration.score_threshold)

    metadata = {
        "model": model_name,
        "n_estimators": best_n_estimators,
        "validation_fraction": validation_fraction(y),
        **final_calibration.to_dict(),
    }
    return final_model, metadata


def train():
    print("[train] Loading training data ...")
    ledger = pd.read_csv(DATA_DIR / "train_ledger.csv", dtype={"amount": str})
    bank   = pd.read_csv(DATA_DIR / "train_bank.csv",   dtype={"deposit_amount": str})
    ground_truth = pd.read_csv(DATA_DIR / "train_ground_truth.csv")

    print(f"[train] {len(ledger)} ledger rows, {len(bank)} bank rows")

    matched_df, unmatched_df = _simple_waterfall(ledger, bank)
    print(f"[train] {len(matched_df)} matched, {len(unmatched_df)} unmatched")

    calibration_metadata = {}
    for model_name, raw_df, feature_builder in [
        ("matched", matched_df, matched_features),
        ("unmatched", unmatched_df, unmatched_features),
    ]:
        if raw_df.empty:
            print(f"[train] WARNING: no {model_name} rows - skipping model")
            continue

        labels, eligible = _labels_and_eligibility(
            ground_truth, raw_df["transaction_id"]
        )
        eligible_df = raw_df.loc[eligible].reset_index(drop=True)
        eligible_labels = labels[eligible.to_numpy()]
        print(
            f"[train] {model_name}: {len(eligible_df)} ML-eligible rows, "
            f"{eligible_labels.sum()} labelled anomalies"
        )

        X = feature_builder(eligible_df)
        model, metadata = _fit_and_calibrate(X, eligible_labels, f"model_{model_name}")
        model_path = MODELS_DIR / f"model_{model_name}.pkl"
        joblib.dump(model, model_path)
        calibration_metadata[model_name] = metadata
        print(
            f"[train] {model_path.name} saved "
            f"(rows={len(X)}, features={X.shape[1]}, "
            f"precision={metadata['precision']:.3f}, "
            f"recall_floor={metadata['recall_floor']:.3f})"
        )

    with open(DATA_DIR / "model_calibration.json", "w") as file_handle:
        json.dump(calibration_metadata, file_handle, indent=2)
    print("[train] Calibration metadata written to model_calibration.json")

    print("[train] Done.")


if __name__ == "__main__":
    train()
