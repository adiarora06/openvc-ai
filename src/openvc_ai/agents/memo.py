from openvc_ai.domain.models import ChatMessage, ForecastResult, LLMRequest
from openvc_ai.llm.ports import LLMPort


class InvestmentMemoAgent:
    def __init__(self, llm: LLMPort):
        self.llm = llm

    @staticmethod
    def _compact_forecast(forecast: ForecastResult) -> dict:
        """Token-efficient summary excluding bulky series/path arrays."""
        return {
            "ticker": forecast.ticker,
            "horizon_days": forecast.horizon_days,
            "current_price": forecast.current_price,
            "expected_price": forecast.expected_price,
            "lower_bound": forecast.lower_bound,
            "upper_bound": forecast.upper_bound,
            "confidence": forecast.confidence,
            "risks": forecast.risks,
        }

    async def write_memo(self, forecast: ForecastResult, news_analysis: str) -> str:
        response = await self.llm.complete(
            LLMRequest(
                messages=[
                    ChatMessage(
                        role="system",
                        content=(
                            "You write cautious investment research memos. Include assumptions, "
                            "risks, and why the model may be wrong. This is not financial advice."
                        ),
                    ),
                    ChatMessage(
                        role="user",
                        content=(
                            f"Forecast summary:\n{self._compact_forecast(forecast)}\n\n"
                            f"News analysis:\n{news_analysis}\n\n"
                            "Write a concise investment memo."
                        ),
                    ),
                ],
                temperature=0.2,
                max_tokens=1000,
            )
        )
        return response.content
