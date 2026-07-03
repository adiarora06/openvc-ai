import pytest
from pydantic import ValidationError

from openvc_ai.domain.models import ForecastRequest


def test_ticker_is_normalized_uppercase():
    req = ForecastRequest(ticker="nvda")
    assert req.ticker == "NVDA"


def test_ticker_strips_whitespace():
    req = ForecastRequest(ticker="  aapl  ")
    assert req.ticker == "AAPL"


def test_invalid_ticker_rejected():
    with pytest.raises(ValidationError):
        ForecastRequest(ticker="bad ticker!")


def test_horizon_bounds_enforced():
    with pytest.raises(ValidationError):
        ForecastRequest(ticker="NVDA", horizon_days=0)
    with pytest.raises(ValidationError):
        ForecastRequest(ticker="NVDA", horizon_days=99999)


def test_defaults():
    req = ForecastRequest(ticker="NVDA")
    assert req.horizon_days == 30
    assert req.include_news is True
    assert req.include_memo is False
