import os, django, json
django.setup()
from django.test import RequestFactory
from Server import models
from Server.models import PlatformUser
from Server.APIs import EventAnnotationHandler
import pandas as pd
def ok(c,m): print(("PASS" if c else "FAIL")+": "+m); assert c,m
inst=models.Institute.find(name="DSC") or models.Institute.create("DSC")
user=PlatformUser.objects.filter(user_name="dscuser").first()
if not user:
    user=PlatformUser(user_name="dscuser",email="d@d.com"); user.institute=inst; user.save(); inst.join(user,"Admin")
p,_=models.Participant.find_or_create("RCS08","MRN-DSC08",inst.pk)
rf=RequestFactory()
view=EventAnnotationHandler.ImportRedcapCSV.as_view()
def call(body):
    req=rf.post("/api/importRedcapCSV", data=json.dumps(body), content_type="application/json"); req.user=user
    return view(req)
# 1) first auto-import
r=call({"ParticipantId":p.uid,"RequestType":"AutoImport"})
ok(r.status_code==200,"autoimport 200 (%s)"%r.status_code)
print("first:", json.dumps({k:r.data[k] for k in ["TotalRecords","Changed","FilesImported"]}))
ok(r.data["TotalRecords"]==678,"first autoimport 678 records")
ok(r.data["Changed"]==1,"first autoimport changed=1")
ok(r.data["Instruments"][0]["Unchanged"]==False,"first marked changed")
# 2) second auto-import -> unchanged no-op
r2=call({"ParticipantId":p.uid,"RequestType":"AutoImport"})
print("second:", json.dumps({k:r2.data[k] for k in ["TotalRecords","Changed","FilesImported"]}))
ok(r2.data["Changed"]==0,"second autoimport changed=0 (idempotent)")
ok(r2.data["Instruments"][0]["Unchanged"]==True,"second marked unchanged")
ok(r2.data["TotalRecords"]==678,"second still 678 records present")
# verify only ONE form/version (no version churn on unchanged)
forms=models.ScaleForms.find_all(institute=inst, record_type="Redcap CSV Import")
ok(len(list(forms))==1,"exactly one form, no version churn")
cnt=models.ScaleRecord.objects.filter(participant=p).count()
ok(cnt==678,"exactly 678 records stored (no duplication) got %d"%cnt)
# 3) simulate a NEW REDCap fetch: append rows to a temp copy, import directly (DataFrame path)
src=os.path.join(EventAnnotationHandler.ImportRedcapCSV.ALLOWED_SERVER_DIR,"RCS08_chronic_pro_df.csv")
df=pd.read_csv(src, low_memory=False)
extra=df.tail(2).copy(); extra["date_time_s1_daily"]=["2026-07-01 10:00:00","2026-07-02 10:00:00"]
df2=pd.concat([df,extra],ignore_index=True)
from modules.SurveyForms import RedcapImportService
res=RedcapImportService.import_export(p, inst, df2, layout="auto", replace=True, skip_if_unchanged=True)
print("after-new-data:", json.dumps({"Unchanged":res[0]["Unchanged"],"RecordsImported":res[0]["RecordsImported"]}))
ok(res[0]["Unchanged"]==False,"changed export re-imported (not skipped)")
ok(res[0]["RecordsImported"]==680,"re-import has 680 records (678+2)")
ok(models.ScaleRecord.objects.filter(participant=p).count()==680,"store now 680 (replaced, not appended)")
print("\nAUTOIMPORT OK")
