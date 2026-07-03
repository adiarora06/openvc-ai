from datetime import date, timedelta

import pandas as pd
import pytest

from openvc_ai.agents.forecasting import QuantForecastAgent


def _make_prices(n: int = 60):
    start = date(2024, 1, 1)
    return pd.DataFrame(
        [{"date": start + timedelta(days=i), "close": 100 + i * 0.25} for i in range(n)]
    )


def test_quant_forecast_returns_bounds():
    result = QuantForecastAgent().forecast(_make_prices(), horizon_days=10, simulations=100)
    assert result["current_price"] > 0
    assert result["lower_bound"] < result["upper_bound"]
    assert 0.0 < result["confidence"] <= 0.9


def test_quant_forecast_includes_per_day_and_paths():
    result = QuantForecastAgent().forecast(
        _make_prices(), horizon_days=5, simulations=200, sample_paths=4
    )
    assert len(result["per_day_percentiles"]) == 5
    assert len(result["sample_paths"]) == 4
    for path in result["sample_paths"]:
        assert len(path) == 5


def test_quant_forecast_requires_minimum_history():
    with pytest.raises(ValueError):
        QuantForecastAgent().forecast(_make_prices(10), horizon_days=5, simulations=50)
