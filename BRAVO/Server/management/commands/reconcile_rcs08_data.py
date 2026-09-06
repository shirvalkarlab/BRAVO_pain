"""Reconcile reviewed RCS08 device imports. Run bravo-backup before --apply."""
import json
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from Server import models
from modules import DataCurator, Database, ReportCache, RCS08DataPolicy as policy

class Command(BaseCommand):
    help = 'Preview or apply the reviewed RCS08 device reconciliation; retains original JSON reports.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        p=models.Participant.find(name='RCS08')
        if not p: raise CommandError('RCS08 not found')
        devices=list(models.DBSDevice.find_all(owner=p).prefetch_related('electrodes'))
        candidates=[d for d in devices if {e.target for e in d.electrodes.all()} == policy.EXPECTED_TARGETS]
        if not candidates: raise CommandError('No device with the reviewed GPi/VIM leads found')
        canonical=max(candidates,key=lambda d:models.SourceFile.objects.filter(owner=p,metadata__Device=d.uid).count())
        bad_devices=[d for d in devices if d not in candidates]
        bad_sources=list(models.SourceFile.objects.filter(owner=p,metadata__Device__in=[d.uid for d in bad_devices]))
        reasons={}
        for source in bad_sources:
            reason=policy.source_exclusion(json.loads(DataCurator.loadCacheFile(source)))
            if not reason: raise CommandError('An unexpected device contains a compatible report; review required')
            reasons[source.uid]=reason
        bad_ids=[s.uid for s in bad_sources]
        source_filter=Q(source_id__in=bad_ids) | Q(source__owner=p,source__type='MedtronicJSON',date__lt=policy.IMPLANT_DAY)
        classes=(models.TherapyModification,models.DBSEvent,models.Annotation,models.Recording,models.Therapy)
        plan={'apply':options['apply'],'devices_before':len(devices),'devices_after':1,
              'excluded_source_files':[s.name for s in bad_sources],
              'derived_rows_removed':{M.__name__:M.objects.filter(source_filter).count() for M in classes},
              'implant_day':'2025-07-16','raw_json_retained':True}
        if not options['apply']:
            self.stdout.write(json.dumps(plan)); return
        original_hashes=dict(models.SourceFile.objects.filter(owner=p,type='MedtronicJSON').values_list('uid','hashed'))
        with transaction.atomic():
            for source in bad_sources:
                source.metadata={**source.metadata,'AnalysisExclusion':reasons[source.uid],
                                 'ExcludedDevice':next(d.get_info() for d in bad_devices if d.uid==source.metadata['Device']),
                                 'Device':''}
                source.save()
            for M in classes: M.objects.filter(source_filter).delete()
            for other in candidates:
                if other.uid==canonical.uid: continue
                for source in models.SourceFile.objects.filter(owner=p,metadata__Device=other.uid):
                    source.metadata={**source.metadata,'OriginalDevice':other.get_info(),'Device':canonical.uid}
                    source.save()
                if other.implanted_date>=policy.IMPLANT_DAY:
                    canonical.implanted_date=other.implanted_date
                other.delete()
            canonical.name=policy.CANONICAL_NAME
            canonical.implanted_location='Right IPG'
            canonical.device_bloodline='Right IPG'
            if canonical.implanted_date<policy.IMPLANT_DAY: canonical.implanted_date=policy.IMPLANT_DAY
            canonical.save()
            for electrode in canonical.electrodes.all():
                electrode.hemisphere=electrode.target.split()[0]
                electrode.custom_name=electrode.target
                electrode.implanted_date=canonical.implanted_date
                electrode.save()
            for device in bad_devices: device.delete()
            # Derived timelines contain prior device IDs; rebuild from retained recordings.
            models.Recording.objects.filter(source__owner=p,type='MedtronicChronicNeuralActivity').delete()
            assert original_hashes==dict(models.SourceFile.objects.filter(owner=p,type='MedtronicJSON').values_list('uid','hashed'))
            ReportCache.invalidate(neural=True)
        plan['raw_source_hashes_unchanged']=True
        self.stdout.write(json.dumps(plan))
