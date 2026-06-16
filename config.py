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
TEST_TYPE = _os.environ.get('TEST_TYPE', 'nakazima').lower()

# Width in mm — selects geometry file W{width}.inp from INP_DIR.
# Available widths: 20, 50, 80, 90, 100, 120, 200
SPECIMEN_WIDTH = int(_os.environ.get('SPECIMEN_WIDTH', 20))

# Path to geometry files (relative to AbaqusProject/ working directory)
INP_DIR = 'PiP_Geometries' if TEST_TYPE == 'pip' else 'Naka_Marciniak_Geometries'

# Name of the imported specimen part (None = first non-tool part found).
# Leave empty to auto-detect when the imported file uses a different part name.
SPECIMEN_PART_NAME = _os.environ.get('SPECIMEN_PART_NAME', 'Specimen') or None

BLANK_THICKNESS            = float(_os.environ.get('BLANK_THICKNESS', '')            or 1.5)    # mm
MATERIAL_ORIENTATION_ANGLE = float(_os.environ.get('MATERIAL_ORIENTATION_ANGLE', '') or 0.0)  # degrees


# =============================================================
# COMPUTATIONAL RESOURCES
# =============================================================
NUM_CPUS = int(_os.environ.get('NUM_CPUS', 24))   # threads for Abaqus/Explicit (mp_mode=threads)
ABAQUS_MEMORY_PERCENT = int(_os.environ.get('ABAQUS_MEMORY_PERCENT', 90))
SLURM_CPUS_PER_TASK = int(_os.environ.get('SLURM_CPUS_PER_TASK', NUM_CPUS))
SLURM_MEM_PER_CPU_GB = float(_os.environ.get('SLURM_MEM_PER_CPU_GB', 4.0))
SLURM_TIME_LIMIT = _os.environ.get('SLURM_TIME_LIMIT', '48:00:00')


# =============================================================
# GEOMETRY
# =============================================================

# ── Common — shared across all test types ────────────────────
DIE_OUTER_RADIUS  = 73.0   # mm — outer radius (die and blank holder)
DIE_HEIGHT        = 40.0   # mm — die wall height above blank
BH_HEIGHT         = 44.0   # mm — blank holder height below blank
BH_FILLET         = 4.0    # mm — blank holder inner fillet radius
PUNCH_RADIUS      = float(_os.environ.get('PUNCH_RADIUS', '') or 50.0)   # mm — punch radius (hemi for Nakazima, flat for Marciniak)
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
# 'inp' → import the specimen mesh from W{SPECIMEN_WIDTH}.inp
# 'bm'  → build the specimen mesh through Nakazima_BM.py
GEOMETRY_SOURCE = _os.environ.get('GEOMETRY_SOURCE', 'cae').lower()

# Specimen mesh backend.  The Streamlit workflow uses the BM builder only.
MESH_BACKEND = 'bm'

SPECIMEN_TYPE = 'circular'   # 'circular' or 'notched' (macro mode only)
A_WIDTH       = 80.0
NOTCH_DEPTH   = 40.0
C_FILLET      = 8.0
BLANK_RADIUS  = 100.0


# =============================================================
# MESH
# =============================================================
# Refinement factor: 1.0 = baseline; 0.5 = half element size (finer); 2.0 = coarser.
MESH_REFINEMENT_FACTOR = float(_os.environ.get('MESH_REFINEMENT_FACTOR', 2.0))

# Mesh seed strategy for imported .cae specimen parts:
#   zones           : add radial partitions + seed per MESH_ZONES table (original stable)
#   bands           : explicit (r_max mm, size mm) list — full manual control per ring
#                     size=None keeps the imported .cae seed for that band
#   outer_reseed    : keep center seeds (r<=FIXED_RADIUS) from .cae, re-seed outer
#                     region with seedEdgeBySize(h(r)) — same size on radial and
#                     circumferential edges → near-square elements, controlled growth
#   imported_scaled : scale existing CAE seeds by a radial factor
#   imported        : keep all CAE seeds as imported, only enforce thickness seeds
MESH_SEED_MODE = _os.environ.get('MESH_SEED_MODE', 'zones').lower()

# Seeding zones: (r_max mm, size_radial mm, size_circumferential mm).
# Edges are assigned the size of the first zone whose r_max exceeds their radius.
# Outer zones are silently skipped on narrow specimens.
MESH_ZONES = [
    ( 5.0, 0.1, 0.1),   # punch apex
    (20.0, 0.2, 0.2),   # punch contact zone
    (30.0, 0.2, 0.2),   # transition
    (55.0, 0.5, 0.5),   # dome shoulder
    (1e9,  1.0, 1.0),   # flange / clamped zone
]

# Cap on the outermost zone element size (applied after MR scaling).
MESH_OUTER_MAX_SIZE = float(_os.environ.get('MESH_OUTER_MAX_SIZE', 1.6))

# Keep punch-apex zone fixed during mesh sensitivity (r<5 mm stays at 0.1 mm).
MESH_CORE_FIXED = _os.environ.get('MESH_CORE_FIXED', '1').lower() not in ('0', 'false', 'no')

# Explicit radial band seeding — used when MESH_SEED_MODE = 'bands'.
# size = None → keep imported .cae seed; size = float → seedEdgeBySize(size)
MESH_SEED_BANDS = [
    (27.5, None),   # keep .cae seeds untouched up to r=27.5 mm
    (1e9,  0.8 ),   # outer zone
]

# Center seed size (mm) — should match the fine seed in the .cae (punch apex region).
# Used by outer_reseed as h_center; h_rim = MESH_CENTER_SIZE * MESH_REFINEMENT_FACTOR.
MESH_CENTER_SIZE = float(_os.environ.get('MESH_CENTER_SIZE', '') or 0.1)

# Radius (mm) below which outer_reseed / imported_scaled leave the .cae seeds untouched.
MESH_IMPORTED_FIXED_RADIUS = float(_os.environ.get('MESH_IMPORTED_FIXED_RADIUS', '') or
                                   27.5)

# Growth exponent for outer_reseed and imported_scaled (radial_growth mode).
#   1.0 = linear ramp;  >1 = stays fine longer, jumps near rim;  <1 = coarsens fast
MESH_IMPORTED_GROWTH_POWER = float(_os.environ.get('MESH_IMPORTED_GROWTH_POWER', '') or
                                   1.0)

# ── imported_scaled-only parameters ──────────────────────────────────────────
MESH_IMPORTED_SEED_SCALE = float(_os.environ.get('MESH_IMPORTED_SEED_SCALE', '') or
                                 MESH_REFINEMENT_FACTOR)
MESH_IMPORTED_SCALE_MODE = _os.environ.get('MESH_IMPORTED_SCALE_MODE',
                                           'radial_growth').lower()
MESH_IMPORTED_BAND_RADIUS = float(_os.environ.get('MESH_IMPORTED_BAND_RADIUS', '') or
                                  50.0)
MESH_OVERRIDE_THICKNESS_SEEDS = (
    _os.environ.get('MESH_OVERRIDE_THICKNESS_SEEDS', '1').lower()
    not in ('0', 'false', 'no')
)
MESH_DUMP_IMPORTED_SEEDS = (
    _os.environ.get('MESH_DUMP_IMPORTED_SEEDS', '1').lower()
    not in ('0', 'false', 'no')
)

# ── topological mode parameters ───────────────────────────────────────────────
# Multiplier applied to the core seed size read from the CAE file.
# 1.0 = keep designer's intent; 0.8 = 20 % finer; 1.2 = 20 % coarser.
MESH_CORE_SCALE = float(_os.environ.get('MESH_CORE_SCALE', '') or 1.0)

# Ratio of outer-rim seed size to (scaled) core seed size.
# outer_size = new_core_size × MESH_OUTER_GROWTH_RATIO
MESH_OUTER_GROWTH_RATIO = float(_os.environ.get('MESH_OUTER_GROWTH_RATIO', '') or 4.0)

# >1.0 enables biased seeding on spoke edges (fine at core, coarse at rim).
# The bias transitions from new_core_size to outer_size along each spoke.
MESH_RADIAL_BIAS_RATIO = float(_os.environ.get('MESH_RADIAL_BIAS_RATIO', '') or 1.0)

# XY offset (mm) of the probe point used to locate the core cell.
# Increase if the blank centre vertex sits exactly at origin.
MESH_CORE_PROBE_OFFSET = float(_os.environ.get('MESH_CORE_PROBE_OFFSET', '') or 0.5)

# Elements through blank thickness — independent of MESH_REFINEMENT_FACTOR.
N_THICKNESS_SEEDS = int(_os.environ.get('N_THICKNESS_SEEDS', 10))

# ── BM mesh backend manual controls ───────────────────────────────────────────
# When disabled, Nakazima_BM.py uses the legacy fine mesh sizes multiplied by
# MESH_REFINEMENT_FACTOR. When enabled, the BM_MESH_* values below are absolute
# target element sizes in mm and MESH_REFINEMENT_FACTOR no longer scales them.
BM_MESH_USE_MANUAL = (
    _os.environ.get('BM_MESH_USE_MANUAL', '0').lower()
    in ('1', 'true', 'yes', 'on')
)
BM_MESH_TAG = _os.environ.get('BM_MESH_TAG', '')
BM_MIRROR = (
    _os.environ.get('BM_MIRROR', '0').lower()
    in ('1', 'true', 'yes', 'on')
)
ENABLE_SYMMETRIES = (
    _os.environ.get('ENABLE_SYMMETRIES', '1').lower()
    in ('1', 'true', 'yes', 'on')
)

# Partition/geometry parameters used by the BM mesher.
BM_P_INNER_X = _os.environ.get('BM_P_INNER_X', '')
BM_P_INNER_R = _os.environ.get('BM_P_INNER_R', '')
BM_P_CIRCLE_R = _os.environ.get('BM_P_CIRCLE_R', '')
BM_P_XZPLANE_1 = _os.environ.get('BM_P_XZPLANE_1', '')
BM_W200_SECTION1_Y = _os.environ.get('BM_W200_SECTION1_Y', '')
BM_W200_SECTION2_R = _os.environ.get('BM_W200_SECTION2_R', '')
BM_W200_SECTION3_R = _os.environ.get('BM_W200_SECTION3_R', '')

# In-plane BM target element sizes in mm.
BM_MESH_SECTION1_X = _os.environ.get('BM_MESH_SECTION1_X', '')
BM_MESH_SECTION1_Y = _os.environ.get('BM_MESH_SECTION1_Y', '')
BM_MESH_SECTION2_X = _os.environ.get('BM_MESH_SECTION2_X', '')
BM_MESH_SECTION2_Y = _os.environ.get('BM_MESH_SECTION2_Y', '')
BM_MESH_SECTION3_Y = _os.environ.get('BM_MESH_SECTION3_Y', '')
BM_MESH_SECTION3_1_Y = _os.environ.get('BM_MESH_SECTION3_1_Y', '')
BM_MESH_SECTION4_Y = _os.environ.get('BM_MESH_SECTION4_Y', '')
BM_MESH_W200_SECTION1 = _os.environ.get('BM_MESH_W200_SECTION1', '')
BM_MESH_W200_SECTION2 = _os.environ.get('BM_MESH_W200_SECTION2', '')
BM_MESH_W200_SECTION3 = _os.environ.get('BM_MESH_W200_SECTION3', '')
BM_MESH_W200_SECTION4 = _os.environ.get('BM_MESH_W200_SECTION4', '')

# Dome observation zone used by postproc.py to find the critical element.
# ISO 12004-2 §6.3.3.3: fracture must occur within 15% of punch diameter.
R_DOME = 0.15 * PUNCH_RADIUS * 2.0


# =============================================================
# FORMING PARAMETERS
# =============================================================
PUNCH_DISPLACEMENT = float(_os.environ.get('PUNCH_DISPLACEMENT', '') or 35.0)  # mm
PUNCH_SPEED        = float(_os.environ.get('PUNCH_SPEED', '') or 5.0)  # mm/s
STEP_TIME          = PUNCH_DISPLACEMENT / PUNCH_SPEED
# Check ALLKE/ALLIE < 5 % in post-processing to validate quasi-static assumption.

# Punch velocity profile through the forming step:
#   'smoothstep' → SmoothStep displacement: velocity 0→peak(mid)→0 (legacy default).
#                  Velocity is never constant; it decelerates through the fracture
#                  phase, masking the Volk-Hora thinning-rate bifurcation.
#   'constant'   → constant punch velocity (= PUNCH_SPEED) with a short smooth
#                  ramp at the step ends (PUNCH_RAMP_FRACTION) so the strain rate
#                  stays steady through fracture and V&H necking is resolvable.
PUNCH_VELOCITY_PROFILE = _os.environ.get('PUNCH_VELOCITY_PROFILE', 'smoothstep').strip().lower()
PUNCH_RAMP_FRACTION    = float(_os.environ.get('PUNCH_RAMP_FRACTION', '') or 0.05)  # smooth fraction at step ends (constant profile)

USE_EDGE_ENCASTRE = True   # encastre the outer blank edge


# =============================================================
# MASS SCALING
# =============================================================
USE_MASS_SCALING = True
# Default 1e-6 s; override via MASS_SCALING_DT env var for sensitivity sweeps.
MASS_SCALING_DT = float(_os.environ.get('MASS_SCALING_DT', '') or 1.0e-5)   # s


# =============================================================
# OUTPUT FREQUENCY
# =============================================================
# Field output rate in Hz.  At PUNCH_SPEED=1 mm/s and default travel, STEP_TIME=35 s, so
# 40 Hz writes 2000 field frames (dt=0.025 s).
FIELD_OUTPUT_HZ = float(_os.environ.get('FIELD_OUTPUT_HZ', '') or 40.0)
N_FIELD_INTERVALS = int(_os.environ.get('N_FIELD_INTERVALS', '') or
                        max(1, round(STEP_TIME * FIELD_OUTPUT_HZ)))


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

# Density in Abaqus tonne-mm-s units (t/mm³).
# 2780 kg/m³  →  2780 × 1e-9 t/mm³
MATERIAL_DENSITY = 2.78e-9

# 46 VUMAT constants (see VUMAT_explicit.f header for full description).
# Unit system: tonne / mm / s   →  stress [MPa], energy [N·mm = mJ], Cp [N·mm/(t·K)]
#
# Block 1  Props  1– 8 : Elastic + thermal
# Block 2  Props  9–16 : Yield + flow  —  nAFR Hill'48  (P12, P22, P33, G12, G22, G33, M, -)
# Block 3  Props 17–24 : Hardening  —  mixed Swift-Voce  (HARDflag=3 at slot 24)
# Block 4  Props 25–32 : JC strain-rate + temperature
# Block 5  Props 33–40 : HC fracture initiation  (FAILflag at slot 40)
# Block 6  Props 41–46 : Post-initiation damage
#
# Material: 5xxx series Al-Mg alloy  (E=71 GPa, ρ=2780 kg/m³ lab-measured)
#
# Anisotropy characterisation: YLD2000-2d  m=8
#   a1=0.950041, a2=1.015801, a3=1.011741, a4=1.032842,
#   a5=1.027225, a6=1.038630, a7=1.027541, a8=1.082842
# Hill'48 P/G calibrated from YLD2000 via numerical differentiation:
#   PP (yield surface, from stress ratios): P12=-0.5013, P22=0.9734, P33=0.2318
#   GG (plastic potential, from r-values):  G12=-0.4133, G22=0.5574, G33=4.3917
#   Implied stress ratios: σ90/σ0=0.987, σ45/σ0=0.963, σb/σ0=0.985
#   Implied r-values:      r0=0.704, r45=2.320, r90=0.741
#
# HC fracture (orientation-dependent characterisation):
#   0°:  a=1.35, b0=0.70, c=0.10, n=0.10, γ=0.0, d=1.701
#   45°: a=1.35, b0=0.82, c=0.07, n=0.10, γ=0.0, d=1.701
#   90°: a=1.35, b0=0.75, c=0.08, n=0.10, γ=0.0, d=1.701
# The VUMAT HC routine uses only (a, b0, c, n) at a single orientation.
# γ and d are not consumed by this VUMAT formulation.
VUMAT_CONSTANTS = (
    # ── Props 1–8 : Elastic + thermal ─────────────────────────
    #    E [MPa]      v       Cp [N·mm/(t·K)]  Xi(TQ)   -      -      -   Forflag
    71000.0,      0.33,      8.97e8,           0.9,   0.0,   0.0,   0.0,    0.0,
    # ── Props 9–16 : nAFR Hill'48 yield + flow ────────────────
    #    P12       P22       P33      G12       G22       G33      M    -
    -0.5013,    0.9734,   0.2318,  -0.4133,   0.5574,   4.3917,  0.0, 0.0,
    # ── Props 17–24 : Mixed Swift-Voce hardening (HARDflag=3) ─
    #    A [MPa]       e0           n         s0 [MPa]      Q [MPa]       C      alpha   HARDflag
    665.5268118, 0.005871704, 0.361186334, 125.9658583, 275.7543382, 9.847337119, 0.01,    3.0,
    # ── Props 25–32 : JC rate + temperature ───────────────────
    #    eps0dot     C_JC   m_JC    T0 [°C]  Tr [°C]  Tm [°C]  epsAdot    -
    1.0e-3,          0.0,   0.0,    25.0,    25.0,    600.0,    1.0,      0.0,
    # ── Props 33–40 : HC fracture initiation (FAILflag=3) ─────
    #    a           b0      c        n       D4      D5    ADDFAIL  FAILflag
    1.35,           0.7,    0.1,     0.1,    0.0,    0.0,    0.0,     3.0,
    # ── Props 41–46 : Post-initiation damage ──────────────────
    #    D0    Dc     mD    DcMax  bMinS     k
    1.0,  2.0,  0.0,  1.0,   0.1,  1.0,
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
# POST-PROCESSING  (postproc.py thresholds & criteria)
# =============================================================
# Single source of truth for every magic number used by postproc.py
# (fracture-frame detection, V&H / SDV6 / Zone-A·B necking criteria,
# region selection, quasi-static QA).  Edit defaults here — you should
# never have to open postproc.py to tune a threshold.
#
# Each value still honours its environment-variable override (used by the
# deploy/sweep scripts), falling back to the default given here.  Keep the
# env-var NAMES identical to those postproc.py already reads, so wiring
# postproc.py to consume POSTPROC_THRESHOLDS is a drop-in follow-up and the
# existing sweep scripts keep working unchanged.
#
# Py2.7-safe (postproc.py runs under `abaqus python`): plain helpers + dict.

def _pp_float(name, default):
    raw = _os.environ.get(name, '')
    if raw is None or raw == '':
        return float(default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


def _pp_int(name, default):
    raw = _os.environ.get(name, '')
    if raw is None or raw == '':
        return int(default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return int(default)


def _pp_str(name, default):
    raw = _os.environ.get(name, '')
    return raw if raw not in (None, '') else default


def _pp_bool(name, default):
    raw = _os.environ.get(name, '')
    if raw is None or raw == '':
        return bool(default)
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


POSTPROC_THRESHOLDS = {

    # ── Dome observation zone ────────────────────────────────────────────────
    # Radius (mm) around the punch axis used to find the critical/fracture
    # element.  Defaults to the ISO 12004-2 15%-of-punch-diameter zone (R_DOME).
    'r_dome_mm':                   _pp_float('POSTPROC_R_DOME', R_DOME),
    # 'auto' = thickness axis is the smallest geometric extent; else 'x'/'y'/'z'.
    'thickness_axis':              _pp_str('POSTPROC_THICKNESS_AXIS', 'auto'),

    # ── Fracture-frame detection ─────────────────────────────────────────────
    # Detector mode for selecting the crack frame f_c:
    #   'force'  → force-peak (F-d drop) only
    #   'status' → legacy STATUS-cluster only (reproduces previous behavior)
    #   'auto'   → force first, fall back to STATUS   [recommended]
    'fracture_detector':           _pp_str('POSTPROC_FRACTURE_DETECTOR', 'auto'),
    # Min connected deleted in-plane cells to accept a STATUS fracture cluster
    # (STATUS detector / fallback only).  Mesh-COUPLED.
    'min_cluster_cells':           _pp_int('MIN_FRACTURE_CLUSTER_CELLS', 20),
    # Extra field frames kept after the detected crack frame, for visual
    # crack-frame alignment.  0 = endpoint is the last intact frame (f_c-1).
    'fracture_frame_offset':       _pp_int('POSTPROC_FRACTURE_FRAME_OFFSET', 0),

    # ── Force-based detector ─────────────────────────────────────────────────
    # Leading fraction of the force history ignored before searching for the
    # peak (skips the initial contact transient).
    'force_peak_guard_fraction':   _pp_float('POSTPROC_FORCE_PEAK_GUARD_FRACTION', 0.02),
    # Normalized post-peak force drop that defines the crack frame from history.
    'force_drop_fraction':         _pp_float('POSTPROC_FORCE_DROP_FRACTION', 0.15),

    # ── Through-thickness deletion gate (STATUS detector / fallback) ──────────
    'require_through_thickness':   _pp_bool('POSTPROC_REQUIRE_THROUGH_THICKNESS_DELETION', True),
    # Fraction of a thickness column that must delete for that cell to count as
    # cracked.  1.0 = full severance; lower = nearer crack initiation (FLC event).
    'through_thickness_fraction':  _pp_float('POSTPROC_THROUGH_THICKNESS_FRACTION', 1.0),
    'min_through_thickness_layers': _pp_int('POSTPROC_MIN_THROUGH_THICKNESS_DELETED_LAYERS', 0),

    # ── Volk-Hora necking criterion ──────────────────────────────────────────
    'vh_fracture_radius_mm':       _pp_float('POSTPROC_VH_FRACTURE_RADIUS_MM', 3.0),
    # Zone anchor: '' (legacy) | critical_eqps | point | center.
    'vh_anchor':                   _pp_str('POSTPROC_VH_ANCHOR', ''),
    'vh_fit_window_frac':          _pp_float('POSTPROC_VH_FIT_WINDOW_FRAC', 0.4),
    'vh_min_stable_points':        _pp_int('POSTPROC_VH_MIN_STABLE_POINTS', 7),
    'vh_min_unstable_points':      _pp_int('POSTPROC_VH_MIN_UNSTABLE_POINTS', 3),
    'vh_eval_back_frames':         _pp_int('POSTPROC_VH_EVAL_BACK_FRAMES', 2),
    'vh_alpha':                    _pp_float('POSTPROC_VH_ALPHA', 0.55),
    'vh_seed_count':               _pp_int('POSTPROC_VH_SEED_COUNT', 5),
    'vh_seed_fraction':            _pp_float('POSTPROC_VH_SEED_FRACTION', 0.0),
    'vh_seed_area_mm2':            _pp_float('POSTPROC_VH_SEED_AREA_MM2', 0.0),

    # ── Zone-A/B strain-rate-ratio necking criterion ─────────────────────────
    'ratio_ab_threshold':          _pp_float('POSTPROC_RATIO_AB_THRESHOLD', 7.0),
    # Reference (Zone A) probe radius and fracture-exclusion radius (mm).
    'ref_radius_mm':               _pp_float('POSTPROC_REF_RADIUS_MM', 20.0),
    'ref_exclude_radius_mm':       _pp_float('POSTPROC_REF_EXCLUDE_RADIUS_MM', 15.0),

    # ── Region / cluster selection ───────────────────────────────────────────
    'cluster_keep_count':          _pp_int('POSTPROC_CLUSTER_KEEP_COUNT', 5),
    'cluster_search_radius_mm':    _pp_float('POSTPROC_CLUSTER_SEARCH_RADIUS_MM', 5.0),
    # Max points sampled when estimating median in-plane element spacing.
    'spacing_sample_max':          _pp_int('POSTPROC_SPACING_SAMPLE_MAX', 1500),

    # ── Quasi-static QA ──────────────────────────────────────────────────────
    # Warn if max(ALLKE/ALLIE) over the forming window exceeds this (explicit
    # dynamics mass-scaling validity check).
    'qs_ratio_limit':              _pp_float('POSTPROC_QS_RATIO_LIMIT', 0.10),

    # ── Output toggles ───────────────────────────────────────────────────────
    # Write the full per-element dome strain history (large for dense meshes).
    'write_dome_history':          _pp_bool('POSTPROC_WRITE_DOME_HISTORY', False),
}


# =============================================================
# FILE NAMING
# (derived from all variables above — do not edit manually)
# =============================================================
_t           = str(BLANK_THICKNESS).replace('.', 'p')
_punch_d     = int(round(PUNCH_RADIUS * 2))
_test_prefix = {'nakazima': 'Naka', 'marciniak': 'Marc', 'pip': 'Pip'}[TEST_TYPE]
_test_cap    = _test_prefix + (str(_punch_d) if TEST_TYPE != 'pip' else '')
_ang         = str(int(MATERIAL_ORIENTATION_ANGLE))

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

_ts_suffix = ('_nt' + str(N_THICKNESS_SEEDS) if N_THICKNESS_SEEDS != 10 else '')

_ps_suffix = ('_ps' + ('%.4g' % PUNCH_SPEED).replace('.', 'p')
              if TEST_TYPE != 'pip' and abs(PUNCH_SPEED - 5.0) > 1e-6 else '')
_pd_suffix = ('_pd' + ('%.4g' % PUNCH_DISPLACEMENT).replace('.', 'p')
              if TEST_TYPE != 'pip' and abs(PUNCH_DISPLACEMENT - 35.0) > 1e-6 else '')

_bm_tag = ''.join(ch for ch in str(BM_MESH_TAG or '') if ch.isalnum())[:24]
_bm_suffix = ('_bm' + (_bm_tag or 'man')) if BM_MESH_USE_MANUAL else ''

# Velocity-profile suffix — only present for the non-default constant-speed punch,
# so constant-velocity runs get a distinct ODB/output dir and never collide with
# the smooth-step results.
_vp_suffix = ('_vconst' if PUNCH_VELOCITY_PROFILE == 'constant' else '')

JOB_NAME   = '{}_W{}_t{}_ang{}{}{}{}{}{}{}{}{}'.format(_test_cap, SPECIMEN_WIDTH, _t, _ang, _pip_suffix, _ms_suffix, _mr_suffix, _ts_suffix, _ps_suffix, _pd_suffix, _bm_suffix, _vp_suffix)
CAE_NAME   = '{}_W{}_t{}_ang{}{}{}{}{}{}{}{}{}.cae'.format(TEST_TYPE, SPECIMEN_WIDTH, _t, _ang, _pip_suffix, _ms_suffix, _mr_suffix, _ts_suffix, _ps_suffix, _pd_suffix, _bm_suffix, _vp_suffix)
INP_NAME   = '{}_W{}_t{}_ang{}{}{}{}{}{}{}{}{}'.format(TEST_TYPE, SPECIMEN_WIDTH, _t, _ang, _pip_suffix, _ms_suffix, _mr_suffix, _ts_suffix, _ps_suffix, _pd_suffix, _bm_suffix, _vp_suffix)
OUTPUT_DIR = _os.path.join(_os.environ.get('OUTPUT_BASE_DIR', _os.getcwd()), JOB_NAME)
