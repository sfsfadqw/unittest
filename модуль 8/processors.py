import logging
from datetime import datetime
from uuid import uuid4

logger = logging.getLogger(__name__)


def log_payment(transaction_id: str, amount: float, status: str) -> None:
    logger.info(f"Payment {transaction_id}: {amount} - {status}")


def generate_transaction_id() -> str:
    return str(uuid4())


class AuditService:
    def __init__(self):
        self.events = []
    
    def record_event(self, event_type: str, data: dict) -> None:
        event = {
            'type': event_type,
            'data': data,
            'timestamp': datetime.now().isoformat()
        }
        self.events.append(event)
    
    def get_events(self) -> list:
        return self.events