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
REST API Request Error Handler Module
===================================================
@author: Jackson Cagle, University of Florida
@email: jackson.cagle@neurology.ufl.edu
"""

import logging, os
import json 
import traceback

from django.views.debug import ExceptionReporter

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARD_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

class ErrorHandlingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)
            if response.status_code >= 400:
                message = "Request From " + get_client_ip(request) + " | Request URL: " + request.path + " | Error Code: " + str(response.status_code)
                print(message)
            return response
        
        except Exception as e:
            message = "Request From " + get_client_ip(request) + " | Request URL: " + request.path + "\n"
            print(message)

    # This is the error thrown for 500 (Python Script Error)
    def process_exception(self, request, exception):
        message = "Request From " + get_client_ip(request) + " | Request URL: " + request.path + "\n"
        print(message)
        print(traceback.format_exc())