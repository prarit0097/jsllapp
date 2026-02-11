from rest_framework.test import APITestCase

from apps.market.providers.mock_provider import MockPriceProvider
from apps.market.services import ingest_1m_candles


class HealthEndpointTests(APITestCase):
    def test_health_endpoint(self):
        response = self.client.get('/api/v1/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})


class MetaEndpointTests(APITestCase):
    def test_meta_endpoint(self):
        response = self.client.get('/api/v1/meta')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {'app': 'JSLL Decision Intelligence', 'version': '0.1.0'},
        )


class QuoteEndpointTests(APITestCase):
    def test_latest_quote_returns_200(self):
        ingest_1m_candles(MockPriceProvider())
        response = self.client.get('/api/v1/jsll/quote/latest')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')


class OhlcEndpointTests(APITestCase):
    def test_ohlc_endpoint_returns_data(self):
        ingest_1m_candles(MockPriceProvider())
        response = self.client.get('/api/v1/jsll/ohlc/1m?limit=5')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.json()) > 0)


class PipelineStatusTests(APITestCase):
    def test_pipeline_status_returns_expected_keys(self):
        ingest_1m_candles(MockPriceProvider())
        response = self.client.get('/api/v1/jsll/pipeline/status')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('last_run', payload)
        self.assertIn('last_candle_time', payload)
        self.assertIn('candles_last_60m', payload)
        self.assertIn('data_ok', payload)