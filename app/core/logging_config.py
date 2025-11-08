import logging
import sys
from app.core.config import settings

def setup_logging():
    """Set up the root logger."""
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s - %(levelname)s - [%(name)s] - %(message)s",
        stream=sys.stdout,
    )
