import os, sys
BRAVO_Path = ""
sys.path.append(BRAVO_Path)

from BRAVO import wsgi
from Server import models

AsyncJobScripts = {
    "BurstAnalysis": "",
    "ExtractSpectralFeaturesDuringStimulation": "/modules/AnalysisPipelineScripts/AnalysisPipeline.py ExtractSpectralFeaturesDuringStimulation"
}

def ScheduleSlurmJob(requester, recording_uid, script_name, config):
    SLURM_JOB_PATH = os.path.join(BRAVO_Path, "modules", "AsyncJobScheduler")
    with open(os.path.join(SLURM_JOB_PATH, "sjob.sh"), 'r') as f:
        sbatch_script = f.read()
    
    job = models.AsyncJob.create(
        name="BRAVO_Processing_Schedule",
        type="SLURM",
        recording_uid=recording_uid,
        result_message="",
        requester=requester,
        metadata={
            "script_name": script_name,
            "config": config
        }
    )

    sbatch_script = sbatch_script.replace("${SLURM_JOB_NAME}", job.uid)
    sbatch_script = sbatch_script.replace("${SLURM_WORKING_DIR}", SLURM_JOB_PATH)
    sbatch_script = sbatch_script.replace("${PYTHON_ENV}", BRAVO_Path + "/venv/bin/activate")
    sbatch_script = sbatch_script.replace("${SLURM_JOB_SCRIPT}", BRAVO_Path + AsyncJobScripts[script_name])
    sbatch_script = sbatch_script.replace("${JOB_ARGS}", "\" \"".join(config))

    with open(os.path.join(SLURM_JOB_PATH, job.uid + ".sh"), 'w+') as f:
        f.write(sbatch_script)

def CheckJobStatus(job_id):
    job = models.AsyncJob.find(uid=job_id)
    if not job:
        return {"status": "error", "message": "Job not found"}

    return {"status": "success", "data": job.get_info()}

if __name__ == "__main__":
    pass