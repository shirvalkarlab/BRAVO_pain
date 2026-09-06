from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings
from Server.Middlewares.TransportCookies import TransportCookiesMiddleware


class TransportCookieTests(SimpleTestCase):
    def response(self, request):
        response = HttpResponse()
        response.set_cookie(settings.SESSION_COOKIE_NAME, 'synthetic-session')
        response.set_cookie(settings.CSRF_COOKIE_NAME, 'synthetic-csrf')
        return response

    def test_https_marks_both_authentication_cookies_secure(self):
        response = TransportCookiesMiddleware(self.response)(RequestFactory().get('/', secure=True))
        for name in (settings.SESSION_COOKIE_NAME, settings.CSRF_COOKIE_NAME):
            self.assertTrue(response.cookies[name]['secure'])

    def test_local_http_keeps_its_working_cookie_transport(self):
        response = TransportCookiesMiddleware(self.response)(RequestFactory().get('/'))
        self.assertFalse(response.cookies[settings.SESSION_COOKIE_NAME]['secure'])

    @override_settings(SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'))
    def test_trusted_https_proxy_marks_cookies_secure(self):
        request = RequestFactory().get('/', HTTP_X_FORWARDED_PROTO='https')
        response = TransportCookiesMiddleware(self.response)(request)
        self.assertTrue(response.cookies[settings.SESSION_COOKIE_NAME]['secure'])

    def test_response_without_cookies_is_unchanged(self):
        response = TransportCookiesMiddleware(lambda request: HttpResponse(status=204))(RequestFactory().get('/',secure=True))
        self.assertEqual(response.status_code,204)
        self.assertFalse(response.cookies)
