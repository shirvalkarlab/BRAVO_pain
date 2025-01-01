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

from . import Auth, WebSession, Participants, DataHandler, EventAnnotationHandler, DataAnalysis, Therapy

urlpatterns = [
    path('register', Auth.UserRegister.as_view()),
    path('login', Auth.UserLogin.as_view()),
    path('logout', Auth.UserLogout.as_view()),
    
    path('uploadData', DataHandler.DataUploadHandler.as_view()),
    path('setRecordingTimeShift', DataHandler.RecordingTimeShiftHandler.as_view()),

    path('querySurveyForms', EventAnnotationHandler.QuerySurveyForms.as_view()),
    path('deleteSurveyForms', EventAnnotationHandler.DeleteSurveyForms.as_view()),
    path('setSurveyForms', EventAnnotationHandler.SetSurveyForms.as_view()),
    path('queryParticipantSurveyRecords', EventAnnotationHandler.QueryParticipantSurveyRecords.as_view()),
    
    path('queryParticipantEvents', EventAnnotationHandler.QueryEventHandler.as_view()),
    path('queryParticipantAnnotations', EventAnnotationHandler.QueryAnnotationHandler.as_view()),
    path('addParticipantAnnotation', EventAnnotationHandler.InsertAnnotationHandler.as_view()),
    path('deleteParticipantAnnotation', EventAnnotationHandler.DeleteAnnotationHandler.as_view()),

    path('querySessions', WebSession.QuerySessionConfig.as_view()),
    path('updateSessions', WebSession.UpdateSessionConfig.as_view()),
    path('queryProcessingQueue', WebSession.QueryProcessingQueue.as_view()),

    path('queryParticipants', Participants.QueryParticipants.as_view()),
    path('queryParticipantInformation', Participants.QueryParticipantInformation.as_view()),
    path('createParticipantInformation', Participants.CreateParticipantInformation.as_view()),
    path('updateParticipantInformation', Participants.UpdateParticipantInformation.as_view()),
    path('deleteParticipantInformation', Participants.DeleteParticipantInformation.as_view()),
    path('updateDeviceInformation', Participants.UpdateDeviceInformation.as_view()),
    path('deleteDeviceInformation', Participants.DeleteDeviceInformation.as_view()),
    path('checkAccessPermission', Participants.CheckAccessPermission.as_view()),

    path('queryTherapeuticEffectAnalysis', DataAnalysis.QueryTherapeuticEffectAnalysis.as_view()),
    path('queryNeuralActivitySnapshot', DataAnalysis.QueryNeuralActivitySnapshot.as_view()),
    path('queryChronicNeuralActivity', DataAnalysis.QueryChronicNeuralActivity.as_view()),

    path('queryTherapyHistory', Therapy.QueryTherapyHistory.as_view()),
    
]