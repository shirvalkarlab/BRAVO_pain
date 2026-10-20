"""Real native survey persistence with canonical provider processing in a disposable DB."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
from test_optional_oauth_startup import isolated


def test_actual_canonical_redcap_native_form_and_transaction_rollback(tmp_path):
    daily=str(Path(__file__).resolve().parents[2]/'scripts/daily_import')
    isolated(tmp_path,f'''
        import sys,json
        sys.path.insert(0,{daily!r})
        import providers
        os.environ['REDCAP_API_URL']='https://synthetic.invalid/api/'
        os.environ['REDCAP_API_TOKEN']='synthetic-only'
        import pandas as pd
        from django.core.management import call_command
        from django.db import transaction
        from Server import models
        from modules.Biomarkers import bravo_service as bravo
        from modules.SurveyForms import RedcapImport,RedcapImportService
        call_command('migrate',verbosity=0,interactive=False)
        institute=models.Institute.objects.create(name='Synthetic Institute')
        person=models.Participant.objects.create(name='Synthetic',institute=institute)
        mapping={{'pt':'Synthetic','instruments':['daily'],'timestamp_label':'survey_time',
                  'metric_labels':{{'nrs':'pain','mpq_sum':['item1','item2']}}}}
        raw=pd.DataFrame({{'record_id':['Synthetic','Synthetic'],'redcap_repeat_instrument':['daily','daily'],
            'survey_time':['2020-07-01 12:00:00','2020-12-01 12:00:00'],
            'pain':[0.,float('nan')],'item1':[2.,float('nan')],'item2':[3.,float('nan')]}})
        with patch.object(bravo,'_load_pt_config',return_value=mapping),patch.object(bravo.redcap_client,'pull_redcap',return_value=raw) as pull:
            first=providers.redcap(person)
            assert first['records']==2 and first['metrics']==2 and first['unchanged'] is False
            form=models.ScaleForms.objects.get(name='Daily REDCap '+person.uid)
            rows=list(models.ScaleRecord.objects.filter(source=form,participant=person).order_by('date'))
            assert rows[0].record[0][:2]==[0.,5.] and rows[1].record[0][:2]==[None,None]
            assert rows[0].date==pd.Timestamp('2020-07-01T19:00:00Z').timestamp()
            assert rows[1].date==pd.Timestamp('2020-12-01T20:00:00Z').timestamp()
            ids=[r.uid for r in rows]
            assert providers.redcap(person)['unchanged'] is True
            assert list(models.ScaleRecord.objects.filter(source=form,participant=person).order_by('date').values_list('uid',flat=True))==ids
            assert pull.call_count==2
            # A late write failure must roll back native delete/reinsert entirely.
            raw.loc[0,'pain']=1.
            original=models.ScaleRecord.create
            count=[0]
            def failing(*args,**kwargs):
                count[0]+=1
                if count[0]==2:raise RuntimeError('synthetic write failure')
                return original(*args,**kwargs)
            with patch.object(models.ScaleRecord,'create',side_effect=failing):
                try:providers.redcap(person)
                except RuntimeError:pass
                else:raise AssertionError('write failure must propagate')
            assert list(models.ScaleRecord.objects.filter(source=form,participant=person).order_by('date').values_list('uid',flat=True))==ids
            assert list(models.ScaleRecord.objects.filter(source=form,participant=person).order_by('date'))[0].record[0][0]==0.
            # An empty provider result cannot erase prior forms.
            with patch.object(bravo,'_load_pros',return_value=raw.iloc[:0]):
                try:providers.redcap(person)
                except ValueError:pass
                else:raise AssertionError('empty export must fail')
            assert models.ScaleRecord.objects.filter(source=form,participant=person).count()==2
    ''')
