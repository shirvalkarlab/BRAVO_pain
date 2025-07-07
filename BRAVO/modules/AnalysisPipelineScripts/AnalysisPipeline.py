import os, sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from filelock import Timeout, FileLock
from BRAVO import wsgi 

if __name__ == "__main__":
    if sys.argv[1] == "ExtractSpectralFeaturesDuringSurvey":
        from modules.AnalysisPipelineScripts.ExtractSpectralFeaturesDuringSurvey import HandleRefreshAnalysis
        lock = FileLock(sys.argv[1] + ".lock")
        try:
            with lock.acquire(timeout=30):
                HandleRefreshAnalysis()

        except Timeout:
            print("Lockfile Not Acquired before Timeout")
            

    elif sys.argv[1] == "ExtractSpectralFeaturesDuringStimulation":
        from modules.AnalysisPipelineScripts.ExtractSpectralFeaturesDuringStimulation import HandleRefreshAnalysis
        lock = FileLock(sys.argv[1] + ".lock")
        try:
            with lock.acquire(timeout=30):
                HandleRefreshAnalysis()
                
        except Timeout:
            print("Lockfile Not Acquired before Timeout")
            
