"""Entry point for running the OpenVC-AI API server."""

import uvicorn

from openvc_ai.config.logging_config import configure_logging
from openvc_ai.config.settings import settings


def main() -> None:
    configure_logging(settings.log_level)
    uvicorn.run(
        "openvc_ai.api.app:app",
        host="0.0.0.0",
        port=5050,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
