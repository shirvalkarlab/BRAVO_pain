from rest_framework.authentication import BaseAuthentication, BasicAuthentication
from rest_framework.exceptions import PermissionDenied
from .Middlewares.ReadOnlyAccount import is_read_only_user, viewer_request_allowed
from . import models

def enforce_viewer_access(user, request):
    # Token/basic authentication runs after Django middleware. Apply the same
    # viewer policy here so changing authentication cannot grant write/export rights.
    if is_read_only_user(user) and not viewer_request_allowed(request):
        raise PermissionDenied("This account has view-only access.")


class ReadOnlyBasicAuthentication(BasicAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result:
            enforce_viewer_access(result[0], request)
        return result


class BRAVOAPIAuthentication(BaseAuthentication):
    def authenticate(self, request):
        if "X-Secure-API-Key" in request.headers:
            secure_key = request.headers["X-Secure-API-Key"]
            user = models.PlatformUser.find(api_token=secure_key)
            if not user:
                return None
            
            enforce_viewer_access(user, request)
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
            
            enforce_viewer_access(user, request)
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
        