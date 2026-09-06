#!/bin/bash
#SBATCH --job-name=${SLURM_JOB_NAME}
#SBATCH --output=${SLURM_WORKING_DIR}/${SLURM_JOB_NAME}.out
#SBATCH --error=${SLURM_WORKING_DIR}/${SLURM_JOB_NAME}.err
#SBATCH --time=01:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=4G

# Use the same interpreter as the web process; no guessed virtualenv path.
${JOB_COMMAND}
result=$?
exit_file=${EXIT_FILE}
printf '%s\n' "$result" > "$exit_file.tmp"
mv "$exit_file.tmp" "$exit_file"
exit "$result"
