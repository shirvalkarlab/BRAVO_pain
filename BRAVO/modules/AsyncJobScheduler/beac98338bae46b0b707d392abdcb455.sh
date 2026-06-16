#!/bin/bash
#SBATCH --job-name=beac98338bae46b0b707d392abdcb455
#SBATCH --output=/usr/src/BRAVO/modules/AsyncJobScheduler/beac98338bae46b0b707d392abdcb455.out
#SBATCH --error=/usr/src/BRAVO/modules/AsyncJobScheduler/beac98338bae46b0b707d392abdcb455.err
#SBATCH --time=01:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=4G

# Activate virtual environment if needed
source /usr/src/BRAVO/venv/bin/activate

# Run your Python script
exec python /usr/src/BRAVO/modules/AnalysisPipelineScripts/AnalysisPipeline.py ExtractSpectralFeaturesDuringSurvey