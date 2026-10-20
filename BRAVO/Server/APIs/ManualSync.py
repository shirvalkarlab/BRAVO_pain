"""Admin-only fixed mailbox endpoint; no subprocess or provider execution."""
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from Server.authentication import ReadOnlySessionAuthentication
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from Server import models
from modules import Database, ManualSyncProtocol as protocol


class ManualSync(APIView):
    # Host-side operations require a browser session with CSRF, never API-key bypass.
    authentication_classes = [ReadOnlySessionAuthentication]
    parser_classes = [JSONParser]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_protect)
    def post(self, request):
        data = request.data
        if not isinstance(data, dict) or set(data) != {'ParticipantId', 'RequestType'} or data['RequestType'] not in ('Status', 'Start'):
            return Response({'message': 'Invalid synchronization request.'}, status=400)
        try:
            participant_uid = protocol.uid(data['ParticipantId'])
        except ValueError:
            return Response({'message': 'Invalid participant.'}, status=400)
        study_uid = request.user.configuration.get('ActiveStudy')
        if not Database.checkAccessPermission(request.user, participant_uid, study_uid=study_uid):
            return Response(status=403)
        person = models.Participant.find(uid=participant_uid)
        if person is None or person.institute_id is None:
            return Response(status=403)
        relation = models.InstituteRel.find(institute=person.institute, member=request.user)
        if relation is None or relation.permission.get('Position') != 'Admin':
            return Response(status=403)
        try:
            config = protocol.load_config()
            if (person.uid, person.institute_id) != (config['target_participant_uid'], config['target_institute_uid']):
                return Response(status=403)
            job, created = protocol.submit(config, request.user.uid) if data['RequestType'] == 'Start' else (protocol.status(config), False)
        except (OSError, ValueError):
            return Response({'CanSync': True, 'Available': False,
                'message': 'Synchronization is unavailable. Ask the platform administrator to check the service.'}, status=503)
        return Response({'CanSync': True, 'Available': True, 'Job': job,
            'Sources': {'Mode': config['source_mode'], 'UpstreamAvailable': config['upstream_available']},
            'Created': created}, status=202 if created else 200)
