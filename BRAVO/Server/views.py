""""""
"""
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under Open Source GPL-3.0 License

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
"""
"""
SQL Table Definitions
===================================================
@author: Jackson Cagle, University of Florida
@email: jackson.cagle@neurology.ufl.edu
"""

import os
from uuid import uuid4
import ipaddress
import math
import threading
import time

from django.shortcuts import render
from django.http.response import HttpResponse, HttpResponseRedirect
from django.conf import settings
import rest_framework.views as RestViews
import rest_framework.parsers as RestParsers

from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator

from Server import models

ConsecutiveError = {}
_RATE_LIMIT_LOCK = threading.Lock()


def get_client_ip(request):
    """Use Caddy's overwritten client header only from an explicitly trusted peer.

    No general X-Forwarded-For trust: a direct client may supply any such header.
    A missing or malformed peer/header yields the peer address or no identity.
    """
    try:
        peer = ipaddress.ip_address(request.META.get("REMOTE_ADDR", ""))
    except ValueError:
        return None
    trusted = getattr(settings, "BRAVO_TRUSTED_PROXY_CIDRS", ())
    for cidr in trusted:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            continue
        if peer in network:
            try:
                return str(ipaddress.ip_address(request.META.get("HTTP_X_BRAVO_CLIENT_IP", "")))
            except ValueError:
                # Never aggregate visitors under a trusted proxy when its required
                # client header is missing. Deployment checks must catch that setup error.
                return None
    return str(peer)


def _homepage_retry_after(ip, now):
    """A short per-worker burst limit; never create permanent blacklist records."""
    if ip is None:
        return 0
    with _RATE_LIMIT_LOCK:
        for key in list(ConsecutiveError):
            if now - ConsecutiveError[key]["LastRequest"] >= 10:
                del ConsecutiveError[key]
        entry = ConsecutiveError.setdefault(ip, {"LastRequest": now, "Count": 0})
        entry["Count"] += 1
        if entry["Count"] > 10:
            return max(1, math.ceil(10 - (now - entry["LastRequest"])))
    return 0

class StaticProxy(RestViews.APIView):
    def get(self, request):
        return HttpResponseRedirect('//' + os.environ["SERVER_HOST"] + ':3000' + request.path)

class Homepage(RestViews.APIView):
    parser_classes = [RestParsers.JSONParser]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):

        requestIpAddr = get_client_ip(request)
        if requestIpAddr and models.BlacklistRecords.exists(ip_address=requestIpAddr):
            return render(request, "404.html")

        if not request.user.is_authenticated:
            retry_after = _homepage_retry_after(requestIpAddr, time.monotonic())
            if retry_after:
                response = HttpResponse("Too many requests. Please try again shortly.", status=429)
                response["Retry-After"] = str(retry_after)
                return response

        context = {}

        # If Development Uncomment the following:
        # return render(request, "index_dev.html", context=context)
        return render(request, "index.html", context=context)
