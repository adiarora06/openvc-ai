from openvc_ai.domain.models import ChatMessage, LLMRequest, NewsItem
from openvc_ai.llm.ports import LLMPort


class NewsAnalysisAgent:
    def __init__(self, llm: LLMPort):
        self.llm = llm

    async def analyze(self, ticker: str, news: list[NewsItem]) -> str:
        if not news:
            return "No recent company news was available from the configured news provider."

        compact_news = "\n".join(
            f"- {item.headline} | {item.summary or ''}"[:700] for item in news[:12]
        )
        response = await self.llm.complete(
            LLMRequest(
                messages=[
                    ChatMessage(
                        role="system",
                        content=(
                            "You are a cautious investment research analyst. Summarize news impact. "
                            "Do not claim certainty. Separate bullish, bearish, and unknown factors."
                        ),
                    ),
                    ChatMessage(
                        role="user",
                        content=f"Ticker: {ticker}\nRecent news:\n{compact_news}\nReturn a concise market-impact analysis.",
                    ),
                ],
                temperature=0.1,
                max_tokens=700,
            )
        )
        return response.content
