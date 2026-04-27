import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log
from .exceptions import RateLimitError, ProviderNotAvailableError

logger = logging.getLogger(__name__)

def build_retry_decorator(max_attempts: int = 3, min_wait: float = 2, max_wait: float = 30):
    """Create a tenacity retry decorator tailored to LLM errors."""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=min_wait, min=min_wait, max=max_wait),
        retry=retry_if_exception_type((RateLimitError, ProviderNotAvailableError, ConnectionError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
