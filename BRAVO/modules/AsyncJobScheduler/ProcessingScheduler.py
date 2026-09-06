import os, sys
BRAVO_Path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(BRAVO_Path)

from BRAVO import wsgi
from Server import models
import subprocess
import psutil
import time
import shlex
import hashlib
import json
from filelock import FileLock
from pathlib import Path

USE_SLURM = os.environ.get('USE_SLURM', 'FALSE') == 'TRUE'
SLURM_JOB_PATH = os.path.join(os.environ.get("DATASERVER_PATH", BRAVO_Path), "jobs")
TEMPLATE_PATH = os.path.join(BRAVO_Path, "modules", "AsyncJobScheduler", "sjob.sh")

AsyncJobScripts = {
    "BurstAnalysis": "/modules/AnalysisPipelineScripts/AnalysisPipeline.py BurstAnalysis ${JOB_ARGS}",
    "FitbitRefresh": "/modules/Fitbit/FitbitDataUpdateService.py ${JOB_ARGS}",
    "ExtractSpectralFeaturesDuringStimulation": "/modules/AnalysisPipelineScripts/AnalysisPipeline.py ExtractSpectralFeaturesDuringStimulation",
    "ExtractSpectralFeaturesDuringSurvey": "/modules/AnalysisPipelineScripts/AnalysisPipeline.py ExtractSpectralFeaturesDuringSurvey",
    "BIDSExport": "/modules/AnalysisPipelineScripts/AnalysisPipeline.py BIDSExport ${JOB_ARGS}",
}

def ScheduleSlurmJob(requester, recording_uid, script_name, config, refresh=False):
    Path(SLURM_JOB_PATH).mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(json.dumps([str(requester.pk), recording_uid, script_name, config], sort_keys=True).encode()).hexdigest()
    with FileLock(os.path.join(SLURM_JOB_PATH, key + ".lock"), timeout=30):
        return _schedule_job(requester, recording_uid, script_name, config, refresh)


def _schedule_job(requester, recording_uid, script_name, config, refresh=False):
    Path(SLURM_JOB_PATH).mkdir(parents=True, exist_ok=True)
    if script_name not in AsyncJobScripts:
        raise ValueError("Unknown background analysis")
    existing_job = models.AsyncJob.find(recording_uid=recording_uid, requester=requester, metadata__script_name=script_name, metadata__config=config)
    if existing_job:
        if refresh:
            state = CheckJobStatus(existing_job)
            if state["State"] not in {"Completed", "Failed"}:
                return existing_job
        else:
            return existing_job

    job = models.AsyncJob.create(
        name="BRAVO_Processing_Schedule",
        type="SLURM" if USE_SLURM else "LOCAL",
        recording_uid=recording_uid,
        result_message="",
        requester=requester,
        metadata={
            "script_name": script_name,
            "config": config,
            "job_directory": SLURM_JOB_PATH,
        }
    )

    with open(TEMPLATE_PATH, 'r') as f:
        sbatch_script = f.read()
    
    sbatch_script = sbatch_script.replace("${SLURM_JOB_NAME}", job.uid)
    sbatch_script = sbatch_script.replace("${SLURM_WORKING_DIR}", SLURM_JOB_PATH)
    arguments = shlex.split(AsyncJobScripts[script_name].replace("${JOB_ARGS}", job.uid))
    arguments[0] = BRAVO_Path + arguments[0]
    command = [os.environ.get("BRAVO_JOB_PYTHON", sys.executable), *arguments]
    sbatch_script = sbatch_script.replace("${JOB_COMMAND}", shlex.join(command))
    sbatch_script = sbatch_script.replace("${EXIT_FILE}", shlex.quote(os.path.join(SLURM_JOB_PATH, job.uid + ".exit")))

    with open(os.path.join(SLURM_JOB_PATH, job.uid + ".sh"), 'w+') as f:
        f.write(sbatch_script)

    if USE_SLURM:
        result = subprocess.run("sbatch " + os.path.join(SLURM_JOB_PATH, job.uid + ".sh"), capture_output=True, text=True, shell=True)
        job.metadata["slurm_job_id"] = result.stdout.strip().split(" ")[-1]
        job.save()
    else:
        with open(os.path.join(SLURM_JOB_PATH, job.uid + ".out"), "ab") as out, open(os.path.join(SLURM_JOB_PATH, job.uid + ".err"), "ab") as err:
            process = subprocess.Popen(["bash", os.path.join(SLURM_JOB_PATH, job.uid + ".sh")],
                                       stdout=out, stderr=err, start_new_session=True)
        job.metadata["pid"] = process.pid
        try:
            job.metadata["pid_create_time"] = psutil.Process(process.pid).create_time()
        except psutil.Error:
            pass
        # A fast worker may have already saved its terminal state.
        job.save(update_fields=["metadata"])
        CheckJobStatus(job)

    return job

def CheckJobStatus(job):
    job.refresh_from_db()
    if job.type == "LOCAL":
        if job.state in {"Completed", "Failed"}:
            return job.get_info()
        directory = job.metadata.get("job_directory", SLURM_JOB_PATH)
        exit_file = Path(directory) / (job.uid + ".exit")
        if exit_file.is_file():
            try:
                code = int(exit_file.read_text().strip())
                job.state = "Completed" if code == 0 else "Failed"
                job.result_message = "" if code == 0 else f"Background analysis exited with code {code}."
            except (OSError, ValueError):
                job.state = "Failed"
                job.result_message = "Background analysis produced an invalid completion status."
        else:
            try:
                ps_proc = psutil.Process(job.metadata["pid"])
                if ps_proc.create_time() != job.metadata.get("pid_create_time") or ps_proc.status() == psutil.STATUS_ZOMBIE:
                    raise psutil.NoSuchProcess(job.metadata["pid"])
                job.state = "Running"
            except (psutil.Error, KeyError):
                job.state = "Failed"
                job.result_message = "Background analysis stopped without reporting successful completion. Retry the analysis."
        job.save()

    elif job.type == "SLURM":
        format_str = "\"%.18i|%.9P|%.20j|%.8u|%.2t|%.10M|%.6D|%.30R\""
        result = subprocess.run("squeue -j " + job.metadata["slurm_job_id"] + " --noheader --format " + format_str, capture_output=True, text=True, shell=True)
        if len(result.stdout.strip()) == 0:
            job.state = "Completed"
            job.save()
        else:
            result = result.stdout.strip().split("|")
            job.state = result[4].strip()
            job.save()

    return job.get_info()

if __name__ == "__main__":
    pass