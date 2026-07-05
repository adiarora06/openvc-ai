from datetime import date, timedelta

import pandas as pd
import pytest

from openvc_ai.domain.models import BacktestRequest
from openvc_ai.evaluation.backtesting import ForecastBacktester


def _make_prices(n: int = 180):
    start = date(2024, 1, 1)
    return pd.DataFrame(
        [{"date": start + timedelta(days=i), "close": 100 + i * 0.2} for i in range(n)]
    )


def test_backtest_returns_metrics_and_windows():
    request = BacktestRequest(
        ticker="NVDA",
        horizon_days=10,
        training_window_days=60,
        stride_days=20,
        max_windows=4,
    )

    result = ForecastBacktester().run(_make_prices(), request)

    assert result.ticker == "NVDA"
    assert result.windows == 4
    assert result.mae >= 0
    assert result.rmse >= 0
    assert result.mape >= 0
    assert 0 <= result.directional_accuracy <= 1
    assert 0 <= result.interval_coverage <= 1
    assert len(result.window_results) == 4


def test_backtest_requires_enough_history():
    request = BacktestRequest(ticker="NVDA", horizon_days=30, training_window_days=100)

    with pytest.raises(ValueError, match="Not enough price history"):
        ForecastBacktester().run(_make_prices(50), request)
