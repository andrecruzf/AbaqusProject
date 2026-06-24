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
NUM_CPUS = 24   # threads for Abaqus/Explicit (mp_mode=threads)


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
GEOMETRY_SOURCE = _os.environ.get('GEOMETRY_SOURCE', 'cae').lower()

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
N_THICKNESS_SEEDS = 10

# Dome observation zone used by postproc.py to find the critical element.
# ISO 12004-2 §6.3.3.3: fracture must occur within 15% of punch diameter.
R_DOME = 0.15 * PUNCH_RADIUS * 2.0


# =============================================================
# FORMING PARAMETERS
# =============================================================
PUNCH_DISPLACEMENT = 50                          # mm
PUNCH_SPEED        = float(_os.environ.get('PUNCH_SPEED', '') or 5.0)  # mm/s
STEP_TIME          = PUNCH_DISPLACEMENT / PUNCH_SPEED
# Check ALLKE/ALLIE < 5 % in post-processing to validate quasi-static assumption.

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
# Field output rate in Hz.  At PUNCH_SPEED=1 mm/s, STEP_TIME=50 s, so
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

_ps_suffix = ('_ps' + ('%.4g' % PUNCH_SPEED).replace('.', 'p')
              if TEST_TYPE != 'pip' and abs(PUNCH_SPEED - 5.0) > 1e-6 else '')

JOB_NAME   = '{}_W{}_t{}_ang{}{}{}{}{}'.format(_test_cap, SPECIMEN_WIDTH, _t, _ang, _pip_suffix, _ms_suffix, _mr_suffix, _ps_suffix)
CAE_NAME   = '{}_W{}_t{}_ang{}{}{}{}{}.cae'.format(TEST_TYPE, SPECIMEN_WIDTH, _t, _ang, _pip_suffix, _ms_suffix, _mr_suffix, _ps_suffix)
INP_NAME   = '{}_W{}_t{}_ang{}{}{}{}'.format(TEST_TYPE, SPECIMEN_WIDTH, _t, _ang, _pip_suffix, _ms_suffix, _mr_suffix)
OUTPUT_DIR = _os.path.join(_os.environ.get('OUTPUT_BASE_DIR', _os.getcwd()), JOB_NAME)
