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
import os as _os

MODEL_NAME = 'Model-1'


# =============================================================
# TEST CONFIGURATION
# =============================================================
# 'nakazima'  → hemispherical punch
# 'marciniak' → flat punch (ISO 12004-2 §6.3.4)
# 'pip'       → punch-in-punch
TEST_TYPE = _os.environ.get('TEST_TYPE', 'pip').lower()

# Width in mm — selects geometry file W{width}.inp from INP_DIR.
# Available widths: 20, 50, 80, 90, 100, 120, 200
SPECIMEN_WIDTH = int(_os.environ.get('SPECIMEN_WIDTH', 20))

# Path to geometry files (relative to AbaqusProject/ working directory)
INP_DIR = 'PiP_Geometries' if TEST_TYPE == 'pip' else 'Naka_Marciniak_Geometries'

# Name of the imported specimen part (None = first non-tool part found)
SPECIMEN_PART_NAME = 'Specimen'

BLANK_THICKNESS            = float(_os.environ.get('BLANK_THICKNESS', 1.5))         # mm
MATERIAL_ORIENTATION_ANGLE = float(_os.environ.get('MATERIAL_ORIENTATION_ANGLE', 0.0))  # degrees


# =============================================================
# COMPUTATIONAL RESOURCES
# =============================================================
NUM_CPUS = 24   # threads for Abaqus/Explicit (mp_mode=threads)


# =============================================================
# GEOMETRY
# =============================================================

# ── Common — shared across all test types ────────────────────
DIE_OUTER_RADIUS  = 73.0   # mm — outer radius (die and blank holder)
DIE_HEIGHT        = 40.0   # mm — die wall height above blank
BH_HEIGHT         = 44.0   # mm — blank holder height below blank
BH_FILLET         = 4.0    # mm — blank holder inner fillet radius
PUNCH_RADIUS      = 50.0   # mm — punch radius (hemi for Nakazima, flat for Marciniak)
PUNCH_HEIGHT      = 60.0   # mm — punch cylindrical body height
PUNCH_EDGE_FILLET = 10.0   # mm — edge fillet (Marciniak only, 10% of diameter per ISO 12004-2)

# ── Test-type-specific — die throat and blank-holder inner radius ──
if TEST_TYPE == 'nakazima':
    DIE_INNER_RADIUS = 52.5   # mm — die throat radius
    DIE_FILLET       = 8.0    # mm — die throat fillet
    BH_INNER_RADIUS  = 52.5   # mm — blank holder inner radius
elif TEST_TYPE == 'marciniak':  # ISO 12004-2 §6.3.4.2
    DIE_INNER_RADIUS = 60.0   # mm — 120% of punch diameter (Ø120 mm die)
    DIE_FILLET       = 12.0   # mm — 12% of punch diameter (mid of 10–20% range)
    BH_INNER_RADIUS  = 62.0   # mm — 2 mm clearance over die inner radius
elif TEST_TYPE == 'pip':
    DIE_INNER_RADIUS = 55.0   # mm — die inner wall radius
    DIE_FILLET       = 15.0   # mm — die throat fillet radius
    BH_INNER_RADIUS  = 62.5   # mm — blank holder inner radius
else:
    raise ValueError("Unknown TEST_TYPE: '%s'. Expected 'nakazima', 'marciniak', or 'pip'." % TEST_TYPE)

# ── PiP (Punch-in-Punch) geometry ────────────────────────────
if TEST_TYPE == 'pip':
    PIP_PUNCH_DIR    = 'PiP_Punches'
    PIP_GEOMETRY_DIR = 'PiP_Geometries'
    # Available IDs: PUNCH_1, PUNCH_2, PUNCH_21, PUNCH_23, PUNCH_24, PUNCH_25
    PIP_PUNCH2_ID    = _os.environ.get('PIP_PUNCH2_ID', 'PUNCH_21')
    PIP_PUNCH_CAE    = _os.path.join(PIP_PUNCH_DIR, '{}.cae'.format(PIP_PUNCH2_ID))

    # Punch1 — annular outer punch (clamps blank and pre-forms outer zone)
    PIP_PUNCH1_INNER_RADIUS    = 20.0    # mm — inner bore radius (central hole)
    PIP_PUNCH1_EDGE_FILLET     = 2.0     # mm — fillet at inner bore edge
    PIP_PUNCH1_FLANGE_INNER_R  = 22.0   # mm — flat flange starts here
    PIP_PUNCH1_FLANGE_OUTER_R  = 28.75  # mm — flat flange ends / large fillet start
    PIP_PUNCH1_FILLET_RADIUS   = 15.0   # mm — large outer fillet radius
    PIP_PUNCH1_FILLET_CENTER_R = 28.75  # mm — fillet centre radial coordinate
    PIP_PUNCH1_FILLET_CENTER_Z = 30.0   # mm — fillet centre axial coordinate (local Y)
    PIP_PUNCH1_OUTER_RADIUS    = 43.75  # mm — outer cylindrical wall radius
    PIP_PUNCH1_HEIGHT          = 43.0   # mm — total punch height (cylindrical body)

    # Die geometry (flat ring + fillet, same BH/Die outer radius as Nakazima)
    PIP_DIE_FLAT_INNER_R = 70.0   # mm — inner edge of flat contact ring on die
    PIP_DIE_FILLET       = 15.0   # mm — die throat fillet
    PIP_DIE_INNER_WALL_R = 55.0   # mm — die inner wall radius below fillet
    PIP_DIE_HEIGHT       = 25.0   # mm — die wall height
    PIP_BH_INNER_RADIUS  = 62.5   # mm — blank holder inner bore radius
    PIP_BH_HEIGHT        = 20.0   # mm — blank holder height
    PIP_BH_CHAMFER       = 2.0    # mm — blank holder inner chamfer

    # Process parameters
    PIP_PUNCH1_DISPLACEMENT = 20.0   # mm — Punch1 travel in Step 1
    PIP_PUNCH2_DISPLACEMENT = 20.0   # mm — Punch2 additional travel in Step 2
    PIP_STEP1_TIME          = 10.0   # s  — duration of Step 1 → 2 mm/s (ISO 12004-2: 0.5–2 mm/s)
    PIP_STEP2_TIME          = 10.0   # s  — duration of Step 2 → 2 mm/s

# ── Geometry source (macro mode) ─────────────────────────────
# 'cae' → import the specimen mesh from W{SPECIMEN_WIDTH}.cae
GEOMETRY_SOURCE = 'cae'

SPECIMEN_TYPE = 'circular'   # 'circular' or 'notched' (macro mode only)
A_WIDTH       = 80.0
NOTCH_DEPTH   = 40.0
C_FILLET      = 8.0
BLANK_RADIUS  = 100.0


# =============================================================
# MESH
# =============================================================
# Refinement factor: 1.0 = baseline; 0.5 = half element size (finer); 2.0 = coarser.
MESH_REFINEMENT_FACTOR = float(_os.environ.get('MESH_REFINEMENT_FACTOR', 4.0))

# Seeding zones: (r_max mm, size_radial mm, size_circumferential mm).
# Edges on the blank top face are assigned the size of the first zone whose
# r_max exceeds their radial position.  Outer zones skipped on narrow specimens.
MESH_ZONES = [
    ( 5.0, 0.1, 0.1),   # punch apex
    (20.0, 0.2, 0.2),   # punch contact zone
    (30.0, 0.2, 0.2),   # transition
    (55.0, 0.5, 0.5),   # dome shoulder
    (1e9,  1.0, 1.0),   # flange / clamped zone
]

# Elements through blank thickness — independent of MESH_REFINEMENT_FACTOR.
N_THICKNESS_SEEDS = 10

# Dome observation zone used by postproc.py to find the critical element.
# ISO 12004-2 §6.3.3.3: fracture must occur within 15% of punch diameter.
R_DOME = 0.15 * PUNCH_RADIUS * 2.0


# =============================================================
# FORMING PARAMETERS
# =============================================================
PUNCH_DISPLACEMENT = 37.0                          # mm
STEP_TIME          = PUNCH_DISPLACEMENT / 5.0      # s  — → 7.4 mm/s (ISO 12004-2: 0.5–2 mm/s)
# Check ALLKE/ALLIE < 5 % in post-processing to validate quasi-static assumption.

USE_EDGE_ENCASTRE = True   # encastre the outer blank edge


# =============================================================
# MASS SCALING
# =============================================================
USE_MASS_SCALING = True
# Default 1e-6 s; override via MASS_SCALING_DT env var for sensitivity sweeps.
MASS_SCALING_DT = float(_os.environ.get('MASS_SCALING_DT', 1.0e-6))   # s


# =============================================================
# FRICTION
# =============================================================
FR_PUNCH = 0.0   # Coulomb coefficient — punch / blank (nakazima/marciniak)
if TEST_TYPE != 'pip':
    FR_CLAMP = 0.35   # die / blank and blank-holder / blank
else:
    FR_PUNCH1 = 0.10    # Punch1 / blank
    FR_PUNCH2 = 0.005   # Punch2 / blank
    FR_CLAMP  = 0.22    # die and blank-holder / blank


# =============================================================
# MATERIAL / VUMAT
# =============================================================
VUMAT_PATH    = 'VUMAT_explicit.f'
MATERIAL_NAME = 'mat'   # must match the VUMAT user-material name

# 46 VUMAT constants: elastic, strength, fracture/damage, numerical
VUMAT_CONSTANTS = (
    210000, 0.3, 4.49E8, 0.9, 0.0, 0.0, 0.0, 0.0,
    -0.632037464212743, 1.02021859572227, 3.09488820610282, -0.615242, 0.932977, 2.523173, 0.0, 0.0,
    616.4216042, 0.012115207, 0.224421494, 243.5375383, 213.1450349, 10.14801667, 0.89, 3.0,
    1.E-3, 0.0, 0.0, 25, 25.0, 1200., 20., 0.0,
    1.48, 1.13, 0.05, 0.1, 0.0, 0.0, 0.0, 3.0,
    1.0, 2.0, 0.00, 1.0, 0.1, 1.0,
)

DEPVAR_COUNT  = 17
DEPVAR_DELETE = 7   # SDV index that triggers element deletion
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


# =============================================================
# FILE NAMING
# (derived from all variables above — do not edit manually)
# =============================================================
_t        = str(BLANK_THICKNESS).replace('.', 'p')
_test_cap = TEST_TYPE.capitalize()   # 'Nakazima', 'Marciniak', or 'Pip'
_ang      = str(int(MATERIAL_ORIENTATION_ANGLE))

_pip_punch2_id = _os.environ.get('PIP_PUNCH2_ID', 'PUNCH_21') if TEST_TYPE == 'pip' else None
_pip_suffix    = '_p2{}'.format(_pip_punch2_id).replace('PUNCH_', '') if _pip_punch2_id else ''

# Mass-scaling suffix — only present when MASS_SCALING_DT is explicitly
# overridden via env (e.g. by a mass-scaling sweep script).
_ms_suffix = ''
if _os.environ.get('MASS_SCALING_DT', ''):
    import math as _math
    _ms_exp  = int(_math.floor(_math.log10(MASS_SCALING_DT)))
    _ms_mant = int(round(MASS_SCALING_DT / 10 ** _ms_exp))
    _ms_suffix = '_ms%de%d' % (_ms_mant, abs(_ms_exp))

_mr_suffix = ('_mr' + ('%.4g' % MESH_REFINEMENT_FACTOR).replace('.', 'p')
              if abs(MESH_REFINEMENT_FACTOR - 1.0) > 1e-6 else '')

JOB_NAME   = '{}_W{}_t{}_ang{}{}{}{}'.format(_test_cap, SPECIMEN_WIDTH, _t, _ang, _pip_suffix, _ms_suffix, _mr_suffix)
CAE_NAME   = '{}_W{}_t{}_ang{}{}{}{}.cae'.format(TEST_TYPE, SPECIMEN_WIDTH, _t, _ang, _pip_suffix, _ms_suffix, _mr_suffix)
INP_NAME   = '{}_W{}_t{}_ang{}{}{}{}'.format(TEST_TYPE, SPECIMEN_WIDTH, _t, _ang, _pip_suffix, _ms_suffix, _mr_suffix)
OUTPUT_DIR = JOB_NAME