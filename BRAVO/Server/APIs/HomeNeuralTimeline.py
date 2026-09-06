"""Authenticated, participant-scoped native home Timeline read endpoint."""
import time
from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from Server import models
from modules import Database, HomeNeuralTimeline
from modules.RCS08DataPolicy import applies_to


class QueryHomeNeuralTimeline(APIView):
    parser_classes = [JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        body = request.data
        if (not isinstance(body, dict) or set(body) not in (
                {'ParticipantId'}, {'ParticipantId', 'window'}, {'ParticipantId', 'window', 'start_date', 'end_date'}) or
                ('window' in body and body['window'] not in ('past28', 'custom')) or
                (body.get('window') == 'past28' and set(body) != {'ParticipantId', 'window'}) or
                (body.get('window') == 'custom' and set(body) != {'ParticipantId', 'window', 'start_date', 'end_date'}) or
                not isinstance(body.get('ParticipantId'), str) or not body['ParticipantId'] or len(body['ParticipantId']) > 128):
            return Response({'message': 'Malformed Input'}, status=400)
        now = time.time()
        options = {key: body[key] for key in ('window', 'start_date', 'end_date') if key in body}
        try:
            HomeNeuralTimeline.windows((), now, **options)
        except (ValueError, OverflowError):
            return Response({'message': 'Malformed Input'}, status=400)
        permission = Database.checkAccessPermission(request.user, body['ParticipantId'],
                                                    study_uid=request.user.configuration.get('ActiveStudy'))
        if not permission:
            return Response(status=403)
        participant = models.Participant.find(uid=body['ParticipantId'])
        if participant is None:
            return Response(status=403)
        if not applies_to(participant):
            return Response({'message': 'A reviewed stimulation visit calendar is not available for this participant.'}, status=404)
        try:
            report = HomeNeuralTimeline.read(participant, now, **options)
        except (KeyError, ValueError, TypeError, IndexError, OverflowError, OSError):
            return Response({'message': 'Native home Timeline data or its reviewed visit calendar is unavailable.'}, status=503)
        return Response(report, headers={'Cache-Control': 'no-store'})
