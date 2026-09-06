from django.test import SimpleTestCase, RequestFactory, override_settings
from django.http import HttpResponse
from Server.Middlewares.LoopbackSecurity import LoopbackSecurityMiddleware


@override_settings(ALLOWED_HOSTS=['localhost','127.0.0.1','share.example','localhost.example'],SECURE_SSL_REDIRECT=True,SECURE_HSTS_SECONDS=86400,SECURE_SSL_HOST=None)
class LoopbackSecurityTests(SimpleTestCase):
    def setUp(self):
        self.middleware=LoopbackSecurityMiddleware(lambda request:HttpResponse('ok'))
        self.factory=RequestFactory()

    def test_http_loopback_remains_available(self):
        for host in ['localhost:8080','127.0.0.1:8080']:
            self.assertEqual(self.middleware(self.factory.get('/',HTTP_HOST=host)).status_code,200)

    def test_shared_http_redirects_to_https(self):
        response=self.middleware(self.factory.get('/database',HTTP_HOST='share.example'))
        self.assertEqual(response.status_code,301)
        self.assertEqual(response['Location'],'https://share.example/database')

    def test_lookalike_hostname_does_not_get_loopback_exception(self):
        self.assertEqual(self.middleware(self.factory.get('/',HTTP_HOST='localhost.example')).status_code,301)

    def test_shared_https_keeps_hsts(self):
        response=self.middleware(self.factory.get('/',HTTP_HOST='share.example',secure=True))
        self.assertEqual(response.status_code,200)
        self.assertIn('max-age=86400',response['Strict-Transport-Security'])
