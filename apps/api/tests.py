from rest_framework.test import APITestCase


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