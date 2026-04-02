from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from django.db import transaction
from django.utils import timezone

from apps.events.models import Announcement, NewsItem
from apps.market.models import Ohlc1m

from .models import PricePrediction, PricePredictionRun


FEATURE_COLUMNS = [
    # Price returns at multiple lags
    'r1', 'r5', 'r15', 'r60', 'r120',
    # Rolling return volatility (std of 1m returns)
    'vol_std_5', 'vol_std_15', 'vol_std_60', 'vol_std_120',
    # Rolling momentum (cumulative 1m returns)
    'mom_15', 'mom_60', 'mom_120',
    # Rolling mean high-low range ratio
    'range_mean_15', 'range_mean_60', 'range_mean_120',
    # Volume z-scores (normalised — replaces raw vol_mean which was scale-distorting)
    'vol_z_15', 'vol_z_60', 'vol_z_120',
    # Technical indicators
    'rsi_14',     # RSI via Wilder EMA
    'atr_pct',    # ATR as % of close (scale-invariant volatility)
    'macd_hist',  # MACD histogram / close (normalised momentum signal)
    'bb_pct_b',   # Bollinger Band %B (0 = lower, 0.5 = mid, 1 = upper)
    # Intraday context
    'vwap_dist',        # Close vs session VWAP (intraday mean reversion)
    'open_to_now_ret',  # Return from session open to current close
    # Announcement event features
    'ann_high_count_2h', 'ann_high_count_24h', 'ann_high_count_7d',
    'ann_high_sum_2h', 'ann_high_sum_24h', 'ann_high_sum_7d',
    'ann_last_impact', 'ann_results_flag_7d',
    # News sentiment features
    'news_count_2h', 'news_count_24h',
    'news_sent_avg_2h', 'news_sent_avg_24h',
]

HORIZONS = {
    '1h': 60,
    '3h': 180,
    '5h': 300,
    '1d': 1440,
}

# Out-of-sample residual baseline per horizon.
# Residual at this level → 0 confidence; 0 residual → 1.0 confidence.
_CONFIDENCE_BASELINES = {
    60: 0.005,    # 1h: 0.5% OOS residual = confidence 0
    180: 0.008,   # 3h
    300: 0.010,   # 5h
    1440: 0.020,  # 1d
}


@dataclass
class ModelBundle:
    model: object
    model_name: str
    mean: Optional[np.ndarray]
    std: Optional[np.ndarray]
    feature_names: List[str]
    samples: int
    residual_std: Optional[float]

    def _transform(self, X: np.ndarray) -> np.ndarray:
        if self.mean is None or self.std is None:
            return X
        return (X - self.mean) / self.std

    def predict(self, x: np.ndarray) -> float:
        x = np.asarray(x, dtype=float)
        return float(self.model.predict([self._transform(x)])[0])

    def predict_many(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=float)
        return np.asarray(self.model.predict(self._transform(X)))


# ──────────────────────────── Ridge helpers ──────────────────────────────────

def _normalize_features(X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std = np.where(std == 0, 1.0, std)
    return (X - mean) / std, mean, std


def _fit_ridge(X: np.ndarray, y: np.ndarray, alpha: float = 1.0) -> Tuple[np.ndarray, float]:
    Xb = np.concatenate([np.ones((X.shape[0], 1)), X], axis=1)
    eye = np.eye(Xb.shape[1])
    eye[0, 0] = 0.0
    beta = np.linalg.solve(Xb.T @ Xb + alpha * eye, Xb.T @ y)
    return beta[1:], float(beta[0])


def _fit_ridge_bundle(X: np.ndarray, y: np.ndarray) -> ModelBundle:
    n = len(X)
    split = max(30, int(n * 0.8))

    # Out-of-sample estimate using held-out 20%
    Xn_tr, mean_tr, std_tr = _normalize_features(X[:split])
    coef_tr, intercept_tr = _fit_ridge(Xn_tr, y[:split])

    class _Linear:
        def __init__(self, coef, intercept):
            self.coef = coef
            self.intercept = intercept

        def predict(self, X):
            return np.asarray(X) @ self.coef + self.intercept

    val_model = _Linear(coef_tr, intercept_tr)
    if split < n:
        Xn_val = (X[split:] - mean_tr) / std_tr
        residual_std = float(np.std(y[split:] - val_model.predict(Xn_val)))
    else:
        residual_std = float(np.std(y[:split] - val_model.predict(Xn_tr)))

    # Final model trained on all data for best predictions
    Xn_full, mean_full, std_full = _normalize_features(X)
    coef_full, intercept_full = _fit_ridge(Xn_full, y)
    final_model = _Linear(coef_full, intercept_full)

    return ModelBundle(
        model=final_model,
        model_name='ridge_v2',
        mean=mean_full,
        std=std_full,
        feature_names=list(FEATURE_COLUMNS),
        samples=n,
        residual_std=residual_std,
    )


def _fit_gbr_bundle(X: np.ndarray, y: np.ndarray) -> Optional[ModelBundle]:
    try:
        from sklearn.ensemble import GradientBoostingRegressor
    except ImportError:
        return None

    n = len(X)
    split = max(50, int(n * 0.8))

    params = dict(
        n_estimators=100,
        learning_rate=0.05,
        max_depth=2,          # Reduced from 3 — prevents leaf memorisation
        min_samples_leaf=20,  # Each leaf needs >= 20 observations
        subsample=0.6,        # Strong stochastic regularisation
        max_features='sqrt',  # Feature subsampling per split
        random_state=42,
    )

    # Fit on 80% to get an honest out-of-sample residual estimate
    val_model = GradientBoostingRegressor(**params)
    val_model.fit(X[:split], y[:split])
    if split < n:
        val_preds = val_model.predict(X[split:])
        residual_std = float(np.std(y[split:] - val_preds))
    else:
        residual_std = None

    # Final model on 100% of data for best predictions
    final_model = GradientBoostingRegressor(**params)
    final_model.fit(X, y)

    return ModelBundle(
        model=final_model,
        model_name='gbr_v2',
        mean=None,
        std=None,
        feature_names=list(FEATURE_COLUMNS),
        samples=n,
        residual_std=residual_std,
    )


# ─────────────────────── Technical indicator helpers ─────────────────────────

def _rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI using Wilder's EMA (alpha = 1/period). Returns values in [0, 100].

    Uses a small epsilon floor on avg_loss so that pure-uptrend sessions
    correctly return RSI ≈ 100 rather than NaN→50.
    """
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    alpha = 1.0 / period
    avg_gain = gain.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    # clip to a tiny epsilon: pure uptrend → RS very large → RSI ≈ 100
    rs = avg_gain / avg_loss.clip(lower=1e-10)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    # Restore NaN for periods that lack sufficient history (min_periods not met)
    return rsi.where(avg_gain.notna(), other=50.0)


def _atr_pct_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR as percentage of close price — scale-invariant volatility."""
    high, low, prev_close = df['high'], df['low'], df['close'].shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    return (atr / df['close'].replace(0.0, np.nan)).fillna(0.0)


def _macd_hist_series(close: pd.Series) -> pd.Series:
    """MACD histogram normalised by price — scale-free momentum signal."""
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return ((macd - signal) / close.replace(0.0, np.nan)).fillna(0.0)


def _bb_pct_b_series(close: pd.Series, period: int = 20) -> pd.Series:
    """Bollinger Band %B: 0 = lower band, 0.5 = midline, 1 = upper band."""
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = mid + 2.0 * std
    lower = mid - 2.0 * std
    band = (upper - lower).replace(0.0, np.nan)
    return ((close - lower) / band).fillna(0.5)


# ─────────────────────────── Event feature helpers ───────────────────────────

def _build_cumulative_window(
    ts_index: pd.DatetimeIndex,
    events_df: pd.DataFrame,
    value_col: str,
    window: pd.Timedelta,
) -> np.ndarray:
    """Sum of events_df[value_col] in (ts - window, ts] for each ts in ts_index."""
    if events_df.empty:
        return np.zeros(len(ts_index))

    df = events_df[['published_at', value_col]].copy()
    df['cum'] = df[value_col].cumsum()
    df = df.sort_values('published_at')

    ts_df = pd.DataFrame({'ts': ts_index})
    end = pd.merge_asof(ts_df, df[['published_at', 'cum']], left_on='ts', right_on='published_at', direction='backward')
    start_df = pd.DataFrame({'ts': ts_index - window})
    start = pd.merge_asof(start_df, df[['published_at', 'cum']], left_on='ts', right_on='published_at', direction='backward')

    return end['cum'].fillna(0.0).to_numpy() - start['cum'].fillna(0.0).to_numpy()


def _add_event_features(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    start_ts = df.index.min() - pd.Timedelta(days=7)
    end_ts = df.index.max()

    ann_qs = Announcement.objects.filter(
        published_at__gte=start_ts,
        published_at__lte=end_ts,
        low_priority=False,
    ).values('published_at', 'impact_score', 'type', 'headline')

    ann_df = pd.DataFrame(list(ann_qs))
    _zero_cols = (
        'ann_high_count_2h', 'ann_high_count_24h', 'ann_high_count_7d',
        'ann_high_sum_2h', 'ann_high_sum_24h', 'ann_high_sum_7d',
        'ann_last_impact', 'ann_results_flag_7d',
    )
    if ann_df.empty:
        for col in _zero_cols:
            df[col] = 0
        return df

    ann_df['published_at'] = pd.to_datetime(ann_df['published_at'], utc=True)
    ann_df = ann_df.sort_values('published_at')
    ann_df['high_flag'] = (ann_df['impact_score'] >= 10).astype(int)
    ann_df['headline_lower'] = ann_df['headline'].str.lower()
    ann_df['results_flag'] = (
        ann_df['type'].isin(['results', 'board_meeting'])
        & ann_df['headline_lower'].str.contains('financial|results', regex=True)
    ).astype(int)

    ts_index = df.index
    df['ann_high_count_2h'] = _build_cumulative_window(ts_index, ann_df, 'high_flag', pd.Timedelta(hours=2))
    df['ann_high_count_24h'] = _build_cumulative_window(ts_index, ann_df, 'high_flag', pd.Timedelta(hours=24))
    df['ann_high_count_7d'] = _build_cumulative_window(ts_index, ann_df, 'high_flag', pd.Timedelta(days=7))
    df['ann_high_sum_2h'] = _build_cumulative_window(ts_index, ann_df, 'impact_score', pd.Timedelta(hours=2))
    df['ann_high_sum_24h'] = _build_cumulative_window(ts_index, ann_df, 'impact_score', pd.Timedelta(hours=24))
    df['ann_high_sum_7d'] = _build_cumulative_window(ts_index, ann_df, 'impact_score', pd.Timedelta(days=7))
    df['ann_results_flag_7d'] = (
        _build_cumulative_window(ts_index, ann_df, 'results_flag', pd.Timedelta(days=7)) > 0
    ).astype(int)

    last = pd.merge_asof(
        pd.DataFrame({'ts': ts_index}),
        ann_df[['published_at', 'impact_score']],
        left_on='ts',
        right_on='published_at',
        direction='backward',
    )
    df['ann_last_impact'] = last['impact_score'].fillna(0.0).to_numpy()
    return df


def _add_news_features(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    start_ts = df.index.min() - pd.Timedelta(days=1)
    end_ts = df.index.max()
    news_qs = NewsItem.objects.filter(
        published_at__gte=start_ts,
        published_at__lte=end_ts,
    ).values('published_at', 'sentiment')

    news_df = pd.DataFrame(list(news_qs))
    if news_df.empty:
        for col in ('news_count_2h', 'news_count_24h', 'news_sent_avg_2h', 'news_sent_avg_24h'):
            df[col] = 0
        return df

    news_df['published_at'] = pd.to_datetime(news_df['published_at'], utc=True)
    news_df = news_df.sort_values('published_at')
    news_df['count_flag'] = 1
    news_df['sent_sum'] = news_df['sentiment']

    ts_index = df.index
    count_2h = _build_cumulative_window(ts_index, news_df, 'count_flag', pd.Timedelta(hours=2))
    count_24h = _build_cumulative_window(ts_index, news_df, 'count_flag', pd.Timedelta(hours=24))
    sum_2h = _build_cumulative_window(ts_index, news_df, 'sent_sum', pd.Timedelta(hours=2))
    sum_24h = _build_cumulative_window(ts_index, news_df, 'sent_sum', pd.Timedelta(hours=24))

    df['news_count_2h'] = count_2h
    df['news_count_24h'] = count_24h
    df['news_sent_avg_2h'] = np.where(count_2h > 0, sum_2h / count_2h, 0.0)
    df['news_sent_avg_24h'] = np.where(count_24h > 0, sum_24h / count_24h, 0.0)
    return df


# ──────────────────────────── Feature dataframe ──────────────────────────────

def build_features_dataframe(start_ts, end_ts) -> pd.DataFrame:
    qs = Ohlc1m.objects.filter(ts__gte=start_ts, ts__lte=end_ts).order_by('ts').values(
        'ts', 'open', 'high', 'low', 'close', 'volume'
    )
    rows = list(qs)
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['ts'] = pd.to_datetime(df['ts'], utc=True)
    df = df.set_index('ts').sort_index()

    # ── Price returns ──
    df['r1'] = df['close'].pct_change(1)
    df['r5'] = df['close'].pct_change(5)
    df['r15'] = df['close'].pct_change(15)
    df['r60'] = df['close'].pct_change(60)
    df['r120'] = df['close'].pct_change(120)

    # ── Return volatility ──
    df['vol_std_5'] = df['r1'].rolling(5).std()
    df['vol_std_15'] = df['r1'].rolling(15).std()
    df['vol_std_60'] = df['r1'].rolling(60).std()
    df['vol_std_120'] = df['r1'].rolling(120).std()

    # ── Momentum ──
    df['mom_15'] = df['r1'].rolling(15).sum()
    df['mom_60'] = df['r1'].rolling(60).sum()
    df['mom_120'] = df['r1'].rolling(120).sum()

    # ── Price range ratio ──
    rng = (df['high'] - df['low']) / df['close'].replace(0.0, np.nan)
    df['range_mean_15'] = rng.rolling(15).mean()
    df['range_mean_60'] = rng.rolling(60).mean()
    df['range_mean_120'] = rng.rolling(120).mean()

    # ── Volume z-scores (normalised, scale-invariant) ──
    for w in (15, 60, 120):
        vmean = df['volume'].rolling(w).mean()
        vstd = df['volume'].rolling(w).std().replace(0.0, np.nan)
        df[f'vol_z_{w}'] = ((df['volume'] - vmean) / vstd).fillna(0.0)

    # ── Technical indicators ──
    df['rsi_14'] = _rsi_series(df['close'])
    df['atr_pct'] = _atr_pct_series(df)
    df['macd_hist'] = _macd_hist_series(df['close'])
    df['bb_pct_b'] = _bb_pct_b_series(df['close'])

    # ── Intraday context (session-scoped, resets at IST 09:15 each day) ──
    ist = ZoneInfo('Asia/Kolkata')
    session_key = pd.Series(df.index.tz_convert(ist).date, index=df.index)

    # VWAP = cumulative(typical_price * volume) / cumulative(volume) within session
    vol_clipped = df['volume'].clip(lower=0.0)
    tp = (df['high'] + df['low'] + df['close']) / 3.0
    cum_tp_vol = (tp * vol_clipped).groupby(session_key).cumsum()
    cum_vol = vol_clipped.groupby(session_key).cumsum()
    vwap = cum_tp_vol / cum_vol.replace(0.0, np.nan)
    df['vwap_dist'] = ((df['close'] - vwap) / df['close'].replace(0.0, np.nan)).fillna(0.0)

    # Return from the first candle of the session to current close
    session_open = df['open'].groupby(session_key).transform('first')
    df['open_to_now_ret'] = ((df['close'] - session_open) / session_open.replace(0.0, np.nan)).fillna(0.0)

    df = _add_event_features(df)
    df = _add_news_features(df)

    return df


def build_labels(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()
    df['y_1h'] = df['close'].shift(-60) / df['close'] - 1.0
    df['y_3h'] = df['close'].shift(-180) / df['close'] - 1.0
    df['y_5h'] = df['close'].shift(-300) / df['close'] - 1.0

    ist = ZoneInfo('Asia/Kolkata')
    df['local_date'] = df.index.tz_convert(ist).date
    last_close_by_date = df.groupby('local_date')['close'].last()
    dates_sorted = sorted(last_close_by_date.index)
    next_date_map = {dates_sorted[i]: dates_sorted[i + 1] for i in range(len(dates_sorted) - 1)}
    df['next_date'] = df['local_date'].map(next_date_map)
    df['next_close'] = df['next_date'].map(last_close_by_date)
    df['y_1d'] = df['next_close'] / df['close'] - 1.0

    return df


def train_models(df: pd.DataFrame) -> Dict[str, Optional[ModelBundle]]:
    if df.empty:
        return {k: None for k in HORIZONS}

    # Exclude synthetic gap-fill candles (volume == 0 from DataQualityEngine) from training.
    # They stay in the DataFrame for rolling-window continuity but must not appear
    # as training samples since they have artificial feature values.
    df_real = df[df['volume'] > 0] if 'volume' in df.columns else df

    models: Dict[str, Optional[ModelBundle]] = {}
    for label in HORIZONS:
        y_col = f'y_{label}'
        subset = df_real.dropna(subset=FEATURE_COLUMNS + [y_col])
        if len(subset) < 500:
            models[label] = None
            continue

        X = subset[FEATURE_COLUMNS].to_numpy(dtype=float)
        y = subset[y_col].to_numpy(dtype=float)

        model = _fit_gbr_bundle(X, y)
        if model is None:
            model = _fit_ridge_bundle(X, y)
        models[label] = model

    return models


def _confidence_from_residual(residual_std: Optional[float], horizon_min: int = 60) -> Optional[float]:
    """Convert out-of-sample residual std to a [0, 1] confidence score per horizon."""
    if residual_std is None:
        return None
    baseline = _CONFIDENCE_BASELINES.get(horizon_min, 0.01)
    score = 1.0 - min(1.0, residual_std / baseline)
    return round(max(0.0, score), 4)


def generate_latest_predictions() -> List[PricePrediction]:
    latest = Ohlc1m.objects.order_by('-ts').first()
    if not latest:
        return []

    start_ts = latest.ts - timedelta(days=180)
    df = build_features_dataframe(start_ts, latest.ts)
    df = build_labels(df)
    models = train_models(df)

    if df.empty:
        return []

    latest_row = df.iloc[-1]
    predictions = []

    with transaction.atomic():
        for label, horizon in HORIZONS.items():
            model = models.get(label)
            feature_vals = latest_row[FEATURE_COLUMNS].to_numpy(dtype=float)
            if model is None or np.isnan(feature_vals).any():
                predicted_return = 0.0
                model_name = 'baseline_v1'
                confidence = None
            else:
                predicted_return = model.predict(feature_vals)
                model_name = model.model_name
                confidence = _confidence_from_residual(model.residual_std, horizon)

            predicted_price = float(latest_row['close']) * (1.0 + predicted_return)
            obj, _created = PricePrediction.objects.update_or_create(
                ts=latest.ts,
                horizon_min=horizon,
                defaults={
                    'predicted_return': float(predicted_return),
                    'predicted_price': float(predicted_price),
                    'last_close': float(latest_row['close']),
                    'model_name': model_name,
                    'confidence': confidence,
                },
            )
            predictions.append(obj)

    return predictions


def run_backtest_and_store(
    train_days: int = 60,
    test_days: int = 5,
) -> Optional[PricePredictionRun]:
    latest = Ohlc1m.objects.order_by('-ts').first()
    if not latest:
        return None

    start_ts = latest.ts - timedelta(days=240)
    df = build_features_dataframe(start_ts, latest.ts)
    df = build_labels(df)
    if df.empty:
        return None

    ist = ZoneInfo('Asia/Kolkata')
    df = df.copy()
    df['local_date'] = df.index.tz_convert(ist).date
    dates = sorted(df['local_date'].unique())
    if len(dates) < train_days + test_days:
        return None

    metrics = {label: {'mae': 0.0, 'dir_acc': 0.0, 'n': 0, 'folds': 0} for label in HORIZONS}
    test_start_date = None
    test_end_date = None

    for i in range(train_days, len(dates) - test_days + 1, test_days):
        train_dates = set(dates[i - train_days: i])
        test_dates = set(dates[i: i + test_days])

        if test_start_date is None:
            test_start_date = min(test_dates)
        test_end_date = max(test_dates)

        # Exclude gap-fill candles from both train and test
        df_train = df[df['local_date'].isin(train_dates) & (df['volume'] > 0)]
        df_test = df[df['local_date'].isin(test_dates) & (df['volume'] > 0)]

        fold_models = train_models(df_train)
        for label in HORIZONS:
            y_col = f'y_{label}'
            test_subset = df_test.dropna(subset=FEATURE_COLUMNS + [y_col])
            if test_subset.empty:
                continue
            fold_model = fold_models.get(label)
            if fold_model is None:
                continue

            X = test_subset[FEATURE_COLUMNS].to_numpy(dtype=float)
            y_true = test_subset[y_col].to_numpy(dtype=float)
            preds = fold_model.predict_many(X)

            metrics[label]['mae'] += float(np.mean(np.abs(preds - y_true)))
            metrics[label]['dir_acc'] += float(np.mean(np.sign(preds) == np.sign(y_true)))
            metrics[label]['n'] += len(test_subset)
            metrics[label]['folds'] += 1

    metrics_summary = {}
    for label, stats in metrics.items():
        if stats['folds'] == 0:
            metrics_summary[label] = {'mae': None, 'directional_accuracy': None, 'samples': 0}
        else:
            metrics_summary[label] = {
                'mae': round(stats['mae'] / stats['folds'], 8),
                'directional_accuracy': round(stats['dir_acc'] / stats['folds'], 4),
                'samples': stats['n'],
            }

    # Resolve UTC datetimes for the test window boundaries
    test_start_dt = None
    test_end_dt = None
    if test_start_date is not None:
        rows = df[df['local_date'] == test_start_date]
        if not rows.empty:
            test_start_dt = rows.index.min().to_pydatetime()
    if test_end_date is not None:
        rows = df[df['local_date'] == test_end_date]
        if not rows.empty:
            test_end_dt = rows.index.max().to_pydatetime()

    run = PricePredictionRun.objects.create(
        train_start=df.index.min().to_pydatetime(),
        train_end=df.index.max().to_pydatetime(),
        test_start=test_start_dt,
        test_end=test_end_dt,
        status='ok',
        metrics_json=metrics_summary,
    )
    return run
