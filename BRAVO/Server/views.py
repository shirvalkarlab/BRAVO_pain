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

from django.shortcuts import render
from django.http.response import HttpResponseRedirect
import rest_framework.views as RestViews
import rest_framework.parsers as RestParsers

from django.views.decorators.csrf import ensure_csrf_cookie 
from django.utils.decorators import method_decorator

class StaticProxy(RestViews.APIView):
    def get(self, request):
        return HttpResponseRedirect('//' + os.environ["SERVER_HOST"] + ':3000' + request.path)

class Homepage(RestViews.APIView):
    parser_classes = [RestParsers.JSONParser]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        context = {}
        
        # If Development Uncomment the following: 
        #return render(request, "index_dev.html", context=context)
        return render(request, "index.html", context=context)
