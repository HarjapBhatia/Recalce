"""
ml/features.py
---------------
Feature engineering for IsolationForest models.

All functions accept pandas DataFrames and return float arrays
suitable for scikit-learn. Amounts are cast to float only here —
nowhere else in the pipeline.

Two feature sets (different dimensionality → two separate models):
  - matched_features()   → [amount, hour_of_day, day_of_week, merchant_freq, fee_ratio, settle_delay]
  - unmatched_features() → [amount, hour_of_day, day_of_week, merchant_freq, amount_zscore]
"""

import numpy as np
import pandas as pd


def _merchant_frequency(df: pd.DataFrame) -> pd.Series:
    """Count of transactions per merchant_id in the batch."""
    freq = df["merchant_id"].value_counts()
    return df["merchant_id"].map(freq).astype(float)


def minimum_transactions_for_zscore(df: pd.DataFrame) -> int:
    """Derive the merchant-history length needed for a stable standard deviation.

    For each merchant, compare the sample standard deviation at `n` transactions
    with the value after the next transaction is added. The first change below
    10 percent is the merchant's stability point. The returned median is an
    integer constrained to a practical range. If no merchant has four records,
    the fallback scales with the current batch size instead of using a fixed
    transaction count.
    """
    if df.empty:
        return 3

    columns = ["merchant_id", "amount"]
    histories = df[columns].copy()
    if "timestamp" in df.columns:
        histories["timestamp"] = pd.to_datetime(df["timestamp"])
        histories = histories.sort_values(["merchant_id", "timestamp"])
    else:
        histories = histories.sort_values(["merchant_id"])

    stability_points: list[int] = []
    for _, merchant_history in histories.groupby("merchant_id", sort=False):
        values = merchant_history["amount"].astype(float).to_numpy()
        if len(values) < 4:
            continue

        current_std = float(np.std(values[:3], ddof=1))
        for n in range(3, len(values)):
            next_std = float(np.std(values[: n + 1], ddof=1))
            if current_std <= 1e-9:
                relative_change = 0.0 if next_std <= 1e-9 else np.inf
            else:
                relative_change = abs(next_std - current_std) / current_std

            if relative_change < 0.10:
                stability_points.append(n)
                break
            current_std = next_std

    if stability_points:
        return int(np.clip(np.ceil(np.median(stability_points)), 3, 15))

    return int(np.clip(np.ceil(np.sqrt(len(df))), 3, 15))


def _safe_std(values: pd.Series) -> float:
    """Return a finite, non-zero sample standard deviation."""
    std = float(values.astype(float).std(ddof=1))
    return std if np.isfinite(std) and std > 1e-9 else 1e-9


def _amount_zscore_per_merchant(
    df: pd.DataFrame, min_txns: int | None = None
) -> pd.Series:
    """
    Z-score of amount within each merchant's transactions.
    The minimum history length is derived from the current data when it is not
    supplied. Merchants below that threshold use the batch-wide distribution.
    """
    amounts = df["amount"].astype(float)
    batch_mean = amounts.mean()
    batch_std = _safe_std(amounts)
    min_txns = minimum_transactions_for_zscore(df) if min_txns is None else min_txns

    scores = pd.Series(index=df.index, dtype=float)
    for merchant, grp in df.groupby("merchant_id"):
        if len(grp) >= min_txns:
            m = grp["amount"].astype(float).mean()
            s = _safe_std(grp["amount"])
        else:
            m, s = batch_mean, batch_std
        scores.loc[grp.index] = (grp["amount"].astype(float) - m) / s

    return scores


def matched_features(matched_df: pd.DataFrame) -> np.ndarray:
    """
    Build feature matrix for matched records.

    Required columns: amount, timestamp, merchant_id, fee_deducted, settlement_delay_days
    Returns shape: (n_samples, 6)
    """
    df = matched_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    features = pd.DataFrame({
        "amount":           df["amount"].astype(float),
        "hour_of_day":      df["timestamp"].dt.hour.astype(float),
        "day_of_week":      df["timestamp"].dt.dayofweek.astype(float),
        "merchant_freq":    _merchant_frequency(df),
        "fee_ratio":        df["fee_deducted"].astype(float) / df["amount"].astype(float).clip(lower=1e-9),
        "settle_delay":     df["settlement_delay_days"].astype(float),
    })
    return features.to_numpy()


def unmatched_features(unmatched_df: pd.DataFrame) -> np.ndarray:
    """
    Build feature matrix for unmatched records.

    Required columns: amount, timestamp, merchant_id
    Returns shape: (n_samples, 5)
    """
    df = unmatched_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    features = pd.DataFrame({
        "amount":        df["amount"].astype(float),
        "hour_of_day":   df["timestamp"].dt.hour.astype(float),
        "day_of_week":   df["timestamp"].dt.dayofweek.astype(float),
        "merchant_freq": _merchant_frequency(df),
        "amount_zscore": _amount_zscore_per_merchant(df),
    })
    return features.to_numpy()
