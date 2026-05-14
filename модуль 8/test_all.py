import unittest
from unittest.mock import patch, Mock
import os

from config import load_payment_config, PaymentConfig
from processors import log_payment, generate_transaction_id, AuditService
from service import PaymentService
from gateway import PaymentGatewayError


class TestConfig(unittest.TestCase):
    """Tests for configuration using patch.dict"""
    
    def test_default_values_when_no_env(self):
        with patch.dict('os.environ', {}, clear=True):
            config = load_payment_config()
            self.assertEqual(config.mode, 'prod')
            self.assertEqual(config.retry_count, 3)
            self.assertEqual(config.timeout_seconds, 30)
            self.assertFalse(config.dry_run)
            self.assertIsNone(config.api_url)
        print("✓ Test 1.1: Default values")
    
    def test_custom_values_from_env(self):
        with patch.dict('os.environ', {
            'PAYMENT_MODE': 'sandbox',
            'PAYMENT_RETRY_COUNT': '5',
            'PAYMENT_TIMEOUT': '60',
            'PAYMENT_API_URL': 'https://custom.api.com'
        }, clear=True):
            config = load_payment_config()
            self.assertEqual(config.mode, 'sandbox')
            self.assertEqual(config.retry_count, 5)
            self.assertEqual(config.timeout_seconds, 60)
            self.assertEqual(config.api_url, 'https://custom.api.com')
        print("✓ Test 1.2: Custom values from ENV")
    
    def test_dry_run_enabled(self):
        with patch.dict('os.environ', {'PAYMENT_DRY_RUN': '1'}, clear=True):
            config = load_payment_config()
            self.assertTrue(config.dry_run)
        print("✓ Test 1.3: Dry-run enabled")
    
    def test_invalid_mode_raises_error(self):
        with patch.dict('os.environ', {'PAYMENT_MODE': 'invalid'}, clear=True):
            with self.assertRaises(ValueError) as context:
                load_payment_config()
            self.assertIn("Unsupported payment mode", str(context.exception))
        print("✓ Test 1.4: Invalid mode error")


class TestProcessors(unittest.TestCase):
    """Tests for processors using patch and patch.object"""
    
    def test_log_payment_calls_logger_info(self):
        with patch('processors.logger') as mock_logger:
            log_payment('tx-123', 100.50, 'success')
            mock_logger.info.assert_called_once_with('Payment tx-123: 100.5 - success')
        print("✓ Test 2.1: Logging works")
    
    @patch('processors.uuid4')
    def test_generate_transaction_id_uses_uuid4(self, mock_uuid4):
        mock_uuid4.return_value = 'test-id-123'
        result = generate_transaction_id()
        self.assertEqual(result, 'test-id-123')
        mock_uuid4.assert_called_once()
        print("✓ Test 2.2: Transaction ID generation")
    
    def test_audit_service_record_event(self):
        audit_service = AuditService()
        with patch.object(audit_service, 'record_event') as mock_record:
            audit_service.record_event('test_event', {'data': 1})
            mock_record.assert_called_once_with('test_event', {'data': 1})
        print("✓ Test 2.3: patch.object for audit method")
    
    def test_audit_service_stores_events(self):
        audit_service = AuditService()
        audit_service.record_event('payment', {'amount': 100})
        events = audit_service.get_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['type'], 'payment')
        print("✓ Test 2.4: Real event storage")


class TestService(unittest.TestCase):
    """Tests for service using setUp and start/stop"""
    
    def setUp(self):
        """Setup mocks for all tests"""
        self.patchers = []
        
        self.MockGateway = self.create_patch('service.PaymentGateway')
        self.mock_log = self.create_patch('service.log_payment')
        self.mock_generate = self.create_patch('service.generate_transaction_id')
        
        self.mock_gateway_instance = self.MockGateway.return_value
        self.mock_gateway_instance.charge.return_value = {'transaction_id': 'tx-real'}
        self.mock_generate.return_value = 'tx-dry'
    
    def create_patch(self, target):
        """Helper for creating patch with auto cleanup"""
        patcher = patch(target)
        mock_obj = patcher.start()
        self.patchers.append(patcher)
        return mock_obj
    
    def tearDown(self):
        """Cleanup all patches"""
        for patcher in self.patchers:
            patcher.stop()
    
    def test_successful_payment_in_prod_mode(self):
        config = PaymentConfig(mode='prod', retry_count=3, timeout_seconds=30, dry_run=False)
        service = PaymentService(config=config)
        result = service.process_payment(100, 'USD', 'token')
        
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['transaction_id'], 'tx-real')
        self.mock_gateway_instance.charge.assert_called_once_with(100, 'USD', 'token')
        self.mock_log.assert_called_once()
        print("✓ Test 3.1: Successful payment in prod mode")
    
    def test_dry_run_mode_skips_gateway(self):
        config = PaymentConfig(mode='prod', retry_count=3, timeout_seconds=30, dry_run=True)
        service = PaymentService(config=config)
        
        self.assertIsNone(service.gateway)
        
        result = service.process_payment(100, 'USD', 'token')
        
        self.assertEqual(result['status'], 'dry_run')
        self.assertEqual(result['transaction_id'], 'tx-dry')
        self.mock_generate.assert_called_once()
        self.mock_gateway_instance.charge.assert_not_called()
        print("✓ Test 3.2: Dry-run mode skips gateway")
    
    def test_invalid_amount_raises_error(self):
        config = PaymentConfig(mode='prod', retry_count=3, timeout_seconds=30, dry_run=False)
        service = PaymentService(config=config)
        
        with self.assertRaises(ValueError) as context:
            service.process_payment(-10, 'USD', 'token')
        
        self.assertEqual(str(context.exception), "Amount must be positive")
        self.mock_gateway_instance.charge.assert_not_called()
        print("✓ Test 3.3: Invalid amount error")
    
    def test_invalid_currency_raises_error(self):
        config = PaymentConfig(mode='prod', retry_count=3, timeout_seconds=30, dry_run=False)
        service = PaymentService(config=config)
        
        with self.assertRaises(ValueError) as context:
            service.process_payment(100, 'GBP', 'token')
        
        self.assertIn("Unsupported currency", str(context.exception))
        self.mock_gateway_instance.charge.assert_not_called()
        print("✓ Test 3.4: Invalid currency error")
    
    def test_config_loaded_from_env(self):
        with patch.dict('os.environ', {'PAYMENT_MODE': 'test', 'PAYMENT_DRY_RUN': '0'}, clear=True):
            service = PaymentService()
            self.assertEqual(service.config.mode, 'test')
            self.assertFalse(service.config.dry_run)
        print("✓ Test 3.5: Config loaded from ENV")


class TestPatchTechniques(unittest.TestCase):
    """Demonstration of different mocking techniques"""
    
    def test_patch_dict_clear_true(self):
        with patch.dict('os.environ', {}, clear=True):
            import os
            self.assertEqual(os.getenv('ANY_VAR', 'default'), 'default')
        print("✓ Technique 1: patch.dict with clear=True")
    
    def test_patch_object(self):
        mock = Mock()
        with patch.object(mock, 'method', return_value='mocked'):
            result = mock.method()
            self.assertEqual(result, 'mocked')
        print("✓ Technique 2: patch.object")
    
    def test_patch_multiple(self):
        with patch.multiple('os', getenv=Mock(return_value='test')):
            import os
            self.assertEqual(os.getenv('ANY'), 'test')
        print("✓ Technique 3: patch.multiple")


if __name__ == '__main__':
    print("=" * 60)
    print("RUNNING TESTS")
    print("=" * 60)
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestConfig))
    suite.addTests(loader.loadTestsFromTestCase(TestProcessors))
    suite.addTests(loader.loadTestsFromTestCase(TestService))
    suite.addTests(loader.loadTestsFromTestCase(TestPatchTechniques))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 60)
    print(f"RESULTS:")
    print(f"  Tests run: {result.testsRun}")
    print(f"  Errors: {len(result.errors)}")
    print(f"  Failures: {len(result.failures)}")
    print("=" * 60)
    
    if result.wasSuccessful():
        print("\n✅ ALL TESTS PASSED!")
    else:
        print("\n❌ SOME TESTS FAILED")
    
    input("\nPress Enter to exit...")