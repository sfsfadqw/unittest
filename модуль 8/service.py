from typing import Optional
from config import load_payment_config, PaymentConfig
from gateway import PaymentGateway, PaymentGatewayError
from processors import log_payment, generate_transaction_id, AuditService


class PaymentService:
    def __init__(self, config: Optional[PaymentConfig] = None):
        self.config = config or load_payment_config()
        self.audit_service = AuditService()
        
        if not self.config.dry_run:
            api_url = self.config.api_url or "https://api.payment.example"
            self.gateway = PaymentGateway(api_url, self.config.timeout_seconds)
        else:
            self.gateway = None
    
    def process_payment(self, amount: float, currency: str, card_token: str) -> dict:
        if amount <= 0:
            raise ValueError("Amount must be positive")
        
        if currency not in ['USD', 'EUR', 'RUB']:
            raise ValueError(f"Unsupported currency: {currency}")
        
        if self.config.dry_run:
            transaction_id = generate_transaction_id()
            log_payment(transaction_id, amount, "dry_run")
            self.audit_service.record_event("payment_dry_run", {
                'amount': amount,
                'currency': currency
            })
            return {
                'status': 'dry_run',
                'transaction_id': transaction_id,
                'amount': amount,
                'currency': currency
            }
        
        result = self.gateway.charge(amount, currency, card_token)
        transaction_id = result['transaction_id']
        log_payment(transaction_id, amount, "success")
        self.audit_service.record_event("payment_success", {
            'transaction_id': transaction_id,
            'amount': amount,
            'currency': currency
        })
        
        return {
            'status': 'success',
            'transaction_id': transaction_id,
            'amount': amount,
            'currency': currency
        }
    
    def get_audit_events(self) -> list:
        return self.audit_service.get_events()