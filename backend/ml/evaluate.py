"""
ml/evaluate.py
--------------
Evaluate both models against the test set using ground_truth.csv.

Reports: Precision, Recall, F1, PR-AUC
Does NOT use accuracy (misleading under 5% anomaly rate).

Usage:
  python ml/evaluate.py
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    precision_recall_fscore_support,
)
from dotenv import load_dotenv

from ml.features import matched_features, unmatched_features
from ml.train import _simple_waterfall

load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR / "ml" / "data"
MODELS_DIR = BACKEND_DIR / "ml" / "models"
OUT_DIR = BACKEND_DIR / "ml" / "data"


ANOMALY_BUCKETS = {"anomaly"}
DATABASE_RULE_BUCKETS = {"duplicate", "ambiguous"}


def load_ground_truth_labels(gt_df: pd.DataFrame, txn_ids: pd.Series) -> np.ndarray:
    """Map transaction IDs to binary labels: 1 = anomaly, 0 = normal."""
    gt_map = gt_df.set_index("transaction_id")["bucket"].to_dict()
    return np.array([
        1 if gt_map.get(tid, "normal") in ANOMALY_BUCKETS else 0
        for tid in txn_ids
    ])


def ml_eligibility_mask(gt_df: pd.DataFrame, txn_ids: pd.Series) -> pd.Series:
    """Mirror rows removed by deterministic PostgreSQL anomaly queries."""
    gt = gt_df.set_index("transaction_id")
    if "ml_eligible" in gt.columns:
        return txn_ids.map(gt["ml_eligible"]).fillna(False).astype(bool)
    return txn_ids.map(
        lambda transaction_id: gt.at[transaction_id, "bucket"]
        not in DATABASE_RULE_BUCKETS
    ).astype(bool)


def evaluate():
    print("[evaluate] Loading test data ...")
    ledger = pd.read_csv(DATA_DIR / "test_ledger.csv",       dtype={"amount": str})
    bank   = pd.read_csv(DATA_DIR / "test_bank.csv",         dtype={"deposit_amount": str})
    gt     = pd.read_csv(DATA_DIR / "test_ground_truth.csv")

    matched_df, unmatched_df = _simple_waterfall(ledger, bank)

    results = {}

    # Rule-resolved rows are deliberately excluded before ML feature creation.
    # In production the equivalent decision comes from PostgreSQL, not labels.
    matched_mask = ml_eligibility_mask(gt, matched_df["transaction_id"])
    unmatched_mask = ml_eligibility_mask(gt, unmatched_df["transaction_id"])
    matched_df = matched_df.loc[matched_mask].reset_index(drop=True)
    unmatched_df = unmatched_df.loc[unmatched_mask].reset_index(drop=True)

    # ── Matched model ─────────────────────────────────────────────────────────
    if not matched_df.empty and (MODELS_DIR / "model_matched.pkl").exists():
        model = joblib.load(MODELS_DIR / "model_matched.pkl")
        X = matched_features(matched_df)
        scores = model.score_samples(X)          # continuous, lower = more anomalous
        preds  = (model.predict(X) == -1).astype(int)  # -1 = anomaly
        y_true = load_ground_truth_labels(gt, matched_df["transaction_id"])

        pr_auc = average_precision_score(y_true, -scores) if y_true.sum() > 0 else 0.0
        p, r, f, _ = precision_recall_fscore_support(y_true, preds, average="binary", zero_division=0)

        results["matched"] = {
            "n_samples": len(X),
            "n_anomalies_true": int(y_true.sum()),
            "n_flagged": int(preds.sum()),
            "precision": round(float(p), 4),
            "recall":    round(float(r), 4),
            "f1":        round(float(f), 4),
            "pr_auc":    round(float(pr_auc), 4),
        }
        print(f"\n[evaluate] Matched model:\n  {results['matched']}")
    else:
        print("[evaluate] model_matched.pkl not found or no matched rows — skipping")

    # ── Unmatched model ───────────────────────────────────────────────────────
    if not unmatched_df.empty and (MODELS_DIR / "model_unmatched.pkl").exists():
        model = joblib.load(MODELS_DIR / "model_unmatched.pkl")
        X = unmatched_features(unmatched_df)
        scores = model.score_samples(X)
        preds  = (model.predict(X) == -1).astype(int)
        y_true = load_ground_truth_labels(gt, unmatched_df["transaction_id"])

        pr_auc = average_precision_score(y_true, -scores) if y_true.sum() > 0 else 0.0
        p, r, f, _ = precision_recall_fscore_support(y_true, preds, average="binary", zero_division=0)

        results["unmatched"] = {
            "n_samples": len(X),
            "n_anomalies_true": int(y_true.sum()),
            "n_flagged": int(preds.sum()),
            "precision": round(float(p), 4),
            "recall":    round(float(r), 4),
            "f1":        round(float(f), 4),
            "pr_auc":    round(float(pr_auc), 4),
        }
        print(f"\n[evaluate] Unmatched model:\n  {results['unmatched']}")
    else:
        print("[evaluate] model_unmatched.pkl not found or no unmatched rows — skipping")

    # ── Save results ──────────────────────────────────────────────────────────
    out_path = OUT_DIR / "evaluation_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[evaluate] Results written to {out_path}")


if __name__ == "__main__":
    evaluate()
