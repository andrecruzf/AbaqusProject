# -*- coding: utf-8 -*-
# =============================================================
# config.py  —  All model parameters in one place.
# Modify only this file to change test configuration.
#
# Coordinate convention:
#   Z = forming direction (punch moves +Z)
#   Blank lies in the XY plane (z=0 at bottom, z=BLANK_THICKNESS at top)
#   Quarter-model symmetry: X=0 (XSYMM) and Y=0 (YSYMM)
# =============================================================

# ── Abaqus names ──────────────────────────────────────────────
MODEL_NAME = 'Model-1'

# ── Specimen selection ────────────────────────────────────────
# Width in mm — selects geometry file W{width}.inp from INP_DIR.
# Available in Engin_Input_Files/geometries: 20, 50, 80, 100, 120, 200
SPECIMEN_WIDTH = 50

# Path to geometry .inp files (relative to AbaqusProject/ working directory)
INP_DIR = 'geometries'

# Name of the imported specimen part (None = first non-tool part found)
SPECIMEN_PART_NAME = None

# ── Cluster resources ─────────────────────────────────────────
NUM_CPUS = 24         # CPUs for Abaqus/Explicit (threads, mp_mode=threads)

# ── Sheet thickness ───────────────────────────────────────────
BLANK_THICKNESS = 1   # mm — varies per sheet batch
JOB_NAME        = 'Nakazima_W{}_t{}'.format(SPECIMEN_WIDTH, BLANK_THICKNESS)
CAE_NAME        = 'nakazima_W{}_t{}.cae'.format(SPECIMEN_WIDTH, BLANK_THICKNESS)
INP_NAME        = 'nakazima_W{}_t{}'.format(SPECIMEN_WIDTH, BLANK_THICKNESS)
OUTPUT_DIR      = JOB_NAME   # subdirectory created per simulation run

# ── Die geometry ──────────────────────────────────────────────
DIE_INNER_RADIUS = 52.5  # mm — die throat / punch clearance radius
DIE_OUTER_RADIUS = 73.0  # mm — outer radius (die and blank holder)
DIE_FILLET       = 8.0   # mm — die throat fillet radius
DIE_HEIGHT       = 40.0  # mm — die wall height above blank

# ── Blank holder (Matrix) geometry ───────────────────────────
BH_INNER_RADIUS  = 54.5  # mm — blank holder inner contact radius
BH_HEIGHT        = 44.0  # mm — blank holder height below blank
BH_FILLET        = 4.0   # mm — fillet radius at inner contact edge

# ── Punch geometry ────────────────────────────────────────────
PUNCH_RADIUS = 50.0      # mm — hemispherical punch radius
PUNCH_HEIGHT = 60.0      # mm — punch cylindrical body height

# ── Forming parameters ────────────────────────────────────────
PUNCH_DISPLACEMENT = 50.0                        # mm — total punch travel
STEP_TIME = PUNCH_DISPLACEMENT / 5.0             # s  — time-scaled (not real speed)
# Check ALLKE/ALLIE < 5 % in post-processing to validate quasi-static assumption.

# ── Mass scaling ──────────────────────────────────────────────
USE_MASS_SCALING = True
MASS_SCALING_DT  = 1.0e-5   # s — target stable time increment (FIXED type)

# ── Friction ──────────────────────────────────────────────────
FR_PUNCH = 0.10   # Coulomb coefficient — punch / blank interface
FR_CLAMP = 0.15   # Coulomb coefficient — die / blank and blank-holder / blank

# ── Material orientation ──────────────────────────────────────
# Angle of the rolling direction (RD) from the global X-axis, in degrees.
# 0°  → RD along X  (standard)
# 90° → RD along Y
MATERIAL_ORIENTATION_ANGLE = 0.0

# ── VUMAT ─────────────────────────────────────────────────────
# Path relative to the AbaqusProject/ working directory.
VUMAT_PATH = 'VUMAT_explicit.f'

# Material name in Abaqus (must match the VUMAT user-material name).
MATERIAL_NAME = 'mat'

# 46 VUMAT constants — source: Engin_Input_Files/material.inp
VUMAT_CONSTANTS = (
    210000.0, 0.3, 4.49e8, 0.9, 0.0, 0.0, 0.0, 1.0,  # PROPS(8)=Forflag: 0=BE, 1=FE
    -0.632037464212743, 1.02021859572227, 3.09488820610282,
    -0.615242, 0.932977, 2.523173, 0.0, 0.0,
    616.4216042, 0.012115207, 0.224421494, 243.5375383,
    213.1450349, 10.14801667, 0.89, 3.0,
    1.0e-3, 0.0, 0.0, 25.0, 25.0, 1200.0, 20.0, 0.0,
    1.48, 1.13, 0.05, 0.1, 0.0, 0.0, 0.0, 3.0,
    1.0, 2.0, 0.0, 1.0, 0.1, 1.0,
)

# State-dependent variables (17 SDVs; SDV 7 triggers element deletion)
DEPVAR_COUNT  = 17
DEPVAR_DELETE = 7
SDV_LABELS = [
    (1,  'EQPS',    'Equivalent Plastic Strain'),
    (2,  'Seq',     'Equivalent stress'),
    (3,  'Qeq',     'Equivalent Hill stress'),
    (4,  'TRIAX',   'Triaxiality'),
    (5,  'LODE',    'Lode parameter'),
    (6,  'D',       'Damage'),
    (7,  'FAIL',    'Failure switch'),
    (8,  'Beta',    'Softening function'),
    (9,  'eeV',     'Volumetric strain'),
    (10, 'T',       'Temperature'),
    (11, 'EQPSdot', 'Equivalent Plastic Strain rate'),
    (12, 'ySRH',    'Strain rate hardening'),
    (13, 'yTS',     'Thermal softening'),
    (14, 'fSR',     'Failure strain rate'),
    (15, 'fTS',     'Failure thermal softening'),
    (16, 'Wcl',     'CL plastic work'),
    (17, 'EQPSf',   'EQPSf'),
]

# ── Geometry source ───────────────────────────────────────────
# 'cae'   → import the specimen mesh from W{SPECIMEN_WIDTH}.cae (recommended)
# 'inp'   → import from W{SPECIMEN_WIDTH}.inp (fallback)
# 'macro' → generate a circular or notched blank via Python sketch
GEOMETRY_SOURCE = 'cae'

# Macro mode only — unused when GEOMETRY_SOURCE='inp'
SPECIMEN_TYPE = 'circular'   # 'circular' or 'notched'
A_WIDTH       = 80.0
NOTCH_DEPTH   = 40.0
C_FILLET      = 8.0
BLANK_RADIUS  = 100.0

# ── Optional boundary conditions ──────────────────────────────
# Encastre the outer edge of the blank (the EDGE nset from the geometry .inp).
# Set True if the blank holder contact alone is insufficient to prevent rim sliding.
USE_EDGE_ENCASTRE =True
