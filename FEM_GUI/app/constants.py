from __future__ import annotations

import sys
from pathlib import Path


FEM_GUI_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = FEM_GUI_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
import config as pipeline_config

STATE_DIR = FEM_GUI_DIR / ".state"
SETTINGS_PATH = STATE_DIR / "settings.json"
APP_LOG_PATH = STATE_DIR / "fem_gui.log"

EULER_HOST = str(getattr(pipeline_config, "EULER_HOST", "euler.ethz.ch"))
DEFAULT_EULER_USER = str(getattr(pipeline_config, "EULER_USER", "acruzfaria"))
REMOTE_PROJECT_ROOT = str(getattr(pipeline_config, "EULER_DIR_TEMPLATE", "/cluster/home/{user}/AbaqusProject"))
REMOTE_SCRATCH_ROOT = str(getattr(pipeline_config, "EULER_SCRATCH_ROOT_TEMPLATE", "/cluster/scratch/{user}"))

WIDTH_OPTIONS = [20, 50, 80, 90, 100, 120, 200]
MS_OPTIONS = [1e-3, 1e-4, 5e-5, 1e-5, 5e-6, 1e-6, 1e-7]
PIP_OPTIONS = ["PUNCH_2", "PUNCH_21", "PUNCH_23", "PUNCH_24", "PUNCH_25"]
TEST_TYPES = ["nakazima", "marciniak", "pip"]
VELOCITY_PROFILES = ["smoothstep", "constant"]
