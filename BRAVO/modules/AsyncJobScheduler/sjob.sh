#!/bin/bash
#SBATCH --job-name=${SLURM_JOB_NAME}
#SBATCH --output=${SLURM_WORKING_DIR}/${SLURM_JOB_NAME}.out
#SBATCH --error=${SLURM_WORKING_DIR}/${SLURM_JOB_NAME}.err
#SBATCH --time=01:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=4G

# Activate virtual environment if needed
source ${PYTHON_ENV}

# Run your Python script
python ${SLURM_JOB_SCRIPT} ${JOB_ARGS}