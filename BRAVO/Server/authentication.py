from rest_framework.authentication import BaseAuthentication, SessionAuthentication
from . import models


class CsrfExemptSessionAuthentication(SessionAuthentication):
    """Session auth that does NOT enforce CSRF.

    DRF's stock SessionAuthentication enforces CSRF on any request that already carries a
    session cookie -- even one the view marked csrf_exempt -- so a stale/mismatched CSRF cookie
    in the browser 403s EVERY request, including /api/login, surfacing as "You do not have the
    permission". For the local/standalone DEBUG instance we skip that check so login always works.
    Production keeps the stock SessionAuthentication (see settings REST_FRAMEWORK).
    """
    def enforce_csrf(self, request):
        return

class BRAVOAPIAuthentication(BaseAuthentication):
    def authenticate(self, request):
        if "X-Secure-API-Key" in request.headers:
            secure_key = request.headers["X-Secure-API-Key"]
            user = models.PlatformUser.find(api_token=secure_key)
            if not user:
                return None
            
            request.csrf_processing_done = True
            user.api_access = True
            return (user, None)

        elif "X-Secure-Auth-Token" in request.headers:
            auth_token = request.headers["X-Secure-Auth-Token"]
            auth_record = models.AuthenticationTokens.objects.filter(token=auth_token, date__lte=models.current_time() + 3600*5).first()
            if not auth_record:
                return None
            
            user = auth_record.user
            if not user:
                return None
            
            request.csrf_processing_done = True
            user.api_access = True
            return (user, None)

        return None

from django.middleware.csrf import CsrfViewMiddleware
class BRAVOCSRFViewMiddleware(CsrfViewMiddleware):
    def process_view(self, request, callback, callback_args, callback_kwargs):
        if "X-Secure-API-Key" in request.headers:
            return None
        return super().process_view(request, callback=callback, callback_args=callback_args, callback_kwargs=callback_kwargs)
        