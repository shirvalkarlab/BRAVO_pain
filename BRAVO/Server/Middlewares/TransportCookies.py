"""Secure cookies on the HTTPS share while retaining local HTTP access."""
from django.conf import settings


class TransportCookiesMiddleware:
    # Placed outside SessionMiddleware so its cookies already exist on response.
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.is_secure():
            for name in (settings.SESSION_COOKIE_NAME, settings.CSRF_COOKIE_NAME):
                if name in response.cookies:
                    response.cookies[name]['secure'] = True
        return response
