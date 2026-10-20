"""Import an explicitly selected clinic/home workbook directory.

The private directory and participant binding must be provided by the operator.
The folder signature makes unchanged repeated imports idempotent.
"""
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError

from Server import models
from modules.StimOptimizer import clinic_pain

class Command(BaseCommand):
    help = "Parse the clinic-and-home testing workbooks and store them as the raw kind clinic_pain_steps."

    def add_arguments(self, parser):
        parser.add_argument("--participant", dest="participant", required=True,
                            help="Participant uid the folder belongs to.")
        parser.add_argument("--folder", dest="folder", required=True,
                            help="Explicit private folder of .xlsx workbooks for this participant.")

    def handle(self, *args, **opts):
        uid = opts["participant"]
        folder = opts.get("folder")
        if not folder or not Path(folder).is_dir():
            raise CommandError("An existing workbook directory must be supplied with --folder.")
        participant = models.Participant.find(uid=uid)
        if participant is None:
            self.stderr.write(f"participant {uid!r} not found")
            raise SystemExit(1)

        report = clinic_pain.ingest_and_store(participant, folder)
        if report.get("store_key") is None:
            self.stderr.write(f"nothing stored: {report.get('reason')}")
            raise SystemExit(1)

        self.stdout.write(
            f"{'wrote' if report['written'] else 'already stored (key unchanged)'}: "
            f"{report['n_files']} files, {report['n_steps']} steps, "
            f"{report['n_with_pain']} with a pain score, key {report['store_key']}")

        steps, manifest = clinic_pain.parse_folder(folder)
        self.stdout.write("\nper-file counts:")
        for r in manifest.to_dict("records"):
            err = f"  ERROR: {r['error']}" if r.get("error") else ""
            self.stdout.write(
                f"  {r['file']:<70s} {r['setting']:<6s} steps={r['n_steps']:>3d} "
                f"with_pain={r['n_with_pain']:>3d} prose={r['n_unparsed_prose']:>2d} "
                f"no_setting={r['n_skipped_no_setting']:>2d}{err}")

        n_clinic = int((steps["setting"] == "clinic").sum())
        n_home = int((steps["setting"] == "home").sum())
        pairs_55 = steps.loc[steps["freq_hz"] == 55.0, ["amp_mA_Left", "amp_mA_Right"]]
        pairs_55 = pairs_55.dropna(how="all").drop_duplicates()
        self.stdout.write(
            f"\ntotals: {int(manifest['n_steps'].sum())} steps, "
            f"{int(manifest['n_with_pain'].sum())} with a pain score, "
            f"{int(manifest['n_unparsed_prose'].sum())} unparsed prose, "
            f"{int(manifest['n_skipped_no_setting'].sum())} skipped (no setting known)\n"
            f"in-clinic rows: {n_clinic}, at-home rows: {n_home}\n"
            f"distinct (Left, Right) current pairs at 55 Hz: {len(pairs_55)}")
