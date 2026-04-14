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

# ──────────────────────────────────── Test type ─────────────────────────────────────────────────
import os as _os
# 'nakazima' → hemispherical punch
# 'marciniak' → flat punch (ISO 12004-2 §6.3.4)
# 'pip' → punch in punch
TEST_TYPE = _os.environ.get('TEST_TYPE', 'pip').lower()

# ── Specimen selection ────────────────────────────────────────
# Width in mm — selects geometry file W{width}.inp from INP_DIR.
# Available in Engin_Input_Files/geometries: 20, 50, 80, 100, 120, 200
SPECIMEN_WIDTH = int(_os.environ.get('SPECIMEN_WIDTH', 20))

# Path to geometry .inp files (relative to AbaqusProject/ working directory)
INP_DIR = 'geometries'

# Name of the imported specimen part (None = first non-tool part found)
SPECIMEN_PART_NAME = 'Specimen'

# ──────────────────────────── Cluster resources ─────────────────────────────────────────
NUM_CPUS = 24         # CPUs for Abaqus/Explicit (threads, mp_mode=threads)

# ───────────────────── Sheet thickness + Orientation angle ──────────────────────────────
BLANK_THICKNESS = float(_os.environ.get('BLANK_THICKNESS', 1))  # mm — varies per sheet batch
MATERIAL_ORIENTATION_ANGLE = float(_os.environ.get('MATERIAL_ORIENTATION_ANGLE', 0.0))

# ───────────────────── File naming convention ──────────────────────────────
_t        = str(BLANK_THICKNESS).replace('.', 'p')
_test_cap = TEST_TYPE.capitalize()   # 'Nakazima', 'Marciniak', or 'Pip'
_ang      = str(int(MATERIAL_ORIENTATION_ANGLE))
JOB_NAME  = '{}_W{}_t{}_ang{}'.format(_test_cap, SPECIMEN_WIDTH, _t, _ang)
CAE_NAME  = '{}_W{}_t{}_ang{}.cae'.format(TEST_TYPE, SPECIMEN_WIDTH, _t, _ang)
INP_NAME  = '{}_W{}_t{}_ang{}'.format(TEST_TYPE, SPECIMEN_WIDTH, _t, _ang)
OUTPUT_DIR = JOB_NAME   # subdirectory created per simulation run

# ── Common geometry — shared across all test types ────────────
DIE_OUTER_RADIUS = 73.0  # mm — outer radius (die and blank holder), same for both tests
DIE_HEIGHT       = 40.0  # mm — die wall height above blank
BH_HEIGHT        = 44.0  # mm — blank holder height below blank
BH_FILLET        = 4.0   # mm — blank holder inner fillet radius
PUNCH_RADIUS      = 50.0   # mm — punch radius (hemi for Nakazima, flat for Marciniak)
PUNCH_HEIGHT      = 60.0   # mm — punch cylindrical body height
PUNCH_EDGE_FILLET = 10.0   # mm — edge fillet radius (Marciniak only, 10% of diameter per ISO 12004-2)

# ── PiP (Punch-in-Punch) geometry ─────────────────────────────
# Only defined when TEST_TYPE == 'pip'; safe to read for all types.
if TEST_TYPE == 'pip':
    # Punch1 — annular outer punch (clamps blank and pre-forms outer zone)
    PIP_PUNCH1_INNER_RADIUS  = 20.0   # mm — inner bore radius (central hole)
    PIP_PUNCH1_EDGE_FILLET   = 2.0    # mm — fillet at inner bore edge
    PIP_PUNCH1_FLANGE_INNER_R = 22.0  # mm — flat flange starts here
    PIP_PUNCH1_FLANGE_OUTER_R = 28.75 # mm — flat flange ends / large fillet start
    PIP_PUNCH1_FILLET_RADIUS  = 15.0  # mm — large outer fillet radius
    PIP_PUNCH1_FILLET_CENTER_R = 28.75 # mm — fillet centre radial coordinate
    PIP_PUNCH1_FILLET_CENTER_Z = 30.0  # mm — fillet centre axial coordinate (local Y)
    PIP_PUNCH1_OUTER_RADIUS   = 43.75  # mm — outer cylindrical wall radius
    PIP_PUNCH1_HEIGHT         = 43.0   # mm — total punch height (cylindrical body)
    # Punch2 — inner hemispherical punch (forms dome in central zone)
    PIP_PUNCH2_RADIUS         = 15.0   # mm — hemisphere radius
    PIP_PUNCH2_HEIGHT         = 40.0   # mm — cylindrical body height below hemisphere
    # Die geometry (flat ring + fillet, same BH/Die outer radius as Nakazima)
    PIP_DIE_FLAT_INNER_R      = 70.0   # mm — inner edge of flat contact ring on die
    PIP_DIE_FILLET            = 15.0   # mm — die throat fillet
    PIP_DIE_INNER_WALL_R      = 55.0   # mm — die inner wall radius below fillet
    PIP_DIE_HEIGHT            = 25.0   # mm — die wall height
    PIP_BH_INNER_RADIUS       = 62.5   # mm — blank holder inner bore radius
    PIP_BH_HEIGHT             = 20.0   # mm — blank holder height
    PIP_BH_CHAMFER            = 2.0    # mm — blank holder inner chamfer
    # Process parameters
    PIP_PUNCH1_DISPLACEMENT   = 20.0   # mm — Punch1 travel in Step 1
    PIP_PUNCH2_DISPLACEMENT   = 20.0   # mm — Punch2 additional travel in Step 2
    PIP_STEP1_TIME            = 10.0   # s  — duration of Step 1 → 2 mm/s (ISO 12004-2: 0.5–2 mm/s)
    PIP_STEP2_TIME            = 10.0   # s  — duration of Step 2 → 2 mm/s
    # Friction coefficients
    FR_PUNCH1  = 0.10    # Punch1 / blank
    FR_PUNCH2  = 0.005   # Punch2 / blank (near-frictionless per PiP reference)
    FR_CLAMP   = 0.22    # Die and blank-holder / blank


# ── Test-type-specific geometry — die throat, BH inner radius ─────────────────
if TEST_TYPE == 'nakazima':
    DIE_INNER_RADIUS = 52.5  # mm — die throat radius
    DIE_FILLET       = 8.0   # mm — die throat fillet
    BH_INNER_RADIUS  = 54.5  # mm — blank holder inner radius (2 mm clearance over die)
elif TEST_TYPE == 'marciniak':  # ISO 12004-2 §6.3.4.2
    DIE_INNER_RADIUS = 60.0  # mm — 120% of punch diameter (Ø120 mm die)
    DIE_FILLET       = 12.0  # mm — 12% of punch diameter (mid of 10–20% range)
    BH_INNER_RADIUS  = 62.0  # mm — 2 mm clearance over die inner radius
elif TEST_TYPE == 'pip':
    # Punch-in-Punch — die/BH geometry from PinP_CR210H reference
    DIE_INNER_RADIUS = 55.0  # mm — die inner wall radius
    DIE_FILLET       = 15.0  # mm — die throat fillet radius
    BH_INNER_RADIUS  = 62.5  # mm — blank holder inner radius
else:
    raise ValueError("Unknown TEST_TYPE: '%s'. Expected 'nakazima', 'marciniak', or 'pip'." % TEST_TYPE)


# ── Dome zone radius for FLC post-processing ──────────────────
# Observation zone used by postproc.py to find the critical element
# ISO 12004-2 §6.3.3.3: fracture must occur within 15% of punch diameter
# from the dome apex → 0.15 × 100 mm = 15 mm.
# Overridable via R_DOME env var.
R_DOME = float(_os.environ.get('R_DOME', 0.15 * PUNCH_RADIUS * 2.0))


# ── Forming parameters ────────────────────────────────────────
PUNCH_DISPLACEMENT = 37.0                        # mm — matches Lennart reference (parameter_naka.inp)
STEP_TIME = PUNCH_DISPLACEMENT / 2.0            # s  — 2 mm/s (ISO 12004-2: 0.5–2 mm/s)
# Check ALLKE/ALLIE < 5 % in post-processing to validate quasi-static assumption.

# ── Mass scaling ──────────────────────────────────────────────
USE_MASS_SCALING = True
MASS_SCALING_DT  = 2.0e-5   # s — increased from 1e-5: v reduced 5→2 mm/s so ALLKE/ALLIE
                             #     scales as DT²×v²; 2e-5 keeps ratio well below 5% threshold

# ── Friction ──────────────────────────────────────────────────
FR_PUNCH = 0   # Coulomb coefficient — punch / blank interface (nakazima/marciniak)
if TEST_TYPE != 'pip':
    FR_CLAMP = 0.15   # Coulomb coefficient — die / blank and blank-holder / blank

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
