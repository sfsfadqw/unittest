class PaymentGatewayError(Exception):
    pass


class PaymentGateway:
    def __init__(self, api_url: str, timeout: int):
        self.api_url = api_url
        self.timeout = timeout
        self._request_count = 0
    
    def charge(self, amount: float, currency: str, card_token: str) -> dict:
        self._request_count += 1
        return {
            'status': 'success',
            'transaction_id': f"tx_{self._request_count}",
            'amount': amount,
            'currency': currency
        }
    
    def get_request_count(self) -> int:
        return self._request_count