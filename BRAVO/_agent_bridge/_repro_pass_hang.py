"""Reproduce the 2026-10-16 06:29 pass that sat waiting for 12 minutes: run the pass's own main()
with every thread's stack written every 60 s."""
import faulthandler, sys, os
sys.path.insert(0, "/usr/src/BRAVO"); sys.path.insert(1, "/usr/src/BRAVO/modules")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
import django; django.setup()
f = open("/usr/src/BRAVO/_agent_bridge/_repro_pass_hang.stacks", "w")
faulthandler.dump_traceback_later(60, repeat=True, file=f)
from modules.ClosedLoopDeployment import refresh_saved_answers as job
job._own_process_group()
sys.exit(job.main(["--participant", "2e3c75c00d7f4f37b53a048d195f11da", "--workers", "32"]))
