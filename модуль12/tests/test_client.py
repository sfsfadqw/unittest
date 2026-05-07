# tests/test_client.py - ИСПРАВЛЕННАЯ ВЕРСИЯ

import unittest
from unittest.mock import Mock, AsyncMock, call, patch
import inspect

# Добавляем импорт AsyncTransport
from app.client import UserClient, Response, ApiTimeoutError, ApiResponseError, AsyncTransport


class TestUserClient(unittest.IsolatedAsyncioTestCase):
    """
    Тесты для UserClient.
    Все тесты изолированы: каждый получает свой event loop.
    """
    
    async def test_success_path(self):
        """Тест 1: Успешный ответ - клиент нормализует данные"""
        transport = Mock()
        transport.send = AsyncMock(
            return_value=Response(200, {"id": 7, "name": " Alice "})
        )
        
        client = UserClient(transport, timeout=0.20, retries=1)
        
        user = await client.get_user(7)
        
        # Проверяем результат
        self.assertEqual(user, {"id": 7, "name": "Alice"})
        
        # Проверяем, что транспорт был вызван и ожидан (не просто вызван!)
        transport.send.assert_awaited_once_with("GET", "/users/7")
        
        # Дополнительная проверка: убеждаемся, что нет лишних вызовов
        self.assertEqual(transport.send.await_count, 1)
    
    async def test_retries_after_timeout(self):
        """Тест 2: Retry после timeout - клиент делает повторную попытку"""
        transport = Mock()
        transport.send = AsyncMock(
            side_effect=[
                TimeoutError(),  # первая попытка - timeout
                Response(200, {"id": 7, "name": "Alice"}),  # вторая - успех
            ]
        )
        
        client = UserClient(
            transport,
            timeout=0.20,
            retries=1,
            retry_delay=0.01,
        )
        
        # Патчим asyncio.sleep, чтобы не ждать реально
        with patch("app.client.asyncio.sleep", return_value=None) as mock_sleep:
            user = await client.get_user(7)
        
        # Проверяем успешный результат
        self.assertEqual(user, {"id": 7, "name": "Alice"})
        
        # Проверяем последовательность ожиданий
        transport.send.assert_has_awaits([
            call("GET", "/users/7"),
            call("GET", "/users/7"),
        ])
        
        # Проверяем, что backoff был вызван ровно один раз
        mock_sleep.assert_awaited_once_with(0.01)
        self.assertEqual(mock_sleep.await_count, 1)
    
    async def test_retries_after_500(self):
        """Тест 3: Retry после 5xx ошибки - клиент повторяет запрос"""
        transport = Mock()
        transport.send = AsyncMock(
            side_effect=[
                Response(500, {"detail": "Internal Server Error"}),
                Response(200, {"id": 7, "name": "Alice"}),
            ]
        )
        
        client = UserClient(
            transport,
            timeout=0.20,
            retries=1,
            retry_delay=0.01,
        )
        
        with patch("app.client.asyncio.sleep", return_value=None) as mock_sleep:
            user = await client.get_user(7)
        
        self.assertEqual(user, {"id": 7, "name": "Alice"})
        
        transport.send.assert_has_awaits([
            call("GET", "/users/7"),
            call("GET", "/users/7"),
        ])
        
        mock_sleep.assert_awaited_once_with(0.01)
    
    async def test_raises_timeout_after_last_attempt(self):
        """Тест 4: Исчерпание попыток - клиент поднимает ApiTimeoutError"""
        transport = Mock()
        transport.send = AsyncMock(
            side_effect=[
                TimeoutError(),
                TimeoutError(),
            ]
        )
        
        client = UserClient(
            transport,
            timeout=0.20,
            retries=1,
            retry_delay=0.01,
        )
        
        with patch("app.client.asyncio.sleep", return_value=None) as mock_sleep:
            with self.assertRaisesRegex(ApiTimeoutError, "timed out after 2 attempts"):
                await client.get_user(7)
        
        # Должно быть 2 попытки (retries=1 -> всего 2 вызова)
        self.assertEqual(transport.send.await_count, 2)
        mock_sleep.assert_awaited_once_with(0.01)
    
    async def test_no_retry_on_404(self):
        """Тест 5: 404 ошибка НЕ вызывает retry"""
        transport = Mock()
        transport.send = AsyncMock(
            return_value=Response(404, {"detail": "User not found"})
        )
        
        client = UserClient(
            transport,
            timeout=0.20,
            retries=3,
            retry_delay=0.01,
        )
        
        with patch("app.client.asyncio.sleep", return_value=None) as mock_sleep:
            with self.assertRaisesRegex(ApiResponseError, "unexpected status: 404"):
                await client.get_user(7)
        
        # Должен быть только один вызов
        transport.send.assert_awaited_once_with("GET", "/users/7")
        
        # Backoff НЕ должен вызываться
        mock_sleep.assert_not_awaited()
        self.assertEqual(mock_sleep.await_count, 0)
    
    async def test_final_500_raises_error(self):
        """Тест 6: Исчерпание попыток при 5xx - клиент поднимает ApiResponseError"""
        transport = Mock()
        transport.send = AsyncMock(
            side_effect=[
                Response(503, {"detail": "Service Unavailable"}),
                Response(503, {"detail": "Service Unavailable"}),
            ]
        )
        
        client = UserClient(
            transport,
            timeout=0.20,
            retries=1,
            retry_delay=0.01,
        )
        
        with patch("app.client.asyncio.sleep", return_value=None) as mock_sleep:
            with self.assertRaisesRegex(ApiResponseError, "server error: 503"):
                await client.get_user(7)
        
        self.assertEqual(transport.send.await_count, 2)
        mock_sleep.assert_awaited_once_with(0.01)
    
    async def test_no_retry_on_400(self):
        """Тест 7: 400 ошибка НЕ вызывает retry (дополнительный негативный сценарий)"""
        transport = Mock()
        transport.send = AsyncMock(
            return_value=Response(400, {"detail": "Bad Request"})
        )
        
        client = UserClient(
            transport,
            timeout=0.20,
            retries=3,
            retry_delay=0.01,
        )
        
        with patch("app.client.asyncio.sleep", return_value=None) as mock_sleep:
            with self.assertRaisesRegex(ApiResponseError, "unexpected status: 400"):
                await client.get_user(7)
        
        transport.send.assert_awaited_once_with("GET", "/users/7")
        mock_sleep.assert_not_awaited()
    
    async def test_timeout_wiring(self):
        """
        Тест 8: Узкий тест на wiring таймаута.
        Проверяем, что клиент передаёт правильный timeout в asyncio.wait_for.
        
        ИСПРАВЛЕНАЯ ВЕРСИЯ: используем side_effect для перехвата аргументов
        """
        transport = Mock()
        transport.send = AsyncMock()
        transport.send.return_value = Response(200, {"id": 7, "name": "Alice"})
        
        # Создаём переменную для захвата аргументов wait_for
        captured_timeout = None
        captured_coro = None
        
        async def wait_for_side_effect(coro, timeout=None):
            """Функция-шпион для перехвата аргументов wait_for"""
            nonlocal captured_timeout, captured_coro
            captured_timeout = timeout
            captured_coro = coro
            # Просто возвращаем результат, который вернула бы оригинальная корутина
            return await coro
        
        # Патчим asyncio.wait_for нашей функцией-шпионом
        with patch("app.client.asyncio.wait_for", side_effect=wait_for_side_effect):
            client = UserClient(
                transport,
                timeout=0.42,  # специфическое значение для проверки
                retries=0,
            )
            
            await client.get_user(7)
            
            # Проверяем, что timeout был передан правильно
            self.assertEqual(captured_timeout, 0.42)
            
            # Проверяем, что корутина - это результат вызова transport.send
            # captured_coro - это корутина, которую вернул transport.send(7)
            # Мы не можем сравнить её напрямую с transport.send, потому что
            # вызов mock возвращает корутину, а не сам mock
            self.assertIsNotNone(captured_coro)

    async def test_zero_retries_no_retry_behavior(self):
        """Тест 9: Без retry (retries=0) - клиент не повторяет запросы"""
        transport = Mock()
        transport.send = AsyncMock(
            side_effect=[
                TimeoutError(),
                Response(200, {"id": 7, "name": "Alice"}),
            ]
        )
        
        client = UserClient(
            transport,
            timeout=0.20,
            retries=0,
            retry_delay=0.01,
        )
        
        # Проверяем, что после первого же timeout клиент падает
        with self.assertRaisesRegex(ApiTimeoutError, "timed out after 1 attempts"):
            await client.get_user(7)
        
        # Должен быть только один вызов
        self.assertEqual(transport.send.await_count, 1)


class TestAsyncTransportContract(unittest.TestCase):
    """
    Дополнительные тесты: проверка контракта AsyncTransport.
    Эти тесты синхронные и не требуют event loop.
    """
    
    def test_async_transport_is_awaitable(self):
        """Проверяем, что AsyncTransport действительно async"""
        # AsyncTransport уже импортирован в начале файла
        self.assertTrue(
            inspect.iscoroutinefunction(AsyncTransport.send),
            "AsyncTransport.send must be an async function"
        )
    
    def test_response_dataclass_exists(self):
        """Проверяем, что Response существует и имеет правильную структуру"""
        response = Response(200, {"id": 1})
        self.assertEqual(response.status, 200)
        self.assertEqual(response.payload, {"id": 1})
    
    def test_exceptions_inheritance(self):
        """Проверяем, что исключения наследуются от Exception"""
        self.assertTrue(issubclass(ApiTimeoutError, Exception))
        self.assertTrue(issubclass(ApiResponseError, Exception))


# Альтернативная версия теста timeout_wiring, которая проверяет именно то,