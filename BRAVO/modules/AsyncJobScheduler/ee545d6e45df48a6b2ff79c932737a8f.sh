#!/bin/bash
#SBATCH --job-name=ee545d6e45df48a6b2ff79c932737a8f
#SBATCH --output=/usr/src/BRAVO/modules/AsyncJobScheduler/ee545d6e45df48a6b2ff79c932737a8f.out
#SBATCH --error=/usr/src/BRAVO/modules/AsyncJobScheduler/ee545d6e45df48a6b2ff79c932737a8f.err
#SBATCH --time=01:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=4G

# Activate virtual environment if needed
source /usr/src/BRAVO/venv/bin/activate

# Run your Python script
exec python /usr/src/BRAVO/modules/AnalysisPipelineScripts/AnalysisPipeline.py ExtractSpectralFeaturesDuringSurvey