#!/bin/bash
#SBATCH --job-name=102c24a8f5104d909bf5ab909ad1227c
#SBATCH --output=/usr/src/BRAVO/modules/AsyncJobScheduler/102c24a8f5104d909bf5ab909ad1227c.out
#SBATCH --error=/usr/src/BRAVO/modules/AsyncJobScheduler/102c24a8f5104d909bf5ab909ad1227c.err
#SBATCH --time=01:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=4G

# Activate virtual environment if needed
source /usr/src/BRAVO/venv/bin/activate

# Run your Python script
exec python /usr/src/BRAVO/modules/AnalysisPipelineScripts/AnalysisPipeline.py ExtractSpectralFeaturesDuringSurvey