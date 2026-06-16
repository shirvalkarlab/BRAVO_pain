#!/bin/bash
#SBATCH --job-name=83c2edb6a8a24b0c98a77b753c2efbee
#SBATCH --output=/usr/src/BRAVO/modules/AsyncJobScheduler/83c2edb6a8a24b0c98a77b753c2efbee.out
#SBATCH --error=/usr/src/BRAVO/modules/AsyncJobScheduler/83c2edb6a8a24b0c98a77b753c2efbee.err
#SBATCH --time=01:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=4G

# Activate virtual environment if needed
source /usr/src/BRAVO/venv/bin/activate

# Run your Python script
exec python /usr/src/BRAVO/modules/AnalysisPipelineScripts/AnalysisPipeline.py ExtractSpectralFeaturesDuringSurvey