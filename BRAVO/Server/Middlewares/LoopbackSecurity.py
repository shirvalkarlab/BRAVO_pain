"""Allow the local loopback UI while requiring HTTPS for shared hostnames."""
from django.http.request import split_domain_port
from django.middleware.security import SecurityMiddleware


class LoopbackSecurityMiddleware(SecurityMiddleware):
    def process_request(self, request):
        host, _ = split_domain_port(request.get_host())
        if host in {'localhost', '127.0.0.1', '[::1]'}:
            return None
        return super().process_request(request)
