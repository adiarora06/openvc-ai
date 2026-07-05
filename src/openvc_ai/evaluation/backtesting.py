"""Historical backtesting for the quantitative forecast model."""

from __future__ import annotations

import math

import pandas as pd

from openvc_ai.agents.forecasting import QuantForecastAgent
from openvc_ai.domain.models import BacktestRequest, BacktestResult, BacktestWindowResult


class ForecastBacktester:
    """Walk-forward backtester using the same QuantForecastAgent as production."""

    def __init__(self, forecaster: QuantForecastAgent | None = None) -> None:
        self.forecaster = forecaster or QuantForecastAgent()

    def run(self, prices: pd.DataFrame, request: BacktestRequest) -> BacktestResult:
        frame = prices.copy().sort_values("date").reset_index(drop=True)
        if frame.empty or len(frame) < request.training_window_days + request.horizon_days:
            raise ValueError(
                "Not enough price history for requested training window and forecast horizon"
            )

        windows: list[BacktestWindowResult] = []
        earliest_cutoff = request.training_window_days - 1
        latest_cutoff = len(frame) - request.horizon_days - 1
        cutoff_indexes = list(range(earliest_cutoff, latest_cutoff + 1, request.stride_days))
        if len(cutoff_indexes) > request.max_windows:
            cutoff_indexes = cutoff_indexes[-request.max_windows :]

        for cutoff_idx in cutoff_indexes:
            train_start_idx = cutoff_idx - request.training_window_days + 1
            target_idx = cutoff_idx + request.horizon_days
            train = frame.iloc[train_start_idx : cutoff_idx + 1]
            target = frame.iloc[target_idx]

            quant = self.forecaster.forecast(
                train,
                request.horizon_days,
                simulations=500,
                sample_paths=0,
            )

            start_price = float(quant["current_price"])
            predicted = float(quant["expected_price"])
            actual = float(target["close"])
            absolute_error = abs(predicted - actual)
            percentage_error = absolute_error / max(abs(actual), 1e-9)
            predicted_return = (predicted - start_price) / max(start_price, 1e-9)
            actual_return = (actual - start_price) / max(start_price, 1e-9)

            windows.append(
                BacktestWindowResult(
                    train_start=train.iloc[0]["date"],
                    forecast_date=train.iloc[-1]["date"],
                    target_date=target["date"],
                    start_price=start_price,
                    predicted_price=predicted,
                    actual_price=actual,
                    lower_bound=float(quant["lower_bound"]),
                    upper_bound=float(quant["upper_bound"]),
                    absolute_error=absolute_error,
                    percentage_error=percentage_error,
                    predicted_return=predicted_return,
                    actual_return=actual_return,
                    direction_correct=(predicted_return >= 0) == (actual_return >= 0),
                    interval_hit=float(quant["lower_bound"]) <= actual <= float(quant["upper_bound"]),
                )
            )

        if not windows:
            raise ValueError("Backtest produced no evaluation windows")

        mae = sum(w.absolute_error for w in windows) / len(windows)
        rmse = math.sqrt(sum(w.absolute_error**2 for w in windows) / len(windows))
        mape = sum(w.percentage_error for w in windows) / len(windows)
        directional_accuracy = sum(w.direction_correct for w in windows) / len(windows)
        interval_coverage = sum(w.interval_hit for w in windows) / len(windows)
        average_predicted_return = sum(w.predicted_return for w in windows) / len(windows)
        average_actual_return = sum(w.actual_return for w in windows) / len(windows)

        return BacktestResult(
            ticker=request.ticker,
            horizon_days=request.horizon_days,
            training_window_days=request.training_window_days,
            stride_days=request.stride_days,
            windows=len(windows),
            mae=mae,
            rmse=rmse,
            mape=mape,
            directional_accuracy=directional_accuracy,
            interval_coverage=interval_coverage,
            average_predicted_return=average_predicted_return,
            average_actual_return=average_actual_return,
            data_points=len(frame),
            first_forecast_date=windows[0].forecast_date,
            last_forecast_date=windows[-1].forecast_date,
            window_results=windows,
        )
