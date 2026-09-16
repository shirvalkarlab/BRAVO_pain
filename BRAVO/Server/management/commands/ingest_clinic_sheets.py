"""Read the lab's clinic-and-home testing workbooks into the store as a raw kind.

WHY THIS EXISTS. The PI's decision, 2026-09-14: "Import all in-clinic AND at-home testing visits.
Pull the in-clinic numbers separately (not in REDCap) as an independent data stream for system
optimization (critical)." The workbooks themselves are gitignored (they carry the patient's own
words in their free-text notes columns), so nothing reads them until this command is run inside
the container where the folder is mounted.

THE KEY DECIDES (decision 26): it is built from the folder's own file set (name and content hash
per file, `StimOptimizer.clinic_pain.folder_signature`), so re-running this command over an
unchanged folder writes nothing -- an already-stored entry is read back and reported, not rebuilt.

USAGE (inside the server container, where `/usr/src/BRAVO/_pro_dump` is mounted):
    python manage.py ingest_clinic_sheets --participant <uid>
    python manage.py ingest_clinic_sheets --participant <uid> --folder /path/to/workbooks
"""
from django.core.management.base import BaseCommand

from Server import models
from modules.StimOptimizer import clinic_pain

DEFAULT_FOLDER = "/usr/src/BRAVO/_pro_dump/clinic_sheets/RCS08"


class Command(BaseCommand):
    help = "Parse the clinic-and-home testing workbooks and store them as the raw kind clinic_pain_steps."

    def add_arguments(self, parser):
        parser.add_argument("--participant", dest="participant", required=True,
                            help="Participant uid the folder belongs to.")
        parser.add_argument("--folder", dest="folder", default=DEFAULT_FOLDER,
                            help=f"Folder of .xlsx workbooks (default: {DEFAULT_FOLDER}).")

    def handle(self, *args, **opts):
        uid = opts["participant"]
        folder = opts["folder"]
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
