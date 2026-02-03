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
All API URLs
===================================================
@author: Jackson Cagle, University of Florida
@email: jackson.cagle@neurology.ufl.edu
"""

from django.urls import path
from django.conf import settings

from Server.APIs import Auth
from . import Participants, DataHandler

urlpatterns = [
    path('login', Auth.UserLogin.as_view()),
    path('queryParticipants', Participants.QueryParticipants.as_view()),
    path('queryParticipantContext', Participants.QueryParticipantContext.as_view()),

    path('getRawData', DataHandler.DataDownloadHandler.as_view()),
]