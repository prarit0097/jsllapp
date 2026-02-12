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
    'r1',
    'r5',
    'r15',
    'r60',
    'vol_std_5',
    'vol_std_15',
    'vol_std_60',
    'mom_15',
    'mom_60',
    'range_mean_15',
    'range_mean_60',
    'vol_mean_15',
    'vol_mean_60',
    'ann_high_count_24h',
    'ann_high_sum_24h',
    'ann_last_impact',
    'ann_results_flag_7d',
    'news_count_24h',
    'news_sent_avg_24h',
    'realized_vol_60m',
]

HORIZONS = {
    '1h': 60,
    '3h': 180,
    '5h': 300,
    '1d': 1440,
}


@dataclass
class ModelBundle:
    coef: np.ndarray
    intercept: float
    mean: np.ndarray
    std: np.ndarray
    feature_names: List[str]
    samples: int


def _normalize_features(X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std = np.where(std == 0, 1.0, std)
    Xn = (X - mean) / std
    return Xn, mean, std


def _fit_ridge(X: np.ndarray, y: np.ndarray, alpha: float = 1.0) -> Tuple[np.ndarray, float]:
    Xb = np.concatenate([np.ones((X.shape[0], 1)), X], axis=1)
    eye = np.eye(Xb.shape[1])
    eye[0, 0] = 0.0
    beta = np.linalg.solve(Xb.T @ Xb + alpha * eye, Xb.T @ y)
    intercept = float(beta[0])
    coef = beta[1:]
    return coef, intercept


def _predict(model: ModelBundle, x: np.ndarray) -> float:
    xn = (x - model.mean) / model.std
    return float(model.intercept + xn @ model.coef)


def _build_cumulative_window(ts_index, events_df, value_col, window):
    if events_df.empty:
        return np.zeros(len(ts_index))

    df = events_df.copy()
    df['cum'] = df[value_col].cumsum()
    df = df[['published_at', 'cum']].sort_values('published_at')

    ts_df = pd.DataFrame({'ts': ts_index})
    end = pd.merge_asof(ts_df, df, left_on='ts', right_on='published_at', direction='backward')
    start_df = pd.DataFrame({'ts': ts_index - window})
    start = pd.merge_asof(start_df, df, left_on='ts', right_on='published_at', direction='backward')

    end_val = end['cum'].fillna(0).to_numpy()
    start_val = start['cum'].fillna(0).to_numpy()
    return end_val - start_val


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
    if ann_df.empty:
        df['ann_high_count_24h'] = 0
        df['ann_high_sum_24h'] = 0.0
        df['ann_last_impact'] = 0.0
        df['ann_results_flag_7d'] = 0
        return df

    ann_df['published_at'] = pd.to_datetime(ann_df['published_at'], utc=True)
    ann_df = ann_df.sort_values('published_at')
    ann_df['high_flag'] = ann_df['impact_score'] >= 10
    ann_df['high_flag'] = ann_df['high_flag'].astype(int)

    ann_df['headline_lower'] = ann_df['headline'].str.lower()
    ann_df['results_flag'] = (
        ann_df['type'].isin(['results', 'board_meeting'])
        & ann_df['headline_lower'].str.contains('financial|results', regex=True)
    ).astype(int)

    ts_index = df.index
    df['ann_high_count_24h'] = _build_cumulative_window(ts_index, ann_df, 'high_flag', pd.Timedelta(hours=24))
    df['ann_high_sum_24h'] = _build_cumulative_window(ts_index, ann_df, 'impact_score', pd.Timedelta(hours=24))
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
    df['ann_last_impact'] = last['impact_score'].fillna(0).to_numpy()
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
        df['news_count_24h'] = 0
        df['news_sent_avg_24h'] = 0.0
        return df

    news_df['published_at'] = pd.to_datetime(news_df['published_at'], utc=True)
    news_df = news_df.sort_values('published_at')
    news_df['count_flag'] = 1
    news_df['sent_sum'] = news_df['sentiment']

    ts_index = df.index
    count_24h = _build_cumulative_window(ts_index, news_df, 'count_flag', pd.Timedelta(hours=24))
    sum_24h = _build_cumulative_window(ts_index, news_df, 'sent_sum', pd.Timedelta(hours=24))

    df['news_count_24h'] = count_24h
    df['news_sent_avg_24h'] = np.where(count_24h > 0, sum_24h / count_24h, 0.0)
    return df


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

    df['r1'] = df['close'].pct_change(1)
    df['r5'] = df['close'].pct_change(5)
    df['r15'] = df['close'].pct_change(15)
    df['r60'] = df['close'].pct_change(60)

    df['vol_std_5'] = df['r1'].rolling(5).std()
    df['vol_std_15'] = df['r1'].rolling(15).std()
    df['vol_std_60'] = df['r1'].rolling(60).std()

    df['mom_15'] = df['r1'].rolling(15).sum()
    df['mom_60'] = df['r1'].rolling(60).sum()

    rng = (df['high'] - df['low']) / df['close'].replace(0, np.nan)
    df['range_mean_15'] = rng.rolling(15).mean()
    df['range_mean_60'] = rng.rolling(60).mean()

    df['vol_mean_15'] = df['volume'].rolling(15).mean()
    df['vol_mean_60'] = df['volume'].rolling(60).mean()

    df['realized_vol_60m'] = df['r1'].rolling(60).std()

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
    dates = list(last_close_by_date.index)
    dates_sorted = sorted(dates)
    next_date_map = {dates_sorted[i]: dates_sorted[i + 1] for i in range(len(dates_sorted) - 1)}
    df['next_date'] = df['local_date'].map(next_date_map)
    df['next_close'] = df['next_date'].map(last_close_by_date)
    df['y_1d'] = df['next_close'] / df['close'] - 1.0

    return df


def train_models(df: pd.DataFrame) -> Dict[str, Optional[ModelBundle]]:
    models = {}
    if df.empty:
        return {k: None for k in HORIZONS}

    for label, horizon in HORIZONS.items():
        y_col = f"y_{label}"
        subset = df.dropna(subset=FEATURE_COLUMNS + [y_col])
        if len(subset) < 50:
            models[label] = None
            continue

        X = subset[FEATURE_COLUMNS].to_numpy(dtype=float)
        y = subset[y_col].to_numpy(dtype=float)
        Xn, mean, std = _normalize_features(X)
        coef, intercept = _fit_ridge(Xn, y)
        models[label] = ModelBundle(
            coef=coef,
            intercept=intercept,
            mean=mean,
            std=std,
            feature_names=list(FEATURE_COLUMNS),
            samples=len(subset),
        )
    return models


def _model_name(model: Optional[ModelBundle]) -> str:
    return 'ridge_v1' if model else 'baseline_v1'


def generate_latest_predictions() -> List[PricePrediction]:
    latest = Ohlc1m.objects.order_by('-ts').first()
    if not latest:
        return []

    start_ts = latest.ts - timedelta(days=120)
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
            else:
                predicted_return = _predict(model, feature_vals)

            predicted_price = latest_row['close'] * (1.0 + predicted_return)
            obj, _created = PricePrediction.objects.update_or_create(
                ts=latest.ts,
                horizon_min=horizon,
                defaults={
                    'predicted_return': float(predicted_return),
                    'predicted_price': float(predicted_price),
                    'last_close': float(latest_row['close']),
                    'model_name': _model_name(model),
                    'confidence': None,
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

    start_ts = latest.ts - timedelta(days=180)
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

    for i in range(train_days, len(dates) - test_days + 1, test_days):
        train_dates = set(dates[i - train_days : i])
        test_dates = set(dates[i : i + test_days])

        df_train = df[df['local_date'].isin(train_dates)]
        df_test = df[df['local_date'].isin(test_dates)]

        models = train_models(df_train)
        for label in HORIZONS:
            y_col = f"y_{label}"
            test_subset = df_test.dropna(subset=FEATURE_COLUMNS + [y_col])
            if test_subset.empty:
                continue

            model = models.get(label)
            if model is None:
                continue

            X = test_subset[FEATURE_COLUMNS].to_numpy(dtype=float)
            y_true = test_subset[y_col].to_numpy(dtype=float)
            preds = []
            for row in X:
                preds.append(_predict(model, row))
            preds = np.array(preds)
            mae = float(np.mean(np.abs(preds - y_true)))
            dir_acc = float(np.mean(np.sign(preds) == np.sign(y_true)))

            metrics[label]['mae'] += mae
            metrics[label]['dir_acc'] += dir_acc
            metrics[label]['n'] += len(test_subset)
            metrics[label]['folds'] += 1

    metrics_summary = {}
    for label, stats in metrics.items():
        if stats['folds'] == 0:
            metrics_summary[label] = {'mae': None, 'directional_accuracy': None, 'samples': 0}
        else:
            metrics_summary[label] = {
                'mae': stats['mae'] / stats['folds'],
                'directional_accuracy': stats['dir_acc'] / stats['folds'],
                'samples': stats['n'],
            }

    run = PricePredictionRun.objects.create(
        train_start=df.index.min(),
        train_end=df.index.max(),
        test_start=None,
        test_end=None,
        status='ok',
        metrics_json=metrics_summary,
    )
    return run
