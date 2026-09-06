"""Participant-scoped read-only access to the reviewed REDCap timeline."""
import datetime as dt
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from Server import models
from modules import Database
from modules.RCS08DataPolicy import applies_to
from modules.RedcapTimeline import VERSION, TIMEZONE, build_report
from modules.ReportCache import cached_report


class QueryRedcapTimeline(APIView):
    parser_classes = [JSONParser]
    permission_classes = [IsAuthenticated]

    @property
    def cache_version(self):
        # Form publication invalidates data/stages; midnight advances the visible endpoint.
        from modules.RedcapComparisons import VERSION as COMPARISON_VERSION, code_identity
        from modules.RedcapHomePrograms import VERSION as HOME_PROGRAM_VERSION
        return ':'.join((VERSION, HOME_PROGRAM_VERSION, COMPARISON_VERSION, code_identity(),
                         dt.datetime.now(ZoneInfo(TIMEZONE)).date().isoformat()))

    @method_decorator(csrf_protect if not settings.DEBUG else csrf_exempt)
    def post(self, request):
        body = request.data
        if (not isinstance(body, dict) or set(body) != {'ParticipantId'}
                or not isinstance(body.get('ParticipantId'), str) or not body['ParticipantId']
                or len(body['ParticipantId']) > 128):
            return Response({'message': 'Malformed Input'}, status=400)
        permission = Database.checkAccessPermission(request.user, body['ParticipantId'],
                                                    study_uid=request.user.configuration.get('ActiveStudy'))
        if not permission:
            return Response(status=403)
        participant = models.Participant.find(uid=body['ParticipantId'])
        if participant is None:
            return Response(status=403)
        if not applies_to(participant):
            return Response({'message': 'This participant has no reviewed pre-trial survey mapping.'}, status=404)
        try:
            return self._report(request, participant)
        except (KeyError, ValueError, TypeError, OverflowError, OSError):
            return Response({'message': 'The REDCap timeline needs an updated reviewed data sync. Please refresh after syncing.'}, status=503)

    @cached_report
    def _report(self, request, participant):
        from modules.RedcapVisitContext import read
        from modules.RedcapStimulation import build_context
        from modules.RedcapHomeAdjustments import apply
        report = build_report(participant)
        daily = models.ScaleForms.find(institute=participant.institute, name='RCS08 Daily PRO (REDCap)',
                                       record_type='REDCap API Sync')
        if (daily is None or not isinstance(daily.record, list) or not daily.record
                or not isinstance(daily.record[0], dict)
                or not isinstance(daily.record[0].get('processing'), dict)):
            raise ValueError('Daily reviewed processing metadata is unavailable')
        report['visits'] = read(daily, dt.datetime.now(dt.timezone.utc).timestamp())
        report['stimulation'] = apply(build_context(participant),
            daily.record[0]['processing'].get('timeline_home_adjustments', []), dt.datetime.now(dt.timezone.utc).timestamp())
        from modules.RedcapComparisons import read as read_comparisons
        report['comparisons'] = read_comparisons(daily, report['metrics'], dt.datetime.now(dt.timezone.utc).timestamp(), report['stimulation'])
        report['stimulation'].pop('_comparison_snapshots', None)
        return Response(report, headers={'Cache-Control': 'no-store'})
