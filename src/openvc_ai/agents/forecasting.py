import numpy as np
import pandas as pd

from openvc_ai.config.settings import settings


class QuantForecastAgent:
    """Simple baseline model: log-return drift + volatility Monte Carlo forecast."""

    def forecast(
        self,
        prices: pd.DataFrame,
        horizon_days: int,
        simulations: int | None = None,
        sample_paths: int | None = None,
    ) -> dict:
        """Run Monte Carlo simulations and return summary statistics plus per-day percentiles and sampled paths.

        Returns a dict with the existing keys (current_price, expected_price, lower_bound, upper_bound, confidence, drift, volatility)
        plus:
        - per_day_percentiles: list of dicts with {date_index, p10, p50, p90}
        - sample_paths: list of lists (each path is a list of prices for each day)
        """
        if prices.empty or len(prices) < 30:
            raise ValueError("Need at least 30 price points for a basic forecast")

        simulations = simulations if simulations is not None else settings.monte_carlo_simulations
        sample_paths = sample_paths if sample_paths is not None else settings.sample_paths

        close = prices["close"].astype(float).to_numpy()
        current_price = float(close[-1])
        returns = np.diff(np.log(close))
        drift = float(np.mean(returns))
        volatility = float(np.std(returns, ddof=1))

        sims = max(1, int(simulations))
        h = int(horizon_days)

        # generate daily log-return increments for each simulation
        rng = np.random.default_rng(0)
        rand = rng.normal(loc=drift, scale=max(volatility, 1e-9), size=(sims, h))
        # cumulative log-returns and convert to price paths
        cum = np.cumsum(rand, axis=1)
        # prices for each day for each sim
        paths = current_price * np.exp(cum)

        # terminal distribution summary
        terminal_prices = paths[:, -1]
        expected = float(np.mean(terminal_prices))
        lower = float(np.percentile(terminal_prices, 10))
        upper = float(np.percentile(terminal_prices, 90))
        confidence = float(max(0.1, min(0.9, 1.0 - (upper - lower) / max(expected, 1e-9))))

        # per-day percentiles (10th, 50th median, 90th)
        per_day = []
        for day in range(h):
            day_prices = paths[:, day]
            p10 = float(np.percentile(day_prices, 10))
            p50 = float(np.percentile(day_prices, 50))
            p90 = float(np.percentile(day_prices, 90))
            per_day.append({"index": day + 1, "p10": p10, "p50": p50, "p90": p90})

        # sample a small number of example paths for visualization
        sample_count = min(int(sample_paths), sims)
        rng2 = np.random.default_rng(42)
        chosen = rng2.choice(sims, sample_count, replace=False) if sample_count > 0 else []
        samples = []
        for idx in chosen:
            samples.append(list(paths[idx].tolist()))

        return {
            "current_price": current_price,
            "expected_price": expected,
            "lower_bound": lower,
            "upper_bound": upper,
            "confidence": confidence,
            "drift": drift,
            "volatility": volatility,
            "per_day_percentiles": per_day,
            "sample_paths": samples,
        }
