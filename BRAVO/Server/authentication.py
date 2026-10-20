from rest_framework.authentication import BaseAuthentication, SessionAuthentication, BasicAuthentication
from rest_framework.exceptions import AuthenticationFailed
from . import models
from .read_only import is_read_only, enforce_read_only


class ReadOnlySessionAuthentication(SessionAuthentication):
    """Enforce the viewer contract after identity and CSRF verification."""
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            enforce_read_only(request, result[0])
        return result


class ReadOnlyBasicAuthentication(BasicAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None and is_read_only(result[0]):
            raise AuthenticationFailed("Shared viewers must sign in using a browser session.")
        return result


class CsrfExemptSessionAuthentication(ReadOnlySessionAuthentication):
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
            if not user or not user.is_active:
                return None
            
            if is_read_only(user):
                raise AuthenticationFailed("Shared viewers cannot use API credentials.")
            request.csrf_processing_done = True
            user.api_access = True
            return (user, None)

        elif "X-Secure-Auth-Token" in request.headers:
            auth_token = request.headers["X-Secure-Auth-Token"]
            now = models.current_time()
            auth_record = models.AuthenticationTokens.objects.filter(
                token=auth_token, date__gt=now - 3600 * 5, date__lte=now).first()
            if not auth_record:
                return None
            
            user = auth_record.user
            if not user or not user.is_active:
                return None
            
            if is_read_only(user):
                raise AuthenticationFailed("Shared viewers cannot use API credentials.")
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
        