"""Participant-scoped read-only FreeReps visualization adapter."""
import re

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from Server import models
from modules import Database
from modules.OURA import DataManager
from modules.OURA.FreeReps import VERSION, SleepNotFound, build_report
from modules.ReportCache import cached_report


class QueryOuraFreeReps(APIView):
    cache_version = VERSION
    parser_classes = [JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        body = request.data
        if (not isinstance(body, dict) or set(body) - {'ParticipantId', 'SleepId'}
                or not isinstance(body.get('ParticipantId'), str) or not body['ParticipantId']
                or len(body['ParticipantId']) > 128):
            return Response({'message': 'Malformed Input'}, status=400)
        if 'SleepId' in body and (not isinstance(body['SleepId'], str) or not re.fullmatch('[0-9a-f]{24}', body['SleepId'])):
            return Response({'message': 'Malformed sleep selection'}, status=400)
        permission = Database.checkAccessPermission(request.user, body['ParticipantId'],
                                                    study_uid=request.user.configuration.get('ActiveStudy'))
        if not permission:
            return Response(status=403)
        if not models.Participant.find(uid=body['ParticipantId']):
            return Response(status=403)
        return self._report(request)

    @cached_report
    def _report(self, request):
        participant = models.Participant.find(uid=request.data['ParticipantId'])
        try:
            result = build_report(DataManager.loadOuraRingData(participant), request.data.get('SleepId'))
        except SleepNotFound:
            return Response({'message': 'This sleep session is no longer available. Refresh the overview.'}, status=404)
        except (KeyError, ValueError, TypeError, OverflowError):
            return Response({'message': 'Stored Oura data could not be prepared. Please review the source data.'}, status=503)
        return Response(result, headers={'Cache-Control': 'no-store'})
