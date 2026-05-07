from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class Response:
    """Ответ от транспортного слоя"""
    status: int
    payload: dict


class ApiTimeoutError(Exception):
    """Превышено время ожидания при всех попытках"""
    pass


class ApiResponseError(Exception):
    """Ошибка при обработке ответа (не-retryable или после исчерпания попыток)"""
    pass


class AsyncTransport:
    """Интерфейс транспортного слоя (должен быть реализован в реальном коде)"""
    async def send(self, method: str, path: str) -> Response:
        raise NotImplementedError


class UserClient:
    """
    Асинхронный клиент для работы с API пользователей.
    Поддерживает retry на timeout и 5xx ошибки.
    """
    def __init__(
        self,
        transport: AsyncTransport,
        *,
        timeout: float = 0.20,
        retries: int = 1,
        retry_delay: float = 0.01,
    ) -> None:
        self._transport = transport
        self._timeout = timeout
        self._retries = retries
        self._retry_delay = retry_delay

    async def get_user(self, user_id: int) -> dict:
        """
        Получить пользователя по ID.
        
        Возвращает словарь с полями 'id' и 'name'.
        Поддерживает retry:
        - при TimeoutError (от asyncio.wait_for)
        - при HTTP статусе >= 500
        
        Args:
            user_id: ID пользователя
            
        Returns:
            dict: {'id': int, 'name': str}
            
        Raises:
            ApiTimeoutError: после исчерпания всех попыток при timeout
            ApiResponseError: при ошибке ответа (включая исчерпание попыток при 5xx)
        """
        path = f"/users/{user_id}"
        last_timeout: TimeoutError | None = None

        for attempt in range(self._retries + 1):
            try:
                response = await asyncio.wait_for(
                    self._transport.send("GET", path),
                    timeout=self._timeout,
                )
            except TimeoutError as exc:
                last_timeout = exc
                if attempt == self._retries:
                    raise ApiTimeoutError(
                        f"GET {path} timed out after {self._retries + 1} attempts"
                    ) from exc
                await asyncio.sleep(self._retry_delay)
                continue

            # Обработка server-side ошибок (retryable)
            if response.status >= 500:
                if attempt == self._retries:
                    raise ApiResponseError(f"server error: {response.status}")
                await asyncio.sleep(self._retry_delay)
                continue

            # Неуспешный, но не retryable статус (4xx и т.д.)
            if response.status != 200:
                raise ApiResponseError(f"unexpected status: {response.status}")

            # Успешный ответ
            return {
                "id": response.payload["id"],
                "name": response.payload["name"].strip(),
            }

        # Теоретически недостижимо, но для type checker'а
        raise ApiTimeoutError("unreachable") from last_timeout