import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class PaymentConfig:
    mode: str
    retry_count: int
    timeout_seconds: int
    dry_run: bool
    api_url: Optional[str] = None


def load_payment_config() -> PaymentConfig:
    mode = os.getenv("PAYMENT_MODE", "prod")
    
    if mode not in ["prod", "sandbox", "test"]:
        raise ValueError(f"Unsupported payment mode: {mode}")
    
    retry_count = int(os.getenv("PAYMENT_RETRY_COUNT", "3"))
    timeout_seconds = int(os.getenv("PAYMENT_TIMEOUT", "30"))
    dry_run = os.getenv("PAYMENT_DRY_RUN", "0") == "1"
    api_url = os.getenv("PAYMENT_API_URL", None)
    
    return PaymentConfig(
        mode=mode,
        retry_count=retry_count,
        timeout_seconds=timeout_seconds,
        dry_run=dry_run,
        api_url=api_url
    )