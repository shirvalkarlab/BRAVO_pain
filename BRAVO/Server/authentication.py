from rest_framework.authentication import BaseAuthentication
from . import models

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

        return None

from django.middleware.csrf import CsrfViewMiddleware
class BRAVOCSRFViewMiddleware(CsrfViewMiddleware):
    def process_view(self, request, callback, callback_args, callback_kwargs):
        if "X-Secure-API-Key" in request.headers:
            return None
        return super().process_view(request, callback=callback, callback_args=callback_args, callback_kwargs=callback_kwargs)
        