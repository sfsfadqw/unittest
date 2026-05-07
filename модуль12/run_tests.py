import unittest

if __name__ == "__main__":
    # Загружаем все тесты из tests/
    loader = unittest.TestLoader()
    suite = loader.discover("tests", pattern="test_*.py")
    
    # Запускаем с verbosity=2 для детального вывода
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)