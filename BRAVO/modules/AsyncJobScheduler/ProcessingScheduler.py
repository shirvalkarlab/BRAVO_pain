import os, sys
BRAVO_Path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(BRAVO_Path)

from BRAVO import wsgi
from Server import models
import subprocess
import psutil

USE_SLURM = os.environ.get('USE_SLURM', 'FALSE') == 'TRUE'
SLURM_JOB_PATH = os.path.join(BRAVO_Path, "modules", "AsyncJobScheduler")

AsyncJobScripts = {
    "BurstAnalysis": "/modules/AnalysisPipelineScripts/AnalysisPipeline.py BurstAnalysis",
    "ExtractSpectralFeaturesDuringStimulation": "/modules/AnalysisPipelineScripts/AnalysisPipeline.py ExtractSpectralFeaturesDuringStimulation"
}

def ScheduleSlurmJob(requester, recording_uid, script_name, config):
    existing_job = models.AsyncJob.find(recording_uid=recording_uid, requester=requester, metadata__script_name=script_name, metadata__config=config)
    if existing_job:
        return existing_job
    
    job = models.AsyncJob.create(
        name="BRAVO_Processing_Schedule",
        type="SLURM" if USE_SLURM else "LOCAL",
        recording_uid=recording_uid,
        result_message="",
        requester=requester,
        metadata={
            "script_name": script_name,
            "config": config
        }
    )

    
    with open(os.path.join(SLURM_JOB_PATH, "sjob.sh"), 'r') as f:
        sbatch_script = f.read()
    
    sbatch_script = sbatch_script.replace("${SLURM_JOB_NAME}", job.uid)
    sbatch_script = sbatch_script.replace("${SLURM_WORKING_DIR}", SLURM_JOB_PATH)
    sbatch_script = sbatch_script.replace("${PYTHON_ENV}", BRAVO_Path + "/venv/bin/activate")
    sbatch_script = sbatch_script.replace("${SLURM_JOB_SCRIPT}", BRAVO_Path + AsyncJobScripts[script_name])
    sbatch_script = sbatch_script.replace("${JOB_ARGS}", job.uid)

    with open(os.path.join(SLURM_JOB_PATH, job.uid + ".sh"), 'w+') as f:
        f.write(sbatch_script)

    if USE_SLURM:
        pid = subprocess.call(["sbatch", os.path.join(SLURM_JOB_PATH, job.uid + ".sh")])
    else:
        process = subprocess.Popen(["bash", os.path.join(SLURM_JOB_PATH, job.uid + ".sh")])
        job.metadata["pid"] = process.pid
        job.save()
    
    return job

def CheckJobStatus(job):
    if job.type == "LOCAL":
        try:
            ps_proc = psutil.Process(job.metadata["pid"])
            if not job.state == "Running":
                job.state = "Running"
                job.save() 

        except:
            if not job.state == "Completed":
                job.state = "Completed"
                job.save() 

    return job.get_info()

if __name__ == "__main__":
    pass