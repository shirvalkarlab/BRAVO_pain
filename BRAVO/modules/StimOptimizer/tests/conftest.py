"""Put BRAVO/modules on sys.path so `StimOptimizer` imports the same way it does in-container."""
import sys
from pathlib import Path

MODULES_DIR = Path(__file__).resolve().parents[2]
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))
