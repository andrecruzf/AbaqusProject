# -*- coding: utf-8 -*-
"""
postproc.py  —  Extract FLC strain path from a Nakazima/Marciniak ODB.

Standalone:
    abaqus python postproc.py -- <path/to/job.odb>

From pipeline (run_cluster.sh):
    abaqus python postproc.py -- <OUTPUT_DIR>/<JOB_NAME>.odb

Output:
    <odb_dir>/strain_path.csv      selected-region
    mean strain path plus V&H thinning-rate signal
    <odb_dir>/forming_limits.csv   fracture row plus necking rows when fits succeed
    <odb_dir>/energy_data.csv      ALLKE / ALLIE history
    <odb_dir>/punch_fd.csv         punch force-displacement history
    <odb_dir>/global.csv           dashboard-friendly merged global history
    <odb_dir>/elout.csv            ELOUT element history, when present

Algorithm:
    1. Build the dome zone: all elements whose undeformed centroid lies within
       R_DOME mm of the punch axis in the detected sheet plane. By default
       R_DOME = 15% of punch diameter, matching the ISO 12004-2 fracture
       validity zone.
    2. Find the fracture frame. By default the punch force peak is used as the
       primary endpoint and STATUS deletion is used to classify the crack; the
       previous STATUS-cluster detector remains available as fallback.
    3. Critical element: the dome-zone element with STATUS < 0.5 at the fracture frame.
       Tiebreaker (multiple simultaneous fractures): highest EQPS at frame f-1.
       Fallback (STATUS not in field output): max EQPS at frame f-1.
    4. Build a DIC/Volk-Hora-like selected region from the connected rupture
       component, evaluated before deletion, and average that fixed region.
    5. Fit the Volk-Hora signal on the last physical-time window before fracture.
       Additional lightweight criteria are evaluated on the same selected
       region: SDV6 dome-damage inflection.

Environment variables (all optional; defaults in parentheses):

  Geometry / dome zone:
    PUNCH_RADIUS : punch hemisphere radius in mm (50).
    POSTPROC_R_DOME : dome observation radius in mm; overrides the inferred ISO
        radius (default = 15% of punch diameter, R_DOME_DEFAULT = 15.0).
    POSTPROC_THICKNESS_AXIS : x | y | z | auto — sheet-normal axis (auto).
    POSTPROC_SPACING_SAMPLE_MAX : max elements sampled when estimating in-plane
        mesh spacing for connectivity (1500).

  Fracture detection:
    POSTPROC_FRACTURE_DETECTOR : force | status | auto (auto).
    POSTPROC_FORCE_PEAK_GUARD_FRACTION : leading-force fraction ignored before the
        force peak (0.02).
    POSTPROC_FORCE_DROP_FRACTION : post-peak force drop required to define the crack
        frame from history output (0.15).
    POSTPROC_FRACTURE_FRAME_OFFSET : extra field frames kept after the crack frame
        for visual alignment (0).
    POSTPROC_REQUIRE_THROUGH_THICKNESS_DELETION : require deleted STATUS columns to
        pass the through-thickness test before accepting fracture (1).
    POSTPROC_THROUGH_THICKNESS_FRACTION : fraction of a thickness column that must be
        deleted for an in-plane cell to count as cracked (1.0).
    POSTPROC_MIN_THROUGH_THICKNESS_DELETED_LAYERS : absolute min deleted layers per
        in-plane cell; combined with the fraction test (0).
    MIN_FRACTURE_CLUSTER_CELLS : min connected deleted cells to accept a dome
        fracture cluster (module default 20).

  Volk & Hora — zone selection (WHERE the neck is):
    POSTPROC_VH_FRACTURE_RADIUS_MM : half-width of the crack-line band in mm (3.0).
    POSTPROC_VH_SEED_COUNT : number of fastest-thinning seed elements (5).
    POSTPROC_VH_ALPHA : necking-zone threshold; an element joins the zone if its
        thinning rate >= alpha * peak-seed rate (0.55).
    POSTPROC_VH_DAMAGE_MAX : when the alpha zone is larger than needed, prefer
        cells whose damage D at the evaluation frame is <= this value (0.85).
    POSTPROC_VH_DAMAGE_MIN_CELLS : minimum number of acceptable-D cells required
        before applying the damage filter (5).
    POSTPROC_VH_EVAL_BACK_FRAMES : frames before fracture at which the seed rate is
        evaluated (1).

  Volk & Hora — time fit (WHEN necking starts):
    POSTPROC_VH_FIT_WINDOW_FRAC : trailing physical-time fraction used for the
        stable/unstable line fit (0.4).
    POSTPROC_VH_MIN_STABLE_POINTS : min points on the stable branch (7).
    POSTPROC_VH_MIN_UNSTABLE_POINTS : min points on the unstable branch (3).

  Other criteria / output:
    POSTPROC_QS_RATIO_LIMIT : warn if max ALLKE/ALLIE exceeds this value (0.10).
    POSTPROC_WRITE_DOME_HISTORY : also write strain_dome.csv whole-dome field (0).
"""
import sys
import os
import csv
import math
import re

# ── Centralised thresholds (config.py → POSTPROC_THRESHOLDS) ─────────────────
# Single source of truth for every post-processing magic number.  postproc.py
# runs under `abaqus python` and is usually launched from the ODB output
# directory, so put the project-root config.py on sys.path before importing it.
# Per-run env overrides still win: config.py folds POSTPROC_* env vars into the
# dict at import time, and the _env_* helpers below re-check the live env first.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
try:
    from config import POSTPROC_THRESHOLDS as _CFG
    POSTPROC_CFG = dict(_CFG)
except Exception as _cfg_err:   # standalone fallback — mirror config.py defaults
    sys.stderr.write('postproc: config.POSTPROC_THRESHOLDS unavailable (%s); '
                     'using built-in defaults\n' % _cfg_err)
    POSTPROC_CFG = {
        'r_dome_mm': 15.0, 'thickness_axis': 'auto',
        'min_cluster_cells': 20, 'fracture_frame_offset': 0,
        'fracture_detector': 'auto',
        'force_peak_guard_fraction': 0.02, 'force_drop_fraction': 0.15,
        'require_through_thickness': True, 'through_thickness_fraction': 1.0,
        'min_through_thickness_layers': 0,
        'vh_fracture_radius_mm': 3.0, 'vh_fit_window_frac': 0.4,
        'vh_min_stable_points': 7, 'vh_min_unstable_points': 3,
        'vh_eval_back_frames': 1, 'vh_alpha': 0.55, 'vh_seed_count': 5,
        'vh_damage_max': 0.85, 'vh_damage_min_cells': 5,
        'spacing_sample_max': 1500,
        'qs_ratio_limit': 0.10, 'write_dome_history': False,
    }

# Map env-var name → POSTPROC_CFG key.  The _env_* helpers consult this so that
# config.py drives every default while a live env var still overrides per run.
_ENV_TO_CFG = {
    'POSTPROC_R_DOME':                               'r_dome_mm',
    'POSTPROC_THICKNESS_AXIS':                       'thickness_axis',
    'POSTPROC_SPACING_SAMPLE_MAX':                   'spacing_sample_max',
    'POSTPROC_MIN_THROUGH_THICKNESS_DELETED_LAYERS': 'min_through_thickness_layers',
    'POSTPROC_THROUGH_THICKNESS_FRACTION':           'through_thickness_fraction',
    'MIN_FRACTURE_CLUSTER_CELLS':                    'min_cluster_cells',
    'POSTPROC_REQUIRE_THROUGH_THICKNESS_DELETION':   'require_through_thickness',
    'POSTPROC_FRACTURE_FRAME_OFFSET':                'fracture_frame_offset',
    'POSTPROC_FRACTURE_DETECTOR':                    'fracture_detector',
    'POSTPROC_FORCE_PEAK_GUARD_FRACTION':            'force_peak_guard_fraction',
    'POSTPROC_FORCE_DROP_FRACTION':                  'force_drop_fraction',
    'POSTPROC_VH_FRACTURE_RADIUS_MM':                'vh_fracture_radius_mm',
    'POSTPROC_VH_FIT_WINDOW_FRAC':                   'vh_fit_window_frac',
    'POSTPROC_VH_MIN_STABLE_POINTS':                 'vh_min_stable_points',
    'POSTPROC_VH_MIN_UNSTABLE_POINTS':               'vh_min_unstable_points',
    'POSTPROC_VH_EVAL_BACK_FRAMES':                  'vh_eval_back_frames',
    'POSTPROC_VH_ALPHA':                             'vh_alpha',
    'POSTPROC_VH_SEED_COUNT':                        'vh_seed_count',
    'POSTPROC_VH_DAMAGE_MAX':                        'vh_damage_max',
    'POSTPROC_VH_DAMAGE_MIN_CELLS':                  'vh_damage_min_cells',
    'POSTPROC_QS_RATIO_LIMIT':                       'qs_ratio_limit',
    'POSTPROC_WRITE_DOME_HISTORY':                   'write_dome_history',
}


def _cfg_default(name, fallback):
    """Config-driven default for an env var; literal fallback if unmapped."""
    key = _ENV_TO_CFG.get(name)
    if key is not None and key in POSTPROC_CFG:
        return POSTPROC_CFG[key]
    return fallback

# ── Dome zone radius ──────────────────────────────────────────────────────────
R_DOME_DEFAULT = float(POSTPROC_CFG['r_dome_mm'])              # ISO 12004-2 15% punch dia
MIN_FRACTURE_CLUSTER_CELLS = int(POSTPROC_CFG['min_cluster_cells'])
VH_FRACTURE_ZONE_RADIUS_DEFAULT = float(POSTPROC_CFG['vh_fracture_radius_mm'])

# Instance names to try for the blank in the ODB assembly
_INST_NAMES = ('SPECIMEN-1', 'Specimen-1', 'BLANK-1', 'Blank-1')


#==============================================================================
#  CONFIG / ENV PLUMBING  (read live env, fall back to config.py defaults)
#==============================================================================

def _env_int(name, default):
    default = _cfg_default(name, default)
    raw = os.environ.get(name, '')
    if raw == '':
        return int(default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return int(default)


def _env_float(name, default):
    default = _cfg_default(name, default)
    raw = os.environ.get(name, '')
    if raw == '':
        return float(default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


def _env_str(name, default):
    default = _cfg_default(name, default)
    raw = os.environ.get(name, '')
    return raw if raw != '' else default


def _resolve_r_dome(odb_path):
    for name in ('POSTPROC_R_DOME', 'R_DOME'):
        raw = os.environ.get(name, '')
        if raw:
            try:
                return max(0.0, float(raw)), name
            except (TypeError, ValueError):
                pass

    raw_radius = os.environ.get('PUNCH_RADIUS', '')
    if raw_radius:
        try:
            return 0.30 * float(raw_radius), 'PUNCH_RADIUS'
        except (TypeError, ValueError):
            pass

    m = re.search(r'(?:Naka|Marc)(\d+(?:p\d+)?)', os.path.basename(odb_path))
    if m:
        try:
            punch_diam = float(m.group(1).replace('p', '.'))
            return 0.15 * punch_diam, 'job_name'
        except (TypeError, ValueError):
            pass

    return R_DOME_DEFAULT, 'default'




#==============================================================================
#  1. FORCE-DISPLACEMENT  (punch F-d curve + fracture-frame detection)
#==============================================================================

def _punch_history_candidates(step):
    candidates = {}
    for reg_name, region in step.historyRegions.items():
        ho_keys = region.historyOutputs.keys()
        if 'U3' not in ho_keys or 'RF3' not in ho_keys:
            continue
        u3_data = region.historyOutputs['U3'].data
        rf3_data = region.historyOutputs['RF3'].data
        times = []
        u3 = []
        rf3 = []
        for (t, u3_val), (_, rf3_val) in zip(u3_data, rf3_data):
            times.append(t)
            u3.append(u3_val)
            rf3.append(rf3_val)
        if times:
            candidates[reg_name] = (times, u3, rf3)
    return candidates


def _u3_range_values(u3):
    if not u3:
        return 0.0
    return max(u3) - min(u3)


def _extract_punch_history(step):
    """
    Step-local punch history for fracture detection. Uses the same largest-U3-
    stroke region rule as punch_fd.csv. For PiP this intentionally selects one
    punch region by largest stroke.
    """
    candidates = _punch_history_candidates(step)
    if not candidates:
        return [], [], [], None
    best = max(candidates.keys(), key=lambda n: _u3_range_values(candidates[n][1]))
    times, u3, rf3 = candidates[best]
    return times, u3, rf3, best


def _write_punch_fd_csv(odb, out_dir):
    """
    Extract punch U3 (displacement) and RF3 (reaction force) history output
    and write punch_fd.csv.

    Searches all history regions across all steps for those that contain both
    U3 and RF3.  If multiple regions qualify (PiP: two punches), picks the
    one with the largest stroke range.  Time is accumulated across steps so
    the x-axis is continuous.
    """
    out_csv = os.path.join(out_dir, 'punch_fd.csv')
    t_offset = 0.0
    # candidates: region_name -> list of [step_name, t_abs, u3, rf3]
    candidates = {}

    for step in odb.steps.values():
        step_candidates = _punch_history_candidates(step)
        for reg_name, data in step_candidates.items():
            times, u3_data, rf3_data = data
            if reg_name not in candidates:
                candidates[reg_name] = []
            for t, u3, rf3 in zip(times, u3_data, rf3_data):
                candidates[reg_name].append([step.name, t_offset + t, u3, rf3])
        t_offset += step.timePeriod

    if not candidates:
        print('  WARNING: no history region with U3+RF3 found — punch_fd.csv not written.')
        return [], [], []

    def _u3_range(rows):
        return _u3_range_values([r[2] for r in rows])

    best = max(candidates.keys(), key=lambda n: _u3_range(candidates[n]))
    rows = candidates[best]
    print('  Punch F-d: region "%s"  (%d points)' % (best, len(rows)))

    with open(out_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['step_name', 'total_time_s', 'U3_mm', 'RF3_N'])
        writer.writerows(rows)

    print('  Punch F-d data  -> %s' % out_csv)
    return [r[1] for r in rows], [r[2] for r in rows], [r[3] for r in rows]


def _deleted_labels_in_frame(frame, labels_filter=None):
    deleted = set()
    if 'STATUS' not in frame.fieldOutputs.keys():
        return deleted
    for val in frame.fieldOutputs['STATUS'].values:
        if val.data >= 0.5:
            continue
        if labels_filter is not None and val.elementLabel not in labels_filter:
            continue
        deleted.add(val.elementLabel)
    return deleted


def _through_thickness_deleted_labels(deleted_labels, centroids, labels_filter=None, meta=None):
    """
    Keep deleted labels only for in-plane columns whose deleted count reaches the
    through-thickness requirement. This avoids triggering fracture from a partial
    surface/layer deletion before a visible crack has formed through the sheet.
    """
    deleted_set = set(lbl for lbl in deleted_labels if lbl in centroids)
    if not deleted_set:
        return set(), {}

    meta = meta or {'top_axis': 2}
    inplane_axes = _inplane_axes_from_meta(meta)
    labels_scope = set(labels_filter or centroids.keys())
    labels_scope &= set(centroids.keys())

    def _xy_key(lbl):
        c = centroids[lbl]
        return (
            round(c[inplane_axes[0]], 6),
            round(c[inplane_axes[1]], 6),
        )

    stack_by_xy = {}
    for lbl in labels_scope:
        stack_by_xy.setdefault(_xy_key(lbl), set()).add(lbl)

    deleted_by_xy = {}
    for lbl in deleted_set:
        deleted_by_xy.setdefault(_xy_key(lbl), set()).add(lbl)

    min_layers = max(1, _env_int('POSTPROC_MIN_THROUGH_THICKNESS_DELETED_LAYERS', 0))
    frac = max(0.0, min(1.0, _env_float('POSTPROC_THROUGH_THICKNESS_FRACTION', 1.0)))

    qualified = set()
    qualified_columns = 0
    partial_columns = 0
    max_deleted_layers = 0
    max_stack_layers = 0
    for key, dset in deleted_by_xy.items():
        stack_n = len(stack_by_xy.get(key, dset))
        deleted_n = len(dset)
        max_deleted_layers = max(max_deleted_layers, deleted_n)
        max_stack_layers = max(max_stack_layers, stack_n)
        required = max(min_layers, int(math.ceil(frac * stack_n)))
        if deleted_n >= required:
            qualified.update(dset)
            qualified_columns += 1
        else:
            partial_columns += 1

    stats = {
        'deleted_labels': len(deleted_set),
        'qualified_labels': len(qualified),
        'qualified_columns': qualified_columns,
        'partial_columns': partial_columns,
        'max_deleted_layers': max_deleted_layers,
        'max_stack_layers': max_stack_layers,
        'fraction': frac,
        'min_layers': min_layers,
    }
    return qualified, stats


def _largest_deleted_component(labels, centroids, spacing_labels=None, axes=(0, 1)):
    comps = _connected_xy_components(
        labels, centroids, spacing_labels=spacing_labels, axes=axes,
    )
    if not comps:
        return set()
    return set(max(comps, key=len))


def detect_crack_line(odb, frames, dome_labels=None, surface_only=True):
    """Detect the line of elements where the crack happened.

    The crack is the connected band of elements that STATUS-deleted by the time
    the simulation has fully cracked.  We take the last frame that has any
    deletion in the dome zone (the crack is fully propagated by then), keep the
    largest connected in-plane component, and — with ``surface_only`` — restrict
    it to top-surface elements so the result is the visible crack-line trace
    rather than the full through-thickness band.

    Returns
    -------
    dict with:
        ``labels``     : set of element labels forming the crack line
        ``centroids``  : {label: (x, y, z)} for those labels
        ``frame_idx``  : frame the crack line was read from (None if no crack)
        ``surface``    : bool, whether the result is the surface trace only
    Returns ``labels=set()`` and ``frame_idx=None`` when no deletion is found
    (e.g. a run with element deletion disabled or no fracture).
    """
    _inst, centroids, top_labels, meta = _element_centroid_maps(odb)
    inplane_axes = _inplane_axes_from_meta(meta)

    deleted = set()
    frame_idx = None
    for i in range(len(frames) - 1, -1, -1):
        d = _deleted_labels_in_frame(frames[i], labels_filter=dome_labels)
        if d:
            deleted, frame_idx = d, i
            break

    if not deleted:
        print('  Crack line     : no deleted elements found (no fracture / deletion off).')
        return {'labels': set(), 'centroids': {}, 'frame_idx': None,
                'surface': surface_only}

    # Restrict to the top surface BEFORE building connectivity.  In the deformed
    # configuration the through-thickness siblings of one column have slightly
    # different in-plane centroids, so the median-spacing metric over the full 3D
    # blob collapses to the intra-stack jitter (~0.01 mm vs the true ~0.4 mm cell
    # size).  That shrinks the connectivity radius and shatters the crack into
    # per-column clusters.  Connecting one cell per in-plane location (the surface
    # trace) keeps the spacing — and therefore the connectivity — correct.
    used_surface = False
    deleted_top = (deleted & set(top_labels)) if surface_only else set()
    if surface_only and deleted_top:
        top_dome = set(top_labels)
        if dome_labels is not None:
            top_dome &= set(dome_labels)
        crack = _largest_deleted_component(
            deleted_top, centroids,
            spacing_labels=(top_dome or deleted_top), axes=inplane_axes,
        )
        used_surface = True
    else:
        if surface_only:
            print('  Crack line     : no top-surface cells in crack band; '
                  'returning full through-thickness band instead.')
        crack = _largest_deleted_component(
            deleted, centroids, spacing_labels=dome_labels, axes=inplane_axes,
        )

    print('  Crack line     : %d elements at frame %d (%s)'
          % (len(crack), frame_idx, 'surface trace' if used_surface else 'full band'))
    return {'labels': set(crack),
            'centroids': {l: centroids[l] for l in crack if l in centroids},
            'frame_idx': frame_idx,
            'surface': used_surface}


def build_analysis_zone(odb, frames, crack, dome_labels=None,
                        failure_frame_idx=None, radius_mm=None, inner_mm=0.0,
                        label=None):
    """Top-surface band whose in-plane distance to the crack line is in
    ``[inner_mm, radius_mm]``.

    With ``inner_mm=0`` (default) this is the DIC-like strain-evaluation zone:
    every top-surface, in-dome element whose in-plane (reference-config) distance
    to the NEAREST crack-line element is <= ``radius_mm``, still alive at the
    pre-fracture frame.  Line-anchored (distance to the nearest crack cell)
    rather than a single centre + radius, so it forms a uniform-width strip that
    hugs a long crack (e.g. W200 spans ~15 mm) as well as a short one.

    With ``inner_mm > 0`` it instead returns the *ring* between ``inner_mm`` and
    ``radius_mm`` of the crack line — used to build the Zone A reference band
    offset from the neck (the "outer region" of the time-dependent FLC methods).

    ``crack`` is the dict returned by :func:`detect_crack_line`.
    ``radius_mm`` defaults to the V&H fracture-zone radius (~3 mm, the DIC band).
    ``label`` is a short tag for the diagnostic print only.

    Returns a dict with::

        labels    : set of element labels in the band
        distance  : {label: in-plane distance to the crack line [mm]}
        n         : len(labels)
        radius_mm : the band outer half-width used
        inner_mm  : the band inner radius used
    """
    if radius_mm is None:
        radius_mm = max(0.0, _env_float('POSTPROC_VH_FRACTURE_RADIUS_MM',
                                        VH_FRACTURE_ZONE_RADIUS_DEFAULT))
    tag = label or ('Analysis zone' if inner_mm <= 0 else 'Reference zone')
    crack_centroids = (crack or {}).get('centroids') or {}
    empty = {'labels': set(), 'distance': {}, 'n': 0,
             'radius_mm': radius_mm, 'inner_mm': inner_mm}
    if not crack_centroids:
        print('  %-14s : no crack line -> empty zone.' % tag)
        return empty

    _inst, centroids, top_labels, meta = _element_centroid_maps(odb)
    ax = _inplane_axes_from_meta(meta)
    a0, a1 = ax[0], ax[1]
    crack_pts = [(c[a0], c[a1]) for c in crack_centroids.values()]
    r_sq = radius_mm * radius_mm
    r_in_sq = max(0.0, inner_mm) ** 2

    candidates = set(top_labels)
    if dome_labels is not None:
        candidates &= set(dome_labels)

    # Drop cells already deleted at the pre-fracture frame (measure the live band).
    if failure_frame_idx is not None and 0 < failure_frame_idx <= len(frames):
        pre = max(0, failure_frame_idx - 1)
        candidates -= _deleted_labels_in_frame(frames[pre])

    labels = set()
    distance = {}
    for lbl in candidates:
        c = centroids.get(lbl)
        if c is None:
            continue
        px, py = c[a0], c[a1]
        d_sq = min((px - qx) ** 2 + (py - qy) ** 2 for qx, qy in crack_pts)
        if r_in_sq <= d_sq <= r_sq:
            labels.add(lbl)
            distance[lbl] = d_sq ** 0.5

    if inner_mm > 0:
        print('  %-14s : %d top-surface cells %.1f-%.1f mm from the crack line'
              % (tag, len(labels), inner_mm, radius_mm))
    else:
        print('  %-14s : %d top-surface cells within %.1f mm of the crack line'
              % (tag, len(labels), radius_mm))
    return {'labels': labels, 'distance': distance, 'n': len(labels),
            'radius_mm': radius_mm, 'inner_mm': inner_mm}


def _detect_fracture_frame_status(frames, dome_labels, all_centroids,
                                  centroid_meta, spacing_labels):
    """
    Original STATUS-based fracture detector. Kept as the reproducible fallback.
    """
    failure_frame_idx = None
    fracture_type = 'dome'
    fracture_cluster_labels = set()
    first_deletion_frame_idx = None
    first_deletion_labels = set()
    min_cluster_cells = _env_int('MIN_FRACTURE_CLUSTER_CELLS', MIN_FRACTURE_CLUSTER_CELLS)
    inplane_axes = _inplane_axes_from_meta(centroid_meta)
    require_through_thickness = bool(_env_int('POSTPROC_REQUIRE_THROUGH_THICKNESS_DELETION', 1))
    first_partial_deletion = None
    if require_through_thickness:
        print('  Fracture detect: requiring through-thickness STATUS deletion '
              '(fraction=%.2f, min_layers=%d)'
              % (
                  max(0.0, min(1.0, _env_float('POSTPROC_THROUGH_THICKNESS_FRACTION', 1.0))),
                  max(1, _env_int('POSTPROC_MIN_THROUGH_THICKNESS_DELETED_LAYERS', 0)),
              ))
    else:
        print('  Fracture detect: any connected STATUS deletion cluster')

    for i, frame in enumerate(frames):
        deleted = _deleted_labels_in_frame(frame, dome_labels)
        if not deleted:
            continue
        if require_through_thickness:
            tt_deleted, tt_stats = _through_thickness_deleted_labels(
                deleted, all_centroids, labels_filter=spacing_labels, meta=centroid_meta,
            )
            if first_partial_deletion is None:
                first_partial_deletion = (i, tt_stats)
            if not tt_deleted:
                continue
            deleted = tt_deleted
        if first_deletion_frame_idx is None:
            first_deletion_frame_idx = i
            first_deletion_labels = set(deleted)
        comp = _largest_deleted_component(
            deleted, all_centroids, spacing_labels=spacing_labels, axes=inplane_axes,
        )
        if len(comp) >= min_cluster_cells:
            failure_frame_idx = i
            fracture_cluster_labels = comp
            break

    if failure_frame_idx is None and first_deletion_frame_idx is not None:
        failure_frame_idx = first_deletion_frame_idx
        fracture_cluster_labels = _largest_deleted_component(
            first_deletion_labels, all_centroids, spacing_labels=spacing_labels,
            axes=inplane_axes,
        )
        print('  WARNING: no dome fracture cluster reached %d cells; using first deletion cluster (%d cells).'
              % (min_cluster_cells, len(fracture_cluster_labels)))
    elif failure_frame_idx is None and first_partial_deletion is not None:
        i, stats = first_partial_deletion
        print('  WARNING: only partial through-thickness deletion found in dome zone; '
              'first partial frame %d had %d deleted labels, max %d/%d layers.'
              % (i, stats.get('deleted_labels', 0),
                 stats.get('max_deleted_layers', 0), stats.get('max_stack_layers', 0)))

    if failure_frame_idx is None:
        outer_fail = None
        for i, frame in enumerate(frames):
            if 'STATUS' not in frame.fieldOutputs.keys():
                continue
            for val in frame.fieldOutputs['STATUS'].values:
                if val.data < 0.5 and (
                        dome_labels is None or val.elementLabel not in dome_labels):
                    outer_fail = i
                    break
            if outer_fail is not None:
                break

        if outer_fail is not None:
            print('  WARNING: fracture OUTSIDE dome zone at frame %d (t = %.4f s).'
                  % (outer_fail, frames[outer_fail].frameValue))
            print('           Likely outside-dome artefact — endpoint snapped to that frame.')
            failure_frame_idx = outer_fail
            fracture_type = 'outside_dome'
        else:
            print('  WARNING: no qualifying deleted elements found — using last frame.')
            failure_frame_idx = len(frames) - 1
            fracture_type = 'none'

    return {
        'failure_frame_idx': failure_frame_idx,
        'fracture_cluster_labels': fracture_cluster_labels,
        'fracture_type': fracture_type,
        'first_deletion_frame_idx': first_deletion_frame_idx,
    }


def _status_fracture_info_near_frame(frames, frame_idx, dome_labels, all_centroids,
                                     centroid_meta, spacing_labels, frame_offset=0):
    inplane_axes = _inplane_axes_from_meta(centroid_meta)
    n_frames = len(frames)
    i0 = max(0, frame_idx - 1)
    i1 = min(n_frames - 1, frame_idx + max(0, frame_offset) + 1)
    require_through_thickness = bool(_env_int('POSTPROC_REQUIRE_THROUGH_THICKNESS_DELETION', 1))

    for i in range(i0, i1 + 1):
        deleted = _deleted_labels_in_frame(frames[i], dome_labels)
        if not deleted:
            continue
        if require_through_thickness:
            tt_deleted, _stats = _through_thickness_deleted_labels(
                deleted, all_centroids, labels_filter=spacing_labels, meta=centroid_meta,
            )
            if not tt_deleted:
                continue
            deleted = tt_deleted
        comp = _largest_deleted_component(
            deleted, all_centroids, spacing_labels=spacing_labels, axes=inplane_axes,
        )
        if comp:
            return 'dome', comp, i

    for i in range(i0, i1 + 1):
        if 'STATUS' not in frames[i].fieldOutputs.keys():
            continue
        for val in frames[i].fieldOutputs['STATUS'].values:
            if val.data < 0.5 and (
                    dome_labels is None or val.elementLabel not in dome_labels):
                return 'outside_dome', set(), i

    return 'none', set(), None


def _detect_fracture_frame_force(frames, force_times, force_rf3):
    if not force_times or not force_rf3:
        return None
    n = min(len(force_times), len(force_rf3))
    if n < 3:
        return None

    # Skip leading zero-stroke/contact noise by ignoring very small initial force.
    abs_force = [abs(force_rf3[i]) for i in range(n)]
    fmax = max(abs_force)
    if fmax <= 0.0:
        return None
    guard_frac = max(0.0, min(0.5, _env_float('POSTPROC_FORCE_PEAK_GUARD_FRACTION', 0.02)))
    start = 0
    for i in range(n):
        if abs_force[i] >= guard_frac * fmax:
            start = i
            break
    if start >= n - 2:
        return None

    peak_idx = start
    for i in range(start + 1, n):
        if abs_force[i] > abs_force[peak_idx]:
            peak_idx = i
    if peak_idx >= n - 1:
        return None

    t_peak = force_times[peak_idx]

    # The force maximum is the load-instability point: the last stable state.
    # Anchor the crack frame on the peak (NOT on the drop level) so that the
    # analysis window ends at the last frame <= t_peak — the last stable frame —
    # and the localisation/crack frames never enter the strain path or rate.
    # The drop is demoted to a validation guard: require that a genuine load
    # collapse follows the peak, otherwise this is a spurious maximum and we
    # fall back to the STATUS detector.
    drop_frac = max(0.0, min(0.95, _env_float('POSTPROC_FORCE_DROP_FRACTION', 0.15)))
    drop_limit = abs_force[peak_idx] * (1.0 - drop_frac)
    drop_idx = None
    for i in range(peak_idx + 1, n):
        if abs_force[i] <= drop_limit:
            drop_idx = i
            break
    if drop_idx is None:
        return None   # no real drop after the peak -> not a fracture; use fallback
    t_drop = force_times[drop_idx]

    # Force history is sampled on the history grid, which is usually COARSER
    # than the field-output/ODB grid (the grid the strain path and the video
    # live on).  Snap the peak to the NEAREST field frame so the history/field
    # rate mismatch does not shift the endpoint by a frame.  That field frame is
    # the last stable frame (load maximum = instability onset); the crack frame
    # is the next field frame, so the endpoint f_c-1 lands on the last stable
    # frame and the localisation/crack frames stay out of the strain path/rate.
    if not frames:
        return None
    peak_frame = min(range(len(frames)),
                     key=lambda i: abs(frames[i].frameValue - t_peak))
    failure_frame_idx = min(peak_frame + 1, len(frames) - 1)
    if failure_frame_idx <= 0:
        return None
    return {
        'failure_frame_idx': failure_frame_idx,
        't_peak': t_peak,
        't_drop': t_drop,
        'drop_fraction': drop_frac,
    }




#==============================================================================
#  2. ENERGY  (ALLKE / ALLIE history)
#==============================================================================

def _write_energy_csv(odb, out_dir):
    """
    Extract ALLKE and ALLIE from history output across all steps and write
    energy_data.csv with accumulated total time for continuous x-axis.
    Steps are concatenated — total_time_s is monotonically increasing.
    """
    out_csv = os.path.join(out_dir, 'energy_data.csv')
    t_offset = 0.0
    rows = []
    first_step = True

    for step in odb.steps.values():
        ke_data = ie_data = None
        for region in step.historyRegions.values():
            ho = region.historyOutputs
            # Key may be 'ALLKE', 'ALLKE  Whole Model', etc. — search by prefix.
            ke_key = next((k for k in ho.keys() if k.startswith('ALLKE')), None)
            ie_key = next((k for k in ho.keys() if k.startswith('ALLIE')), None)
            if ke_key and ie_key:
                ke_data = ho[ke_key].data
                ie_data = ho[ie_key].data
                break

        if ke_data is None:
            print('  WARNING: ALLKE/ALLIE not found in step "%s" — skipped.' % step.name)
            t_offset += step.timePeriod
            continue

        is_new_step = 0 if first_step else 1
        first_step = False
        for (t, ke), (_, ie) in zip(ke_data, ie_data):
            rows.append([step.name, t_offset + t, ke, ie, is_new_step])
            is_new_step = 0

        t_offset += step.timePeriod

    if not rows:
        print('  WARNING: no energy data — energy_data.csv not written.')
        return [], [], []

    with open(out_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['step_name', 'total_time_s', 'ALLKE', 'ALLIE', 'is_step_boundary'])
        writer.writerows(rows)

    print('  Energy data     -> %s' % out_csv)
    return [r[1] for r in rows], [r[2] for r in rows], [r[3] for r in rows]




#==============================================================================
#  3. STRAIN PATH  (region selection + path/cluster CSV writers)
#==============================================================================

def _select_ranked_region_from_labels(odb, frames, failure_frame_idx, candidate_labels,
                                      scope, method_prefix='volk_hora', crack=None,
                                      path_source='volk_hora_selected_region',
                                      print_label='V&H selection', warning=None):
    if failure_frame_idx is None or failure_frame_idx <= 1:
        return [], {}
    candidate_labels = set(candidate_labels or [])
    if not candidate_labels:
        return [], {}
    zone_radius = max(0.0, _env_float(
        'POSTPROC_VH_FRACTURE_RADIUS_MM',
        VH_FRACTURE_ZONE_RADIUS_DEFAULT,
    ))

    # Drop any cell already deleted at the pre-fracture frame (measure the live
    # band).  build_analysis_zone already does this for failure_frame_idx, but we
    # repeat it defensively against the STATUS field directly.
    pre_last = frames[failure_frame_idx - 1]
    if 'STATUS' in pre_last.fieldOutputs.keys():
        alive_labels = set(
            val.elementLabel for val in pre_last.fieldOutputs['STATUS'].values
            if val.data >= 0.5
        )
        candidate_labels &= alive_labels
    if not candidate_labels:
        return [], {}

    times = [frames[i].frameValue for i in range(failure_frame_idx)]
    if len(times) < 2:
        return [], {}
    back_frames = max(0, _env_int('POSTPROC_VH_EVAL_BACK_FRAMES', 1))
    k_eval = max(0, min(len(times) - 1, len(times) - 1 - back_frames))
    alpha = _env_float('POSTPROC_VH_ALPHA', 0.55)
    seed_count_cfg = max(1, _env_int('POSTPROC_VH_SEED_COUNT', 5))
    damage_max = _env_float('POSTPROC_VH_DAMAGE_MAX', 0.85)
    damage_min_cells = max(1, _env_int('POSTPROC_VH_DAMAGE_MIN_CELLS', 5))

    frame_ids = sorted(set([max(0, k_eval - 1), k_eval, min(len(times) - 1, k_eval + 1)]))
    strain_by_frame = {}
    e1e2_at_eval = {}
    damage_at_eval = {}
    for fi in frame_ids:
        frame = frames[fi]
        vals = {}
        if 'LE' not in frame.fieldOutputs.keys():
            return [], {}
        for val in frame.fieldOutputs['LE'].values:
            lbl = val.elementLabel
            if lbl not in candidate_labels:
                continue
            eps1, eps2 = _principal_strains_from_LE(val)
            key = (lbl, val.integrationPoint)
            vals[key] = eps1 + eps2
            if fi == k_eval:
                e1e2_at_eval[key] = (eps1, eps2)
        strain_by_frame[fi] = vals
        if fi == k_eval and 'SDV6' in frame.fieldOutputs.keys():
            for val in frame.fieldOutputs['SDV6'].values:
                lbl = val.elementLabel
                if lbl in candidate_labels:
                    damage_at_eval[(lbl, val.integrationPoint)] = val.data

    key_set = set(strain_by_frame.get(k_eval, {}).keys())
    for fi in frame_ids:
        key_set &= set(strain_by_frame.get(fi, {}).keys())
    if not key_set:
        return [], {}

    area_map = _top_face_area_map(odb, candidate_labels)
    by_label = {}
    for key in key_set:
        lbl, ip = key
        strain_sum = []
        for fi in range(len(times)):
            if fi in strain_by_frame and key in strain_by_frame[fi]:
                strain_sum.append(strain_by_frame[fi][key])
            else:
                strain_sum.append(None)
        # For the rate we only require the local stencil around k_eval.
        local = [strain_by_frame[fi][key] for fi in frame_ids]
        if len(frame_ids) == 1:
            rate = 0.0
        elif k_eval <= 0:
            dt = times[frame_ids[-1]] - times[frame_ids[0]]
            rate = (local[-1] - local[0]) / dt if dt > 1e-12 else 0.0
        elif k_eval >= len(times) - 1:
            dt = times[frame_ids[-1]] - times[frame_ids[0]]
            rate = (local[-1] - local[0]) / dt if dt > 1e-12 else 0.0
        else:
            dt = times[k_eval + 1] - times[k_eval - 1]
            rate = ((strain_by_frame[k_eval + 1][key] -
                     strain_by_frame[k_eval - 1][key]) / dt
                    if dt > 1e-12 else 0.0)
        eps1, eps2 = e1e2_at_eval.get(key, (None, None))
        rec = {
            'ip': ip,
            'eps1': eps1,
            'eps2': eps2,
            'rate': rate,
            'area': area_map.get(lbl, 1.0),
            'damage_at_eval': damage_at_eval.get(key),
        }
        old = by_label.get(lbl)
        if old is None or rec['rate'] > old['rate']:
            by_label[lbl] = rec

    # DIC / Volk-Hora selection:
    #   1. rank all live crack-band cells by thinning rate at b-1;
    #   2. representative maximum = mean rate of the fastest seed cells;
    #   3. selected necking zone = all cells with rate >= alpha*representative.
    # This mirrors the experimental code in Post_processing_Nakazima_tests and
    # keeps POSTPROC_VH_ALPHA as the primary zone-size control.
    ranked = sorted(by_label.items(), key=lambda item: item[1]['rate'], reverse=True)
    if not ranked:
        return [], {}

    seed_count = min(seed_count_cfg, len(ranked))
    seed = ranked[:seed_count]
    seed_area = sum(max(0.0, rec.get('area', 0.0)) for _, rec in seed)
    rep_rate = (sum(rec['rate'] for _, rec in seed) / float(len(seed))) if seed else 0.0
    threshold = alpha * rep_rate
    if rep_rate > 0.0:
        zone = [(lbl, rec) for lbl, rec in ranked if rec['rate'] >= threshold]
    else:
        # Degenerate/noisy case: keep the seed so downstream diagnostics still
        # show the hottest available cells, but make the weak signal visible.
        zone = list(seed)

    damage_filter_applied = False
    damage_filter_reason = 'not_applicable'
    if damage_max < 1.0 and zone:
        if not damage_at_eval:
            damage_filter_reason = 'no_SDV6_at_eval'
        else:
            low_damage_zone = [
                (lbl, rec) for lbl, rec in zone
                if rec.get('damage_at_eval') is not None and rec.get('damage_at_eval') <= damage_max
            ]
            min_damage_keep = min(len(zone), max(seed_count, damage_min_cells))
            if len(zone) > min_damage_keep and len(low_damage_zone) >= min_damage_keep:
                zone = low_damage_zone
                damage_filter_applied = True
                damage_filter_reason = 'applied'
            elif len(low_damage_zone) < min_damage_keep:
                damage_filter_reason = 'too_few_acceptable_D'
            else:
                damage_filter_reason = 'zone_not_large_enough'
    elif damage_max >= 1.0:
        damage_filter_reason = 'disabled'

    selection_method = (
        '%s_%s_alpha%.2f_seed%d_zone%d_evalback%d_Dmax%.2f_%s'
        % (method_prefix, scope, alpha, seed_count, len(zone), back_frames,
           damage_max, damage_filter_reason)
    )
    if warning:
        selection_method += '_%s' % warning
    candidate_method = selection_method + '_candidate_pool'
    for candidate_rank, (_lbl, rec) in enumerate(ranked, 1):
        rec['candidate_rank'] = candidate_rank
        rec['candidate_count'] = len(ranked)
        rec['selection_threshold_rate'] = threshold
        rec['selection_damage_max'] = damage_max
        rec['damage_filter_applied'] = int(damage_filter_applied)
        rec['damage_filter_reason'] = damage_filter_reason
        rec['selection_method'] = candidate_method

    for rank, (lbl, rec) in enumerate(zone, 1):
        rec['selection_method'] = selection_method
        rec['selection_rank'] = rank
        rec['vh_seed_count'] = seed_count
        rec['vh_seed_area'] = seed_area
        rec['vh_zone_count'] = len(zone)
        rec['vh_alpha'] = alpha
        rec['vh_eval_frame'] = k_eval
        rec['vh_eval_time'] = times[k_eval]
        rec['selection_damage_max'] = damage_max
        rec['damage_filter_applied'] = int(damage_filter_applied)
        rec['damage_filter_reason'] = damage_filter_reason

    zone_area = sum(max(0.0, rec.get('area', 0.0)) for _, rec in zone)
    meta_out = {
        'selection_method': selection_method,
        'candidate_count': len(ranked),
        'seed_count': seed_count,
        'seed_area': seed_area,
        'zone_count': len(zone),
        'zone_area': zone_area,
        'alpha': alpha,
        'eval_frame_index': k_eval,
        'eval_time': times[k_eval],
        'scope': scope,
        'rep_seed_rate': rep_rate,
        'threshold_rate': threshold,
        'fracture_zone_radius_mm': zone_radius,
        'damage_max': damage_max,
        'damage_min_cells': damage_min_cells,
        'damage_filter_applied': damage_filter_applied,
        'damage_filter_reason': damage_filter_reason,
        'candidates': ranked,
        'path_source': path_source,
        'warning': warning or '',
        # The detected crack line, so the orchestrator can build the Zone A
        # reference band offset from the same line without re-detecting it.
        'crack': crack or {},
    }
    if warning:
        print('  WARNING: %s uses diagnostic fallback (%s); exclude from valid FLC.'
              % (print_label, warning))
    print('  %s : %s alpha, candidates=%d, seed=%d, threshold=%.4f /s, selected=%d, D<=%.2f %s, area=%.3g mm2'
          % (print_label, scope, len(ranked), seed_count, threshold, len(zone),
             damage_max, damage_filter_reason, zone_area))
    return zone, meta_out


def _select_vh_region_elements(odb, frames, failure_frame_idx, dome_labels):
    """
    Select the Volk-Hora / Engin necking zone inside the DIC-like analysis band.

    Pipeline: detect the crack line (element-deletion ground truth) -> build the
    ~3 mm top-surface band hugging that line (build_analysis_zone) -> rank band
    cells by thinning rate at the b-1 frame -> representative max = mean of the 5
    fastest -> keep every cell with rate >= alpha * representative max (Engin
    Eqs. 14-16).  The seed can be expanded by count, fraction, or physical area
    to account for FE/DIC resolution differences.  Returns the (label, rec) zone
    and a meta dict in the contract the orchestrator/Streamlit graphics expect.
    """
    if failure_frame_idx is None or failure_frame_idx <= 1:
        return [], {}
    zone_radius = max(0.0, _env_float(
        'POSTPROC_VH_FRACTURE_RADIUS_MM',
        VH_FRACTURE_ZONE_RADIUS_DEFAULT,
    ))

    # Candidate set = the DIC-like analysis band: the top-surface strip within
    # zone_radius (~3 mm) of the *detected crack line* (ground truth from element
    # deletion), line-anchored so it hugs a long crack (e.g. W200) as well as a
    # short one.  This replaces the old radius-ball around the deleted cluster,
    # which drifted onto secondary necks on wide near-equibiaxial specimens.
    crack = detect_crack_line(odb, frames, dome_labels=dome_labels, surface_only=True)
    band = build_analysis_zone(
        odb, frames, crack, dome_labels=dome_labels,
        failure_frame_idx=failure_frame_idx, radius_mm=zone_radius,
    )
    candidate_labels = set(band.get('labels') or [])
    scope = 'crackline_band_r%.1fmm' % zone_radius
    if not candidate_labels:
        print('  V&H selection : empty crack-line band -> no selection.')
        return [], {}
    return _select_ranked_region_from_labels(
        odb, frames, failure_frame_idx, candidate_labels, scope,
        method_prefix='volk_hora', crack=crack,
        path_source='volk_hora_selected_region',
        print_label='V&H selection',
    )


def _select_outside_dome_diagnostic_region(odb, frames, failure_frame_idx,
                                           dome_labels, center_label):
    """
    Diagnostic fallback for outside-dome/edge fracture artefacts.

    There is no valid dome crack line in this case, so this must not create a
    valid FLC point.  It still selects a live top-surface neighborhood around the
    critical in-dome element and writes the same cluster/neighborhood CSVs for
    inspection, all flagged with outside_dome.
    """
    if center_label is None:
        return [], {}
    _inst, centroids, top_labels, meta = _element_centroid_maps(odb)
    if center_label not in centroids or not top_labels:
        return [], {}

    zone_radius = max(0.0, _env_float(
        'POSTPROC_VH_FRACTURE_RADIUS_MM',
        VH_FRACTURE_ZONE_RADIUS_DEFAULT,
    ))
    inplane_axes = _inplane_axes_from_meta(meta)
    c0 = centroids[center_label]
    candidates = set(top_labels)
    if dome_labels is not None:
        candidates &= set(dome_labels)

    candidate_labels = set()
    for lbl in candidates:
        c = centroids.get(lbl)
        if c is None:
            continue
        dist = math.sqrt(
            (c[inplane_axes[0]] - c0[inplane_axes[0]]) ** 2 +
            (c[inplane_axes[1]] - c0[inplane_axes[1]]) ** 2
        )
        if dist <= zone_radius:
            candidate_labels.add(lbl)

    if not candidate_labels and candidates:
        seed_count = max(1, _env_int('POSTPROC_VH_SEED_COUNT', 5))
        nearest = sorted(
            candidates,
            key=lambda lbl: math.sqrt(
                (centroids[lbl][inplane_axes[0]] - c0[inplane_axes[0]]) ** 2 +
                (centroids[lbl][inplane_axes[1]] - c0[inplane_axes[1]]) ** 2
            ) if lbl in centroids else 1e30,
        )
        candidate_labels = set(nearest[:seed_count])

    if not candidate_labels:
        print('  WARNING: outside_dome diagnostic fallback found no live top-surface cells.')
        return [], {}

    scope = 'outside_dome_center_r%.1fmm' % zone_radius
    return _select_ranked_region_from_labels(
        odb, frames, failure_frame_idx, candidate_labels, scope,
        method_prefix='outside_dome_diagnostic',
        crack={},
        path_source='outside_dome_diagnostic_region',
        print_label='Diagnostic selection',
        warning='outside_dome',
    )


def _write_strain_cluster_csv(odb, frames, failure_frame_idx, dome_labels, out_dir,
                              center_label=None, search_radius=5.0,
                              fracture_cluster_labels=None, fracture_center=None,
                              selected_override=None, candidate_override=None):
    """
    Write a DIC-like diagnostic cluster:
      top-surface elements near the first deleted fracture-element cluster, alive at
      pre-fracture, plus the selected Volk-Hora necking-zone subset.
    """
    out_csv = os.path.join(out_dir, 'strain_cluster.csv')
    if failure_frame_idx is None or failure_frame_idx <= 0:
        return None

    selected = list(selected_override or [])
    if not selected:
        print('  Cluster paths : skipped (no selected necking-zone cells)')
        return None
    candidates = list(candidate_override or selected)

    _, centroids, _, meta = _element_centroid_maps(odb)
    inplane_axes = _inplane_axes_from_meta(meta)
    n_keep         = len(selected)
    selected_keys  = set((lbl, rec['ip']) for lbl, rec in selected)
    selected_map   = {(lbl, rec['ip']): rec for lbl, rec in selected}
    candidate_keys = set((lbl, rec['ip']) for lbl, rec in candidates)
    candidate_map  = {(lbl, rec['ip']): rec for lbl, rec in candidates}
    area_map = _top_face_area_map(odb, [lbl for lbl, _ in candidates])
    rank_map = dict(
        ((lbl, rec['ip']), int(rec.get('selection_rank', idx + 1)))
        for idx, (lbl, rec) in enumerate(selected)
    )
    candidate_rank_map = dict(
        ((lbl, rec['ip']), int(rec.get('candidate_rank', idx + 1)))
        for idx, (lbl, rec) in enumerate(candidates)
    )

    fracture_cluster_labels = set(fracture_cluster_labels or [])
    fracture_centers = [centroids[lbl] for lbl in fracture_cluster_labels if lbl in centroids]
    if fracture_center is not None:
        center_x, center_y, center_z = fracture_center
    elif fracture_centers:
        center_x, center_y, center_z = _cluster_center(fracture_cluster_labels, centroids)
    elif center_label is not None and center_label in centroids:
        center_x, center_y, center_z = centroids[center_label]
    else:
        center_x, center_y, center_z = 0.0, 0.0, 0.0

    eqps_by_frame = []
    damage_by_frame = []
    for fi in range(failure_frame_idx):
        frame = frames[fi]
        eqps = {}
        if 'SDV1' in frame.fieldOutputs.keys():
            for val in frame.fieldOutputs['SDV1'].values:
                key = (val.elementLabel, val.integrationPoint)
                if key in candidate_keys:
                    eqps[key] = val.data
        eqps_by_frame.append(eqps)
        damage = {}
        if 'SDV6' in frame.fieldOutputs.keys():
            for val in frame.fieldOutputs['SDV6'].values:
                key = (val.elementLabel, val.integrationPoint)
                if key in candidate_keys:
                    damage[key] = val.data
        damage_by_frame.append(damage)

    rows = []
    neighborhood_rows = []
    for fi in range(failure_frame_idx):
        frame = frames[fi]
        if 'LE' not in frame.fieldOutputs.keys():
            continue
        t = frame.frameValue
        for val in frame.fieldOutputs['LE'].values:
            key = (val.elementLabel, val.integrationPoint)
            if key not in candidate_keys:
                continue
            rec = selected_map.get(key, {})
            eps1, eps2 = _principal_strains_from_LE(val)
            c = centroids.get(val.elementLabel, (0.0, 0.0, 0.0))
            cx, cy, cz = c
            area = area_map.get(val.elementLabel, 1.0)
            if fracture_centers:
                dist = math.sqrt(min(
                    (c[inplane_axes[0]] - fc[inplane_axes[0]]) ** 2 +
                    (c[inplane_axes[1]] - fc[inplane_axes[1]]) ** 2
                    for fc in fracture_centers
                ))
            else:
                center = (center_x, center_y, center_z)
                dist = math.sqrt(
                    (c[inplane_axes[0]] - center[inplane_axes[0]]) ** 2 +
                    (c[inplane_axes[1]] - center[inplane_axes[1]]) ** 2
                )
            if key in selected_keys:
                selected_rank = rank_map[key]
                base_row = (
                    t, val.elementLabel, val.integrationPoint, selected_rank,
                    float(selected_rank) / float(n_keep),
                    cx, cy, cz, area, dist, center_label, center_x, center_y, center_z,
                    len(fracture_cluster_labels),
                    eps1, eps2,
                    eqps_by_frame[fi].get(key, 0.0),
                    damage_by_frame[fi].get(key, 0.0),
                    rec.get('damage_at_eval', ''),
                    rec.get('rate', ''),
                    rec.get('selection_threshold_rate', ''),
                    rec.get('selection_damage_max', ''),
                    rec.get('damage_filter_applied', ''),
                    rec.get('damage_filter_reason', ''),
                    rec.get('candidate_rank', ''),
                    rec.get('candidate_count', ''),
                    rec.get('selection_method',
                            'top_surface_near_first_fracture_element_cluster_r%.1fmm_thinning_top%d'
                            % (search_radius, n_keep)),
                )
                rows.append(base_row)
            candidate_rec = candidate_map.get(key, rec)
            candidate_method = candidate_rec.get(
                'selection_method',
                'top_surface_near_first_fracture_element_cluster_r%.1fmm_candidates'
                % search_radius,
            )
            neighborhood_rows.append((
                t, val.elementLabel, val.integrationPoint,
                rank_map.get(key, candidate_rank_map.get(key, 0)),
                1 if key in selected_keys else 0,
                cx, cy, cz, area, dist, center_label, center_x, center_y, center_z,
                len(fracture_cluster_labels),
                eps1, eps2,
                eqps_by_frame[fi].get(key, 0.0),
                damage_by_frame[fi].get(key, 0.0),
                candidate_rec.get('damage_at_eval', ''),
                candidate_rec.get('rate', ''),
                candidate_rec.get('selection_threshold_rate', ''),
                candidate_rec.get('selection_damage_max', ''),
                candidate_rec.get('damage_filter_applied', ''),
                candidate_rec.get('damage_filter_reason', ''),
                candidate_rec.get('candidate_rank', ''),
                candidate_rec.get('candidate_count', ''),
                candidate_method,
            ))

    with open(out_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow([
            'time_s', 'element_label', 'integration_point', 'selection_rank',
            'selection_fraction_rank', 'centroid_x', 'centroid_y', 'centroid_z',
            'top_face_area', 'distance_to_fracture_center', 'fracture_center_element',
            'fracture_center_x', 'fracture_center_y', 'fracture_center_z',
            'fracture_cluster_size',
            'eps1_major', 'eps2_minor', 'EQPS', 'D', 'D_at_eval',
            'thinning_rate_at_eval', 'selection_threshold_rate',
            'selection_damage_max', 'damage_filter_applied',
            'damage_filter_reason',
            'candidate_rank', 'candidate_count', 'selection_method',
        ])
        writer.writerows(rows)

    neigh_csv = os.path.join(out_dir, 'strain_neighborhood.csv')
    with open(neigh_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow([
            'time_s', 'element_label', 'integration_point', 'selection_rank',
            'in_major_strain_top5', 'centroid_x', 'centroid_y', 'centroid_z',
            'top_face_area', 'distance_to_fracture_center', 'fracture_center_element',
            'fracture_center_x', 'fracture_center_y', 'fracture_center_z',
            'fracture_cluster_size',
            'eps1_major', 'eps2_minor', 'EQPS', 'D', 'D_at_eval',
            'thinning_rate_at_eval', 'selection_threshold_rate',
            'selection_damage_max', 'damage_filter_applied',
            'damage_filter_reason',
            'candidate_rank', 'candidate_count', 'selection_method',
        ])
        writer.writerows(neighborhood_rows)

    selection_methods = sorted(set(rec.get('selection_method', '')
                                   for _, rec in selected if rec.get('selection_method')))
    print('  Cluster paths : %d elements (anchor %s, cluster n=%d, method=%s) -> %s'
          % (n_keep, str(center_label), len(fracture_cluster_labels),
             ','.join(selection_methods) if selection_methods else 'top_surface',
             out_csv))
    print('  Neighborhood  : %d rows for %d candidate elements (%d selected) -> %s'
          % (len(neighborhood_rows), len(candidate_keys), n_keep, neigh_csv))
    _write_strain_cluster_faces_csv(odb, out_dir, selected, center_label,
                                    fracture_cluster_labels=fracture_cluster_labels)
    return out_csv


def _write_strain_cluster_faces_csv(odb, out_dir, selected, center_label,
                                    fracture_cluster_labels=None):
    """
    Write selected cluster and first-deleted element XY cell polygons.
    """
    inst_name, centroids, top_labels, meta = _element_centroid_maps(odb)
    if not inst_name:
        print('  Cluster faces : skipped (no specimen instance)')
        return None
    inst = odb.rootAssembly.instances[inst_name]
    node_coords = {n.label: n.coordinates for n in inst.nodes}
    elem_by_label = {e.label: e for e in inst.elements}
    top_axis = int(meta.get('top_axis', 2))

    rows = []

    def add_polygon(label, role, rank):
        elem = elem_by_label.get(label)
        if elem is None:
            return
        poly = _element_xy_polygon_from_element(elem, node_coords, normal_axis=top_axis)
        for i, (x, y, z) in enumerate(poly, 1):
            rows.append((label, role, rank, i, x, y, z))

    fracture_set = set(fracture_cluster_labels or [])
    for idx, lbl in enumerate(sorted(fracture_set), 1):
        add_polygon(lbl, 'fracture_deleted', idx)

    if center_label is not None:
        add_polygon(center_label, 'first_deleted', 0)

    for idx, item in enumerate(selected, 1):
        lbl, rec = item
        if lbl == center_label:
            continue
        add_polygon(lbl, 'cluster', idx)

    if not rows:
        print('  Cluster faces : skipped (no polygons found)')
        return None

    out_csv = os.path.join(out_dir, 'strain_cluster_faces.csv')
    with open(out_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['element_label', 'role', 'selection_rank',
                         'point_order', 'x', 'y', 'z'])
        writer.writerows(rows)
    print('  Cluster faces : %d polygon vertices -> %s' % (len(rows), out_csv))
    return out_csv


def _write_top_surface_history_csv(odb, frames, failure_frame_idx, labels, out_dir,
                                   filename, method_name):
    """
    Write strain history for top-surface labels. Used for independent V&H zones.
    """
    if failure_frame_idx is None or failure_frame_idx <= 0:
        return None
    inst_name, centroids, top_labels, meta = _element_centroid_maps(odb)
    if not centroids or not top_labels:
        print('  %s: skipped (no top-surface centroids)' % method_name)
        return None

    selected_labels = set(labels) & top_labels
    active_method_name = method_name
    if not selected_labels:
        selected_labels = set(labels)
        active_method_name = method_name.replace('top_surface', 'all_layers') + '_fallback'
        print('  %s: no top-surface/dome intersection; using all %d selected labels'
              % (method_name, len(selected_labels)))
    if not selected_labels:
        print('  %s: skipped (no selected labels)' % method_name)
        return None
    area_map = _top_face_area_map(odb, selected_labels)

    rows = []
    for fi in range(failure_frame_idx):
        frame = frames[fi]
        if 'LE' not in frame.fieldOutputs.keys():
            continue
        t = frame.frameValue
        for val in frame.fieldOutputs['LE'].values:
            lbl = val.elementLabel
            if lbl not in selected_labels:
                continue
            eps1, eps2 = _principal_strains_from_LE(val)
            cx, cy, cz = centroids.get(lbl, (0.0, 0.0, 0.0))
            area = area_map.get(lbl, 1.0)
            rows.append((
                t, lbl, val.integrationPoint, cx, cy, cz, area,
                eps1, eps2, active_method_name,
            ))

    if not rows:
        print('  %s: skipped (no rows)' % method_name)
        return None

    out_csv = os.path.join(out_dir, filename)
    with open(out_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['time_s', 'element_label', 'integration_point',
                         'centroid_x', 'centroid_y', 'centroid_z', 'top_face_area',
                         'eps1_major', 'eps2_minor', 'selection_method'])
        writer.writerows(rows)
    print('  %s: %d rows for %d top-surface elements -> %s'
          % (method_name, len(rows), len(selected_labels), out_csv))
    return out_csv




#==============================================================================
#  4. V&H  (thinning-rate signal + stable/unstable fit)
#==============================================================================

def _mean_rate_history_from_element_histories(times, strain_sum_by_frame):
    """
    Return the representative V&H thinning-rate signal as the spatial mean of
    per-element rate histories. This mirrors the DIC implementation, which
    probes dEzz_dt at the selected necking-zone positions for every frame.
    """
    n = len(times)
    if n == 0:
        return []
    if n != len(strain_sum_by_frame) or n < 2:
        return [0.0] * n

    rates = []
    mean_sum = []
    for frame_map in strain_sum_by_frame:
        vals = list(frame_map.values())
        mean_sum.append(sum(vals) / float(len(vals)) if vals else None)

    for idx in range(n):
        if idx <= 0:
            i0, i1 = 0, 1
        elif idx >= n - 1:
            i0, i1 = n - 2, n - 1
        else:
            i0, i1 = idx - 1, idx + 1
        dt = times[i1] - times[i0]
        if dt <= 1e-12:
            rates.append(0.0)
            continue
        common = set(strain_sum_by_frame[i0].keys()) & set(strain_sum_by_frame[i1].keys())
        local_rates = [
            (strain_sum_by_frame[i1][key] - strain_sum_by_frame[i0][key]) / dt
            for key in common
        ]
        if local_rates:
            rates.append(sum(local_rates) / float(len(local_rates)))
        elif mean_sum[i0] is not None and mean_sum[i1] is not None:
            rates.append((mean_sum[i1] - mean_sum[i0]) / dt)
        else:
            rates.append(0.0)
    return rates


def _volk_hora_fit_indices(times, rates, fit_end_time=None):
    """
    Fit stable and unstable straight lines to the representative thinning-rate
    signal. Mirrors the Streamlit helper, returning frame indices in this path.
    """
    fit_window_frac = max(0.1, min(1.0, _env_float('POSTPROC_VH_FIT_WINDOW_FRAC', 0.4)))
    min_stable = max(2, _env_int('POSTPROC_VH_MIN_STABLE_POINTS', 7))
    min_unstable = max(2, _env_int('POSTPROC_VH_MIN_UNSTABLE_POINTS', 3))
    if len(times) < min_stable + min_unstable or len(rates) != len(times):
        return None
    t_fit_end = times[-1] if fit_end_time is None else float(fit_end_time)
    t_min_fit = times[0] + (1.0 - fit_window_frac) * (t_fit_end - times[0])
    valid_indices = [
        i for i in range(1, len(times) - 1)
        if times[i] >= t_min_fit and times[i] <= t_fit_end
    ]
    if len(valid_indices) < min_stable + min_unstable:
        return None
    x = [times[i] for i in valid_indices]
    y = [rates[i] for i in valid_indices]
    n = len(x)
    if n < min_stable + min_unstable:
        return None

    def _line_fit(xs, ys):
        n_pts = len(xs)
        if n_pts < 2:
            return None
        sx = sum(xs); sy = sum(ys)
        sxx = sum(v * v for v in xs)
        sxy = sum(xs[i] * ys[i] for i in range(n_pts))
        denom = n_pts * sxx - sx * sx
        if abs(denom) < 1e-20:
            return None
        m = (n_pts * sxy - sx * sy) / denom
        q = (sy - m * sx) / n_pts
        mse = sum((ys[i] - (m * xs[i] + q)) ** 2 for i in range(n_pts)) / n_pts
        return m, q, mse

    best_stable = None
    for count in range(min_stable, n - min_unstable + 1):
        fit = _line_fit(x[:count], y[:count])
        if fit is not None and (best_stable is None or fit[2] < best_stable['mse']):
            best_stable = {'count': count, 'slope': fit[0],
                           'intercept': fit[1], 'mse': fit[2]}

    best_unstable = None
    for count in range(min_unstable, n - min_stable + 1):
        fit = _line_fit(x[n - count:], y[n - count:])
        if fit is not None and (best_unstable is None or fit[2] < best_unstable['mse']):
            best_unstable = {'count': count, 'slope': fit[0],
                             'intercept': fit[1], 'mse': fit[2]}
    if best_stable is None or best_unstable is None:
        return None

    denom = best_stable['slope'] - best_unstable['slope']
    if denom >= 0:
        return None
    t_cross = (best_unstable['intercept'] - best_stable['intercept']) / denom
    if t_cross < x[0] or t_cross > x[-1]:
        return None
    kcrit = None
    for i, tv in enumerate(times):
        if tv >= t_cross:
            kcrit = i
            break
    if kcrit is None or kcrit <= 0:
        return None
    return {
        't_cross': t_cross,
        'kcrit': kcrit,
        'kstable': kcrit - 1,
        'stable': best_stable,
        'unstable': best_unstable,
    }




#==============================================================================
#  5. ZONE A/B  (ratio computed inline in the orchestrator; no module fn)
#==============================================================================



#==============================================================================
#  6. FORMING LIMITS  (limits computed inline in the orchestrator; no module fn)
#==============================================================================



#==============================================================================
#  7. CLUSTER LOCATION  (specimen outline for cluster-location diagnostic)
#==============================================================================

def _write_specimen_outline_csv(odb, out_dir):
    """
    Export the initial top-view FE specimen outline from the top element layer.
    """
    inst_name, centroids, top_labels, meta = _element_centroid_maps(odb)
    if not inst_name or not top_labels:
        print('  Specimen outline: skipped (no initial top-layer elements)')
        return None

    inst = odb.rootAssembly.instances[inst_name]
    node_coords = {n.label: n.coordinates for n in inst.nodes}
    edge_counts = {}
    top_axis = int(meta.get('top_axis', 2))
    inplane_axes = _inplane_axes_from_meta(meta)
    top_faces = _top_surface_faces_from_connectivity(inst, node_coords, top_axis)
    if not top_faces:
        print('  Specimen outline: skipped (no external initial top faces)')
        return None

    for _elem_label, top_nodes in top_faces:
        local_edges = set()
        n_top = len(top_nodes)
        if n_top == 4:
            cx = sum(node_coords[n][inplane_axes[0]] for n in top_nodes) / 4.0
            cy = sum(node_coords[n][inplane_axes[1]] for n in top_nodes) / 4.0
            ordered = sorted(
                top_nodes,
                key=lambda n: math.atan2(node_coords[n][inplane_axes[1]] - cy,
                                         node_coords[n][inplane_axes[0]] - cx),
            )
            for i in range(4):
                local_edges.add(tuple(sorted((ordered[i], ordered[(i + 1) % 4]))))
        else:
            for i in range(n_top):
                for j in range(i + 1, n_top):
                    local_edges.add(tuple(sorted((top_nodes[i], top_nodes[j]))))

        for edge in local_edges:
            edge_counts[edge] = edge_counts.get(edge, 0) + 1

    boundary_edges = [edge for edge, count in edge_counts.items() if count == 1]
    if not boundary_edges:
        print('  Specimen outline: skipped (no boundary edges found)')
        return None

    out_csv = os.path.join(out_dir, 'specimen_outline.csv')
    with open(out_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['x1', 'y1', 'z1', 'x2', 'y2', 'z2', 'edge_id'])
        for idx, (n1, n2) in enumerate(boundary_edges, 1):
            c1 = node_coords[n1]
            c2 = node_coords[n2]
            writer.writerow([
                c1[inplane_axes[0]], c1[inplane_axes[1]], c1[top_axis],
                c2[inplane_axes[0]], c2[inplane_axes[1]], c2[top_axis],
                idx,
            ])

    print('  Specimen outline: %d initial top-layer boundary edges -> %s' % (len(boundary_edges), out_csv))
    return out_csv




#==============================================================================
#  8. DIAGNOSTICS / ELOUT  (element history + global CSV)
#==============================================================================

def _get_elout_label(odb):
    """Return the element label for ELOUT from the ODB assembly or instance elsets."""
    asm = odb.rootAssembly
    if 'ELOUT' in asm.elementSets.keys():
        elems = asm.elementSets['ELOUT'].elements
        if elems:
            return elems[0].label
    for inst_name in _INST_NAMES:
        if inst_name not in asm.instances.keys():
            continue
        inst = asm.instances[inst_name]
        if 'ELOUT' in inst.elementSets.keys():
            elems = inst.elementSets['ELOUT'].elements
            if elems:
                return elems[0].label
    return None


def _find_elout_history(odb, elout_label):
    """
    Return dict {ip_number: (region_name, data_dict, times_list)} for all
    history regions belonging to elout_label that contain LE11.
    Uses the last step that has LE data (the forming step).
    """
    ip_regions = {}
    for step in odb.steps.values():
        for rname, region in step.historyRegions.items():
            if 'Int Point' not in rname:
                continue
            if str(elout_label) not in rname:
                continue
            ho = region.historyOutputs
            if 'LE11' not in ho.keys():
                continue
            try:
                ip = int(rname.split('Int Point')[-1].strip())
            except (ValueError, IndexError):
                ip = 1
            times = [t for t, v in ho['LE11'].data]
            data  = {k: [v for t, v in ho[k].data] for k in ho.keys()}
            ip_regions[ip] = (rname, data, times)
    return ip_regions


def extract_elout(odb_path):
    """
    Extract the ELOUT apex element history output.

    Reads LE tensor components directly from historyRegions — no frame looping.
    Writes only elout.csv (via write_elout_csv).  Does NOT touch strain_path.csv
    or forming_limits.csv — those belong exclusively to extract_strain_path.
    energy_data.csv and punch_fd.csv are shared and not re-written if they
    already exist from extract_strain_path.
    """
    from odbAccess import openOdb

    odb_path = os.path.abspath(odb_path)
    out_dir  = os.path.dirname(odb_path)

    print('=' * 60)
    print('  postproc.py  —  ELOUT element history extraction')
    print('  ODB : %s' % odb_path)
    print('=' * 60)

    odb = openOdb(odb_path, readOnly=True)

    elout_label = _get_elout_label(odb)
    if elout_label is None:
        print('  SKIP: ELOUT elset not found in ODB — was the model built with '
              'the current job.py?')
        odb.close()
        return None

    print('  ELOUT element : %d' % elout_label)

    ip_regions = _find_elout_history(odb, elout_label)
    if not ip_regions:
        print('  SKIP: no LE history found for element %d.' % elout_label)
        odb.close()
        return None

    # Highest IP = top surface (outermost section point for shell)
    ip_top = max(ip_regions.keys())
    rname, data, times = ip_regions[ip_top]
    print('  History region: %s  (%d points)' % (rname, len(times)))
    if len(ip_regions) > 1:
        print('  Integration points found: %s  — using IP %d'
              % (sorted(ip_regions.keys()), ip_top))

    # Principal strains from LE components
    e11 = data['LE11'];  e22 = data['LE22'];  e33 = data['LE33']
    e12 = data.get('LE12', [0.0] * len(times))
    e13 = data.get('LE13', [0.0] * len(times))
    e23 = data.get('LE23', [0.0] * len(times))
    eps1_list = []; eps2_list = []
    for i in range(len(times)):
        e1, e2 = _principal_strains_from_components(
            e11[i], e22[i], e33[i], e12[i], e13[i], e23[i])
        eps1_list.append(e1); eps2_list.append(e2)

    # Principal plastic strains from LEP components
    lep11 = data.get('LEP11', [0.0] * len(times))
    lep22 = data.get('LEP22', [0.0] * len(times))
    lep33 = data.get('LEP33', [0.0] * len(times))
    lep12 = data.get('LEP12', [0.0] * len(times))
    lep13 = data.get('LEP13', [0.0] * len(times))
    lep23 = data.get('LEP23', [0.0] * len(times))
    eps1p_list = []; eps2p_list = []
    for i in range(len(times)):
        e1p, e2p = _principal_strains_from_components(
            lep11[i], lep22[i], lep33[i], lep12[i], lep13[i], lep23[i])
        eps1p_list.append(e1p); eps2p_list.append(e2p)

    fail_list = data.get('SDV7', [0.0] * len(times))

    # Fracture: first point where SDV7 (FAIL switch) drops below 0.5.
    # Abaqus DELETE convention: deletevar=1 → alive, drops to 0 → deleted.
    fracture_idx = None
    for i, f in enumerate(fail_list):
        if f < 0.5:
            fracture_idx = i; break
    if fracture_idx is None:
        fracture_idx = len(times) - 1
        print('  NOTE: SDV7 never reached 0.5 — using all %d points.' % len(times))
    else:
        print('  Fracture      : t = %.4f s  (point %d / %d)'
              % (times[fracture_idx], fracture_idx, len(times) - 1))

    n = fracture_idx
    if n < 5:
        print('  SKIP: fewer than 5 points before fracture.')
        odb.close(); return None

    times_c = times[:n]

    print('  ELOUT rows    : %d points before fracture/end.' % len(times_c))

    # energy_data.csv and punch_fd.csv — only write if not already present
    if not os.path.isfile(os.path.join(out_dir, 'energy_data.csv')):
        _write_energy_csv(odb, out_dir)
    if not os.path.isfile(os.path.join(out_dir, 'punch_fd.csv')):
        _write_punch_fd_csv(odb, out_dir)

    # Build return dict: computed principal strains + all raw history quantities
    _skip = {'eps1_le', 'eps2_le', 'eps1_lep', 'eps2_lep', 'times'}
    result = {
        'times':    times_c,
        'eps1_le':  eps1_list[:n],
        'eps2_le':  eps2_list[:n],
        'eps1_lep': eps1p_list[:n],
        'eps2_lep': eps2p_list[:n],
    }
    for key, vals in data.items():
        if key not in _skip:
            result[key] = vals[:n]

    odb.close()
    print('=' * 60)
    return result


def _interp_onto(t_ref, t_src, vals):
    """Linear interpolation of vals(t_src) onto t_ref; clamps at boundaries."""
    if not t_src or not vals:
        return [None] * len(t_ref)
    n = len(t_src)
    out = []
    for t in t_ref:
        if t <= t_src[0]:
            out.append(vals[0])
        elif t >= t_src[-1]:
            out.append(vals[-1])
        else:
            lo, hi = 0, n - 1
            while hi - lo > 1:
                mid = (lo + hi) // 2
                if t_src[mid] <= t:
                    lo = mid
                else:
                    hi = mid
            dt = t_src[hi] - t_src[lo]
            if dt < 1e-15:
                out.append(vals[lo])
            else:
                alpha = (t - t_src[lo]) / dt
                out.append(vals[lo] + alpha * (vals[hi] - vals[lo]))
    return out


def write_elout_csv(out_dir, elout_data):
    """
    Write elout.csv — ELOUT apex element history only.

    Time axis: ELOUT sampling (100 intervals up to element deletion or end of sim).
    Columns: time_s, eps1_le, eps2_le, eps1_lep, eps2_lep, LE*, S*, SP*, SDV*, scalars.
    """
    if elout_data is None:
        print('  WARNING: no ELOUT data — elout.csv not written.')
        return

    skip = {'times'}

    def _sort_key(k):
        if k in ('eps1_le', 'eps2_le', 'eps1_lep', 'eps2_lep'):
            return (0, 0, k)
        if k.startswith('SDV'):
            try:
                return (4, int(k[3:]), '')
            except ValueError:
                pass
        prefix_order = {'LE': 1, 'LEP': 2, 'S': 3, 'SP': 3}
        for pfx, order in prefix_order.items():
            if k.startswith(pfx):
                return (order, 0, k)
        scalar_order = {'MISES': 5, 'PEEQ': 5, 'TRIAX': 5}
        return (scalar_order.get(k, 6), 0, k)

    keys = sorted([k for k in elout_data if k not in skip], key=_sort_key)
    header = ['time_s'] + keys

    out_csv = os.path.join(out_dir, 'elout.csv')
    n = len(elout_data['times'])
    with open(out_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for i in range(n):
            row = [elout_data['times'][i]] + [
                elout_data[k][i] if k in elout_data and i < len(elout_data[k]) else ''
                for k in keys
            ]
            writer.writerow(row)

    print('  ELOUT CSV       -> %s  (%d rows x %d cols)' % (out_csv, n, len(header)))


def write_global_csv(out_dir, field_data):
    """
    Write global.csv — full-simulation quantities independent of the ELOUT element.

    Time axis: punch historyRegion times (full simulation, native rate).
    Columns: time_s, U3_mm, RF3_N, ALLKE, ALLIE, d_dome_max, fracture_type.
    Energy is linearly interpolated onto the punch time axis.
    d_dome_max is matched by nearest field-output frame time.
    """
    if field_data is None:
        print('  WARNING: no field data — global.csv not written.')
        return

    def _nearest(t, src_times, src_vals):
        if not src_times:
            return ''
        best = min(range(len(src_times)), key=lambda i: abs(src_times[i] - t))
        return src_vals[best]

    if field_data.get('punch_times'):
        t_ref   = field_data['punch_times']
        u3_col  = field_data['U3_mm']
        rf3_col = field_data['RF3_N']
    else:
        t_ref   = field_data['times']
        u3_col  = [None] * len(t_ref)
        rf3_col = [None] * len(t_ref)

    if field_data.get('energy_times'):
        allke_col = _interp_onto(t_ref, field_data['energy_times'], field_data['ALLKE'])
        allie_col = _interp_onto(t_ref, field_data['energy_times'], field_data['ALLIE'])
    else:
        allke_col = [None] * len(t_ref)
        allie_col = [None] * len(t_ref)

    f_times    = field_data['times']
    d_dome_col = [_nearest(t, f_times, field_data['d_dome_max']) for t in t_ref]
    frac_col   = [field_data['fracture_type']] * len(t_ref)

    header = ['time_s', 'U3_mm', 'RF3_N', 'ALLKE', 'ALLIE', 'd_dome_max', 'fracture_type']

    out_csv = os.path.join(out_dir, 'global.csv')
    n = len(t_ref)
    with open(out_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for i in range(n):
            row = [t_ref[i], u3_col[i], rf3_col[i],
                   allke_col[i], allie_col[i],
                   d_dome_col[i], frac_col[i]]
            writer.writerow(row)

    print('  Global CSV      -> %s  (%d rows x %d cols)' % (out_csv, n, len(header)))




#==============================================================================
#  ORCHESTRATION  (single-pass ODB extractor; calls sections in tab order)
#==============================================================================

def extract_strain_path(odb_path, out_csv=None, r_dome=None):
    from odbAccess import openOdb

    odb_path = os.path.abspath(odb_path)
    if out_csv is None:
        out_csv = os.path.join(os.path.dirname(odb_path), 'strain_path.csv')
    if r_dome is None:
        r_dome, r_dome_source = _resolve_r_dome(odb_path)
    else:
        r_dome_source = 'argument'

    print('=' * 60)
    print('  postproc.py — strain path extraction')
    print('  ODB    : %s' % odb_path)
    print('  R_DOME : %.1f mm  (source=%s, ISO 15%% punch diameter zone)' %
          (r_dome, r_dome_source))
    print('=' * 60)

    if not os.path.isfile(odb_path):
        print('ERROR: ODB not found: %s' % odb_path)
        return None

    odb      = openOdb(odb_path, readOnly=True)
    step     = list(odb.steps.values())[0]
    frames   = step.frames
    n_frames = len(frames)
    print('  Step   : %s' % step.name)
    print('  Frames : %d' % n_frames)

    # ── 1. Build dome zone ────────────────────────────────────
    dome_labels, inst_name, dome_radii = _build_dome_set(odb, r_dome)

    # ── 2. Find fracture frame ─────────────────────────────────
    fracture_type = 'dome'
    failure_frame_idx = None
    fracture_cluster_labels = set()
    min_cluster_cells = _env_int('MIN_FRACTURE_CLUSTER_CELLS', MIN_FRACTURE_CLUSTER_CELLS)
    _, all_centroids, _, centroid_meta = _element_centroid_maps(odb)
    inplane_axes = _inplane_axes_from_meta(centroid_meta)
    spacing_labels = dome_labels if dome_labels is not None else all_centroids.keys()
    frame_offset = max(0, _env_int('POSTPROC_FRACTURE_FRAME_OFFSET', 0))
    detector_mode = _env_str('POSTPROC_FRACTURE_DETECTOR', 'auto').strip().lower()
    if detector_mode not in ('auto', 'force', 'status'):
        print('  WARNING: invalid POSTPROC_FRACTURE_DETECTOR=%s; using auto.'
              % detector_mode)
        detector_mode = 'auto'

    force_times, force_u3, force_rf3, force_region = _extract_punch_history(step)
    force_result = None
    detector_used = None
    t_peak = None
    t_drop = None

    if detector_mode in ('auto', 'force'):
        force_result = _detect_fracture_frame_force(frames, force_times, force_rf3)
        if force_result is None:
            print('  WARNING: force-based fracture detection unavailable; '
                  'falling back to STATUS detector.')
        else:
            failure_frame_idx = force_result['failure_frame_idx']
            t_peak = force_result['t_peak']
            t_drop = force_result.get('t_drop')
            detector_used = 'force'
            fracture_type, fracture_cluster_labels, status_frame = _status_fracture_info_near_frame(
                frames, failure_frame_idx, dome_labels, all_centroids,
                centroid_meta, spacing_labels, frame_offset=frame_offset,
            )
            if fracture_type == 'none':
                print('  WARNING: force peak defines endpoint but no STATUS deletion was found near frame %d.'
                      % failure_frame_idx)
            elif fracture_type == 'outside_dome':
                print('  WARNING: force peak endpoint has only outside-dome STATUS deletion near frame %d.'
                      % failure_frame_idx)

    if failure_frame_idx is None:
        status_result = _detect_fracture_frame_status(
            frames, dome_labels, all_centroids, centroid_meta, spacing_labels,
        )
        failure_frame_idx = status_result.get('failure_frame_idx')
        fracture_cluster_labels = status_result.get('fracture_cluster_labels') or set()
        fracture_type = status_result.get('fracture_type') or 'none'
        detector_used = 'status'

    force_summary = ''
    if t_peak is not None:
        force_summary = ', t_peak=%.4f s' % t_peak
        if t_drop is not None:
            force_summary += ', t_drop=%.4f s' % t_drop

    print('  Detection summary: detector=%s%s, frame=%s, type=%s, cluster=%d'
          % (
              detector_used or 'none',
              force_summary,
              str(failure_frame_idx),
              fracture_type,
              len(fracture_cluster_labels),
          ))

    if failure_frame_idx == 0:
        print('  ERROR: failure at frame 0 — check ODB.')
        odb.close()
        return None

    path_end_frame_idx = min(n_frames - 1, failure_frame_idx + frame_offset)
    if frame_offset:
        print('  Fracture frame offset: +%d frames for visual endpoint alignment '
              '(detected frame %d -> endpoint frame %d)'
              % (frame_offset, failure_frame_idx, path_end_frame_idx))

    if fracture_type == 'dome':
        print('  Fracture type  : dome  (frame %d, t = %.4f s, cluster threshold=%d cells)'
              % (failure_frame_idx, frames[failure_frame_idx].frameValue, min_cluster_cells))
    elif fracture_type == 'outside_dome':
        print('  Fracture type  : outside_dome (artefact) — endpoint = frame %d'
              % failure_frame_idx)
    else:
        print('  Fracture type  : none — using last frame')

    # ── 3. Critical element: the element that fractured at failure_frame_idx ──
    # Read STATUS at the fracture frame directly — no EQPS proxy.
    # If multiple dome-zone elements fracture simultaneously, pick the one
    # with the highest EQPS at frame f-1 as a tiebreaker.
    frac_frame  = frames[failure_frame_idx]
    pre_frame   = frames[failure_frame_idx - 1]
    crit_label  = None
    crit_ip     = None
    frac_labels = set(fracture_cluster_labels)

    if 'STATUS' in frac_frame.fieldOutputs.keys():
        if not frac_labels:
            frac_labels = _deleted_labels_in_frame(frac_frame, dome_labels)

        if frac_labels and 'SDV1' in pre_frame.fieldOutputs.keys():
            # Tiebreaker: highest EQPS at pre-fracture frame among fractured elements
            eqps_field = pre_frame.fieldOutputs['SDV1']
            max_eqps   = -1.0
            for val in eqps_field.values:
                if val.elementLabel in frac_labels and val.data > max_eqps:
                    max_eqps   = val.data
                    crit_label = val.elementLabel
                    crit_ip    = val.integrationPoint
        elif frac_labels:
            crit_label = next(iter(frac_labels))
            crit_ip    = 1
            max_eqps   = 0.0

    # Fallback: max EQPS in dome at pre-failure frame (STATUS not available)
    if crit_label is None and 'SDV1' in pre_frame.fieldOutputs.keys():
        eqps_field = pre_frame.fieldOutputs['SDV1']
        max_eqps   = -1.0
        for val in eqps_field.values:
            in_dome = (dome_labels is None) or (val.elementLabel in dome_labels)
            if in_dome and val.data > max_eqps:
                max_eqps   = val.data
                crit_label = val.elementLabel
                crit_ip    = val.integrationPoint

    if crit_label is None:
        print('  ERROR: no elements found in dome zone — check R_DOME.')
        odb.close()
        return None

    # Identify the connected fracture-element cluster in the dome.  This cluster,
    # not a single tiebreaker element, anchors all local V&H neighborhood data.
    if not fracture_cluster_labels:
        fracture_cluster_labels = set([crit_label])
    if frac_labels and all_centroids:
        comps = _connected_xy_components(frac_labels, all_centroids,
                                         spacing_labels=spacing_labels,
                                         axes=inplane_axes)
        if comps:
            containing = [c for c in comps if crit_label in c]
            if containing:
                fracture_cluster_labels = set(containing[0])
            else:
                fracture_cluster_labels = set(max(comps, key=len))
    fracture_center = _cluster_center(fracture_cluster_labels, all_centroids)
    print('  Fracture cluster: %d deleted elements at anchor frame, center=(%.3f, %.3f, %.3f)'
          % (len(fracture_cluster_labels), fracture_center[0], fracture_center[1], fracture_center[2]))

    # Report radial position of critical element
    if dome_labels is not None:
        for name in _INST_NAMES:
            if name not in odb.rootAssembly.instances.keys():
                continue
            inst_obj = odb.rootAssembly.instances[name]
            node_xy  = {n.label: (n.coordinates[inplane_axes[0]],
                                  n.coordinates[inplane_axes[1]])
                        for n in inst_obj.nodes}
            for elem in inst_obj.elements:
                if elem.label == crit_label:
                    xs = [node_xy[n][0] for n in elem.connectivity if n in node_xy]
                    ys = [node_xy[n][1] for n in elem.connectivity if n in node_xy]
                    if xs:
                        cx = sum(xs) / len(xs)
                        cy = sum(ys) / len(ys)
                        crit_R = math.sqrt(cx*cx + cy*cy)
                        print('  Critical element : %d  (IP %d)  EQPS = %.4f  R = %.2f mm'
                              % (crit_label, crit_ip, max_eqps, crit_R))
                    break
            break

    # ── 4. Build the selected region for the primary path.
    # The preferred path follows the DIC/Volk-Hora idea: define the rupture
    # region from the connected deleted crack component, go back before deletion,
    # select the high-thinning-rate seed/zone, and average that fixed region
    # through time.  The old nearest-neighbour cluster remains as a fallback.
    vh_zone_radius = max(0.0, _env_float(
        'POSTPROC_VH_FRACTURE_RADIUS_MM',
        VH_FRACTURE_ZONE_RADIUS_DEFAULT,
    ))
    if fracture_type == 'outside_dome':
        print('  WARNING: outside_dome endpoint; writing diagnostic cluster only.')
        _cluster_selected, _vh_meta = _select_outside_dome_diagnostic_region(
            odb, frames, failure_frame_idx, dome_labels, crit_label,
        )
    else:
        _cluster_selected, _vh_meta = _select_vh_region_elements(
            odb, frames, failure_frame_idx, dome_labels,
        )
    if not _cluster_selected:
        print('  Primary path  : crack-line band empty; '
              'falling back to the single critical element')
    elif (_vh_meta or {}).get('warning') == 'outside_dome':
        print('  Primary path  : %d diagnostic elements (%s) [outside_dome — excluded from FLC]'
              % (len(_cluster_selected),
                 _vh_meta.get('selection_method', 'outside_dome_diagnostic')))
    else:
        print('  Primary path  : %d selected elements (%s)'
              % (len(_cluster_selected),
                 _vh_meta.get('selection_method', 'fracture_neighborhood_fallback')))
    cluster_eps1 = [rec['eps1'] for _, rec in _cluster_selected if rec.get('eps1') is not None]
    cluster_eps2 = [rec['eps2'] for _, rec in _cluster_selected if rec.get('eps2') is not None]

    # ── 5. Extract CSV quantities for the selected-region mean path ───────────
    def _is_crit_value(val):
        if val.elementLabel != crit_label:
            return False
        return crit_ip is None or val.integrationPoint == crit_ip

    selected_keys = set((lbl, rec['ip']) for lbl, rec in _cluster_selected)
    selection_method = (
        _vh_meta.get('selection_method') or
        (sorted(set(rec.get('selection_method', '') for _, rec in _cluster_selected
                    if rec.get('selection_method'))) or ['critical_element'])[0]
    )
    path_source = _vh_meta.get('path_source') if _vh_meta else (
        'fracture_neighborhood_selected_region' if selected_keys else 'critical_element'
    )
    selected_n = len(selected_keys)

    records     = []
    times_list  = []
    d_dome_list = []
    strain_sum_by_frame = []

    sdv6_in_odb = True
    sdv4_in_odb = True

    for fi in range(path_end_frame_idx):
        frame = frames[fi]
        t     = frame.frameValue
        eps1 = None
        eps2 = None
        eps1_vals = []
        eps2_vals = []
        eqps_vals = []
        triax_vals = []
        d_vals = []
        frame_strain_sum = {}
        d_dome = 0.0

        for val in frame.fieldOutputs['LE'].values:
            key = (val.elementLabel, val.integrationPoint)
            use_value = (key in selected_keys) if selected_keys else _is_crit_value(val)
            if use_value:
                e1, e2 = _principal_strains_from_LE(val)
                if e1 is not None:
                    eps1_vals.append(e1)
                    eps2_vals.append(e2)
                    frame_strain_sum[key] = e1 + e2

        if 'SDV1' in frame.fieldOutputs.keys():
            for val in frame.fieldOutputs['SDV1'].values:
                key = (val.elementLabel, val.integrationPoint)
                use_value = (key in selected_keys) if selected_keys else _is_crit_value(val)
                if use_value:
                    eqps_vals.append(val.data)

        if sdv4_in_odb and 'SDV4' in frame.fieldOutputs.keys():
            for val in frame.fieldOutputs['SDV4'].values:
                key = (val.elementLabel, val.integrationPoint)
                use_value = (key in selected_keys) if selected_keys else _is_crit_value(val)
                if use_value:
                    triax_vals.append(val.data)
        elif sdv4_in_odb and fi == 0:
            sdv4_in_odb = False
            print('  WARNING: SDV4 (TRIAX) not found in ODB — TRIAX column set to zero.')

        if sdv6_in_odb and 'SDV6' in frame.fieldOutputs.keys():
            for val in frame.fieldOutputs['SDV6'].values:
                key = (val.elementLabel, val.integrationPoint)
                use_value = (key in selected_keys) if selected_keys else _is_crit_value(val)
                if use_value:
                    d_vals.append(val.data)
                in_dome = (dome_labels is None) or (val.elementLabel in dome_labels)
                if in_dome and val.data > d_dome:
                    d_dome = val.data
        elif sdv6_in_odb and fi == 0:
            sdv6_in_odb = False
            print('  WARNING: SDV6 not found in ODB — D columns set to zero.')

        if eps1_vals:
            eps1 = sum(eps1_vals) / float(len(eps1_vals))
            eps2 = sum(eps2_vals) / float(len(eps2_vals))
            eqps = sum(eqps_vals) / float(len(eqps_vals)) if eqps_vals else 0.0
            d_sel = sum(d_vals) / float(len(d_vals)) if d_vals else 0.0
            triax = sum(triax_vals) / float(len(triax_vals)) if triax_vals else 0.0
            records.append([t, eps1, eps2,
                            eqps, d_sel,
                            fracture_type, d_dome,
                            triax])
            times_list.append(t)
            d_dome_list.append(d_dome)
            strain_sum_by_frame.append(frame_strain_sum)

    if records:
        rates = _mean_rate_history_from_element_histories(times_list, strain_sum_by_frame)
        for i, rate in enumerate(rates):
            records[i].extend([
                rate,
                path_source,
                selected_n if selected_n else 1,
                selection_method,
                _vh_meta.get('alpha', ''),
                _vh_meta.get('seed_count', ''),
                _vh_meta.get('zone_area', ''),
                _vh_meta.get('eval_time', ''),
                _vh_meta.get('fracture_zone_radius_mm', vh_zone_radius),
            ])
    else:
        rates = []

    print('  Primary path  : %s (%d points)'
          % (path_source, len(records)))

    # ── 5. Evaluate fracture, V&H, and damage-inflection limits.
    eps1_hist = [r[1] for r in records]
    eps2_hist = [r[2] for r in records]

    # Convenience: limit strains at each frame of interest
    def _lim(idx):
        """Return (eps1, eps2, eqps, d, t) for records[idx], or None."""
        if idx is None or idx >= len(records):
            return None
        r = records[idx]
        return r[1], r[2], r[3], r[4], r[0]

    # Always extract strains at the fracture frame regardless of fracture_type.
    # For 'dome': these are the valid FLC limit strains.
    # For 'outside_dome'/'none': stored with the fracture_type label so the app can flag them.
    lim_frac = _lim(len(records) - 1)
    fit_end_time = frames[path_end_frame_idx].frameValue if path_end_frame_idx < len(frames) else None
    vh_fit = _volk_hora_fit_indices(times_list, rates, fit_end_time=fit_end_time)
    lim_vh = _lim(vh_fit['kstable']) if vh_fit is not None else None
    sdv6_idx = (
        _inflection_index(times_list, d_dome_list)
        if sdv6_in_odb and any(d > 0.0 for d in d_dome_list) else None
    )
    lim_sdv6 = _lim(sdv6_idx)

    # Print summary
    print('')
    print('  %-14s  %7s  %7s  %7s  %7s' % ('Method', 't (s)', 'eps1', 'eps2', 'D'))
    print('  ' + '-' * 54)
    if lim_frac:
        flag = '' if fracture_type == 'dome' else '  [%s — excluded from FLC]' % fracture_type
        print('  %-14s  %7.3f  %7.4f  %7.4f  %7.4f%s' % (
              'Fracture', lim_frac[4], lim_frac[0], lim_frac[1], lim_frac[3], flag))
    else:
        print('  %-14s  %s' % ('Fracture', 'N/A (no records)'))
    if lim_vh:
        print('  %-14s  %7.3f  %7.4f  %7.4f  %7.4f' % (
              'Volk-Hora', lim_vh[4], lim_vh[0], lim_vh[1], lim_vh[3]))
    if lim_sdv6:
        print('  %-14s  %7.3f  %7.4f  %7.4f  %7.4f' % (
              'SDV6/damage', lim_sdv6[4], lim_sdv6[0], lim_sdv6[1], lim_sdv6[3]))
    print('')

    out_dir = os.path.dirname(out_csv)

    # ── 6. Write strain_path.csv ──────────────────────────────
    with open(out_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow([
            'time_s', 'eps1_major', 'eps2_minor', 'EQPS', 'D',
            'fracture_type', 'd_dome_max', 'TRIAX',
            'thinning_rate', 'path_source', 'selected_n', 'selection_method',
            'vh_alpha', 'vh_seed_count', 'vh_zone_area', 'vh_eval_time',
            'vh_fracture_zone_radius_mm',
        ])
        writer.writerows(records)

    print('  Written %d points -> %s' % (len(records), out_csv))

    # ── 7. Write energy_data.csv and punch_fd.csv ────────────
    # punch_fd is written first so we can interpolate U3_mm at fracture time.
    e_times, ke_vals, ie_vals = _write_energy_csv(odb, out_dir)
    p_times, u3_vals, rf3_vals = _write_punch_fd_csv(odb, out_dir)
    qs_limit = _env_float('POSTPROC_QS_RATIO_LIMIT', 0.10)
    qs_max = None
    for ke, ie in zip(ke_vals or [], ie_vals or []):
        if ie is None or abs(ie) <= 1e-20:
            continue
        ratio = abs(ke) / abs(ie)
        if qs_max is None or ratio > qs_max:
            qs_max = ratio
    if qs_max is not None and qs_max > qs_limit:
        print('  WARNING: max ALLKE/ALLIE = %.3f exceeds quasi-static limit %.3f.'
              % (qs_max, qs_limit))

    # Interpolate punch displacement at the fracture instant
    def _interp_u3(t_frac, times, u3s):
        if not times or t_frac is None:
            return None
        if t_frac <= times[0]:
            return u3s[0]
        if t_frac >= times[-1]:
            return u3s[-1]
        for k in range(len(times) - 1):
            if times[k] <= t_frac <= times[k + 1]:
                dt = times[k + 1] - times[k]
                if dt < 1e-12:
                    return u3s[k]
                alpha = (t_frac - times[k]) / dt
                return u3s[k] + alpha * (u3s[k + 1] - u3s[k])
        return None

    u3_frac = _interp_u3(lim_frac[4] if lim_frac else None, list(p_times or []), list(u3_vals or []))
    u3_vh = _interp_u3(lim_vh[4] if lim_vh else None, list(p_times or []), list(u3_vals or []))
    u3_sdv6 = _interp_u3(lim_sdv6[4] if lim_sdv6 else None, list(p_times or []), list(u3_vals or []))

    # ── 8. Write forming_limits.csv ───────────────────────────
    limits_csv = os.path.join(out_dir, 'forming_limits.csv')
    with open(limits_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['method', 'eps1_major', 'eps2_minor', 'EQPS', 'D',
                         'time_s', 'U3_mm', 'fracture_type',
                         'path_source', 'critical_element', 'critical_ip',
                         'cluster_n', 'cluster_eps1_min', 'cluster_eps1_max',
                         'cluster_eps2_min', 'cluster_eps2_max',
                         'selection_method', 'vh_alpha', 'vh_seed_count',
                         'vh_zone_n', 'vh_zone_area', 'vh_eval_time',
                         'vh_fracture_zone_radius_mm',
                         'vh_last_stable_time', 'vh_first_unstable_time'])
        if lim_frac:
            writer.writerow(['fracture',
                             lim_frac[0], lim_frac[1], lim_frac[2], lim_frac[3],
                             lim_frac[4],
                             '' if u3_frac is None else round(u3_frac, 4),
                             fracture_type,
                             path_source,
                             crit_label,
                             '' if crit_ip is None else crit_ip,
                             len(_cluster_selected),
                             '' if not cluster_eps1 else min(cluster_eps1),
                             '' if not cluster_eps1 else max(cluster_eps1),
                             '' if not cluster_eps2 else min(cluster_eps2),
                             '' if not cluster_eps2 else max(cluster_eps2),
                             selection_method,
                             _vh_meta.get('alpha', ''),
                             _vh_meta.get('seed_count', ''),
                             _vh_meta.get('zone_count', ''),
                             _vh_meta.get('zone_area', ''),
                             _vh_meta.get('eval_time', ''),
                             _vh_meta.get('fracture_zone_radius_mm', vh_zone_radius),
                             '' if vh_fit is None else times_list[vh_fit['kstable']],
                             '' if vh_fit is None else times_list[vh_fit['kcrit']]])
        if lim_vh:
            writer.writerow(['volk_hora',
                             lim_vh[0], lim_vh[1], lim_vh[2], lim_vh[3],
                             lim_vh[4],
                             '' if u3_vh is None else round(u3_vh, 4),
                             fracture_type,
                             path_source,
                             crit_label,
                             '' if crit_ip is None else crit_ip,
                             len(_cluster_selected),
                             '' if not cluster_eps1 else min(cluster_eps1),
                             '' if not cluster_eps1 else max(cluster_eps1),
                             '' if not cluster_eps2 else min(cluster_eps2),
                             '' if not cluster_eps2 else max(cluster_eps2),
                             selection_method,
                             _vh_meta.get('alpha', ''),
                             _vh_meta.get('seed_count', ''),
                             _vh_meta.get('zone_count', ''),
                             _vh_meta.get('zone_area', ''),
                             _vh_meta.get('eval_time', ''),
                             _vh_meta.get('fracture_zone_radius_mm', vh_zone_radius),
                             times_list[vh_fit['kstable']],
                             times_list[vh_fit['kcrit']]])
        if lim_sdv6:
            writer.writerow(['sdv6',
                             lim_sdv6[0], lim_sdv6[1], lim_sdv6[2], lim_sdv6[3],
                             lim_sdv6[4],
                             '' if u3_sdv6 is None else round(u3_sdv6, 4),
                             fracture_type,
                             path_source,
                             crit_label,
                             '' if crit_ip is None else crit_ip,
                             len(_cluster_selected),
                             '' if not cluster_eps1 else min(cluster_eps1),
                             '' if not cluster_eps1 else max(cluster_eps1),
                             '' if not cluster_eps2 else min(cluster_eps2),
                             '' if not cluster_eps2 else max(cluster_eps2),
                             'sdv6_dome_max_inflection',
                             '', '', '', '', '',
                             vh_zone_radius, '', ''])
    print('  Forming limits -> %s' % limits_csv)

    # ── 9. Write top-surface strain-path cluster ─────────────
    _write_strain_cluster_csv(odb, frames, path_end_frame_idx, dome_labels, out_dir,
                              center_label=crit_label, search_radius=vh_zone_radius,
                              fracture_cluster_labels=fracture_cluster_labels,
                              fracture_center=fracture_center,
                              selected_override=_cluster_selected,
                              candidate_override=_vh_meta.get('candidates'))

    # ── 10. Write specimen outline for cluster-location diagnostics ─────────
    _write_specimen_outline_csv(odb, out_dir)

    # ── 11. Optional whole-dome field for legacy/independent V&H diagnostics.
    # The selected-region CSVs above are the default path for Streamlit. Keeping
    # this off avoids multi-million-row files for dense solid meshes.
    if dome_labels is not None and _env_int('POSTPROC_WRITE_DOME_HISTORY', 0):
        _write_top_surface_history_csv(
            odb, frames, path_end_frame_idx, dome_labels, out_dir,
            'strain_dome.csv', 'top_surface_dome_all_candidates',
        )
    else:
        print('  strain_dome.csv: skipped (set POSTPROC_WRITE_DOME_HISTORY=1 for full dome history)')

    odb.close()
    print('=' * 60)
    return {
        'times':         times_list,
        'eps1':          eps1_hist,
        'eps2':          eps2_hist,
        'eqps':          [r[3] for r in records],
        'd_crit':        [r[4] for r in records],
        'd_dome_max':    d_dome_list,
        'TRIAX':         [r[7] for r in records],
        'fracture_type': fracture_type,
        'energy_times':  e_times,
        'ALLKE':         ke_vals,
        'ALLIE':         ie_vals,
        'punch_times':   p_times,
        'U3_mm':         u3_vals,
        'RF3_N':         rf3_vals,
    }




#==============================================================================
#  SHARED UTILITIES  (low-level mesh/strain/geometry helpers used across sections)
#==============================================================================

def _inplane_axes_from_meta(meta):
    top_axis = int(meta.get('top_axis', 2))
    return tuple(ax for ax in (0, 1, 2) if ax != top_axis)


def _positive_min_step(values):
    steps = [abs(values[i + 1] - values[i])
             for i in range(len(values) - 1)
             if abs(values[i + 1] - values[i]) > 1e-9]
    return min(steps) if steps else None


def _smooth3(values):
    """3-point centred moving average; endpoints are left unchanged."""
    n = len(values)
    if n < 3:
        return list(values)
    out = list(values)
    for i in range(1, n - 1):
        out[i] = (values[i - 1] + values[i] + values[i + 1]) / 3.0
    return out


def _inflection_index(times, values, start_frac=0.1):
    """
    Return argmax d2(values)/dt2 after the signal becomes nontrivial.
    Used for lightweight scalar-history criteria such as dome-max SDV6.
    """
    n = len(values)
    if n < 5 or len(times) != n:
        return None

    v = _smooth3(values)
    dv = [0.0] * n
    for i in range(1, n - 1):
        dt = times[i + 1] - times[i - 1]
        dv[i] = (v[i + 1] - v[i - 1]) / dt if dt > 1e-12 else 0.0

    d2v = [0.0] * n
    for i in range(1, n - 1):
        dt = times[i + 1] - times[i - 1]
        d2v[i] = (dv[i + 1] - dv[i - 1]) / dt if dt > 1e-12 else 0.0

    v_max = max(abs(x) for x in values) if values else 1.0
    threshold = start_frac * v_max
    start_idx = 1
    for i, val in enumerate(values):
        if abs(val) >= threshold:
            start_idx = max(1, i)
            break

    best_idx, best_val = None, -1e30
    for i in range(start_idx, n - 1):
        if d2v[i] > best_val:
            best_val = d2v[i]
            best_idx = i
    return best_idx


def _principal_strains_from_LE(val):
    """
    Compute the two largest principal logarithmic strains from a LE field value.
      val.data = (LE11, LE22, LE33, LE12, LE13, LE23)  for 3-D solid
    Returns (eps1_major, eps2_minor).
    """
    d = val.data
    e11 = d[0]; e22 = d[1]; e33 = d[2]
    e12 = d[3] if len(d) > 3 else 0.0
    e13 = d[4] if len(d) > 4 else 0.0
    e23 = d[5] if len(d) > 5 else 0.0

    m = (e11 + e22 + e33) / 3.0
    K = [[e11-m, e12,    e13   ],
         [e12,   e22-m,  e23   ],
         [e13,   e23,    e33-m ]]

    q = (K[0][0]**2 + K[1][1]**2 + K[2][2]**2 +
         2*(K[0][1]**2 + K[0][2]**2 + K[1][2]**2)) / 6.0
    q = math.sqrt(max(q, 0.0))

    if q < 1e-14:
        return m, m

    det = (K[0][0]*(K[1][1]*K[2][2] - K[1][2]*K[2][1])
         - K[0][1]*(K[1][0]*K[2][2] - K[1][2]*K[2][0])
         + K[0][2]*(K[1][0]*K[2][1] - K[1][1]*K[2][0]))

    phi = math.acos(max(-1.0, min(1.0, det / (2.0 * q**3)))) / 3.0

    eig1 = m + 2*q*math.cos(phi)
    eig2 = m + 2*q*math.cos(phi + 2*math.pi/3.0)
    eig3 = m + 2*q*math.cos(phi + 4*math.pi/3.0)

    eigs = sorted([eig1, eig2, eig3], reverse=True)
    return eigs[0], eigs[1]


# ── ELOUT element history extraction ─────────────────────────────────────────

def _principal_strains_from_components(e11, e22, e33, e12, e13=0.0, e23=0.0):
    """Same eigenvalue calculation as _principal_strains_from_LE but from raw floats."""
    m = (e11 + e22 + e33) / 3.0
    K = [[e11-m, e12,   e13  ],
         [e12,   e22-m, e23  ],
         [e13,   e23,   e33-m]]
    q = (K[0][0]**2 + K[1][1]**2 + K[2][2]**2
         + 2.0*(K[0][1]**2 + K[0][2]**2 + K[1][2]**2)) / 6.0
    q = math.sqrt(max(q, 0.0))
    if q < 1e-14:
        return m, m
    det = (K[0][0]*(K[1][1]*K[2][2] - K[1][2]*K[2][1])
          - K[0][1]*(K[1][0]*K[2][2] - K[1][2]*K[2][0])
          + K[0][2]*(K[1][0]*K[2][1] - K[1][1]*K[2][0]))
    phi  = math.acos(max(-1.0, min(1.0, det / (2.0 * q**3)))) / 3.0
    eigs = sorted([m + 2.0*q*math.cos(phi + k*2.0*math.pi/3.0)
                   for k in range(3)], reverse=True)
    return eigs[0], eigs[1]


def _element_centroid_maps(odb):
    """
    Return centroid maps for the specimen instance.
    """
    inst = None
    for name in _INST_NAMES:
        if name in odb.rootAssembly.instances.keys():
            inst = odb.rootAssembly.instances[name]
            break
    if inst is None:
        return None, {}, {}, {}

    node_coords = {n.label: n.coordinates for n in inst.nodes}
    centroids = {}
    for elem in inst.elements:
        coords = [node_coords[n] for n in elem.connectivity if n in node_coords]
        if not coords:
            continue
        cx = sum(c[0] for c in coords) / len(coords)
        cy = sum(c[1] for c in coords) / len(coords)
        cz = sum(c[2] for c in coords) / len(coords)
        centroids[elem.label] = (cx, cy, cz)

    if not centroids:
        return inst.name, {}, set(), {'top_axis': 2, 'top_coord': 0.0,
                                      'top_tol': 1e-6, 'z_top': 0.0}

    axis_names = {'x': 0, 'y': 1, 'z': 2}
    axis_env = _env_str('POSTPROC_THICKNESS_AXIS', 'auto').strip().lower()
    if axis_env in axis_names:
        top_axis = axis_names[axis_env]
    else:
        ranges = []
        for ax in range(3):
            vals = [c[ax] for c in centroids.values()]
            ranges.append((max(vals) - min(vals), ax))
        # The sheet thickness is the smallest geometric extent. This keeps the
        # surface filter valid for imported meshes whose thickness axis is not Z.
        top_axis = min(ranges, key=lambda item: item[0])[1]

    top_coord = max(c[top_axis] for c in centroids.values()) if centroids else 0.0
    top_faces = _top_surface_faces_from_connectivity(inst, node_coords, top_axis)
    top_labels = set(lbl for lbl, _ in top_faces)
    top_tol = 1e-6
    if not top_labels:
        axis_values = sorted(set(round(c[top_axis], 6) for c in centroids.values()))
        if len(axis_values) > 1:
            d_axis_min = _positive_min_step(axis_values)
            top_tol = max(1e-6, 0.25 * d_axis_min) if d_axis_min else 1e-6
        else:
            top_tol = 1e-6
        top_labels = set(lbl for lbl, c in centroids.items()
                         if abs(c[top_axis] - top_coord) <= top_tol)
    return inst.name, centroids, top_labels, {
        'top_axis': top_axis,
        'top_coord': top_coord,
        'top_tol': top_tol,
        # Backward-compatible names for code that only needs a top coordinate.
        'z_top': top_coord if top_axis == 2 else None,
    }


def _build_dome_set(odb, r_dome):
    """
    Build dome-zone element set from undeformed element centroids.

    Returns:
        dome_labels      set of element labels with centroid r < r_dome
        inst_name        name of the specimen instance
        dome_radii       {label → centroid radius (mm)}
    """
    inst = None
    for name in _INST_NAMES:
        if name in odb.rootAssembly.instances.keys():
            inst = odb.rootAssembly.instances[name]
            break
    if inst is None:
        print('  WARNING: specimen instance not found — no dome filtering.')
        return None, None, {}

    _, centroids, _, meta = _element_centroid_maps(odb)
    inplane_axes = _inplane_axes_from_meta(meta)

    node_coords = {n.label: n.coordinates for n in inst.nodes}

    # Dome-zone elements (centroid within r_dome)
    r_sq        = r_dome * r_dome
    dome_labels = set()
    dome_radii  = {}
    for elem in inst.elements:
        if elem.label in centroids:
            c = centroids[elem.label]
            cx = c[inplane_axes[0]]
            cy = c[inplane_axes[1]]
        else:
            coords = [node_coords[n] for n in elem.connectivity if n in node_coords]
            if not coords:
                continue
            cx = sum(c[inplane_axes[0]] for c in coords) / len(coords)
            cy = sum(c[inplane_axes[1]] for c in coords) / len(coords)
        r_sq_elem = cx * cx + cy * cy
        if r_sq_elem < r_sq:
            dome_labels.add(elem.label)
            dome_radii[elem.label] = math.sqrt(r_sq_elem)

    print('  Dome zone   : R < %.1f mm  (%d elements)' % (r_dome, len(dome_labels)))
    return dome_labels, inst.name, dome_radii


def _top_surface_faces_from_connectivity(inst, node_coords, top_axis):
    node_axis_values = sorted(set(round(c[top_axis], 6) for c in node_coords.values()))
    if len(node_axis_values) > 1:
        d_axis_min = _positive_min_step(node_axis_values)
        face_tol = max(1e-6, 0.25 * d_axis_min) if d_axis_min else 1e-6
    else:
        face_tol = 1e-6

    face_counts = {}
    top_faces = []
    for elem in inst.elements:
        conn = [n for n in elem.connectivity if n in node_coords]
        if len(conn) < 4:
            continue
        vals = [node_coords[n][top_axis] for n in conn]
        elem_top = max(vals)
        elem_bot = min(vals)
        top_nodes = [n for n in conn if abs(node_coords[n][top_axis] - elem_top) <= face_tol]
        bot_nodes = [n for n in conn if abs(node_coords[n][top_axis] - elem_bot) <= face_tol]
        for face_nodes in (top_nodes, bot_nodes):
            if len(face_nodes) >= 3:
                key = tuple(sorted(face_nodes))
                face_counts[key] = face_counts.get(key, 0) + 1
        if len(top_nodes) >= 3:
            top_faces.append((elem.label, top_nodes))

    external = []
    for lbl, face_nodes in top_faces:
        if face_counts.get(tuple(sorted(face_nodes)), 0) == 1:
            external.append((lbl, face_nodes))
    return external


def _element_xy_polygon_from_element(elem_obj, node_coords, normal_axis=2):
    """
    Return an ordered XY footprint polygon for an element object.
    Uses the element's highest-z face, so bottom-layer deleted elements still
    get a top-view cell footprint.
    """
    coords = [(n, node_coords[n]) for n in elem_obj.connectivity if n in node_coords]
    if len(coords) < 3:
        return []
    normal_axis = int(normal_axis)
    inplane_axes = tuple(ax for ax in (0, 1, 2) if ax != normal_axis)
    vmax = max(c[normal_axis] for _, c in coords)
    vals = sorted(set(round(c[normal_axis], 6) for _, c in coords))
    if len(vals) > 1:
        dz_min = _positive_min_step(vals)
        ztol = max(1e-6, 0.25 * dz_min) if dz_min else 1e-6
    else:
        ztol = 1e-6
    face = [(n, c) for n, c in coords if abs(c[normal_axis] - vmax) <= ztol]
    if len(face) < 3:
        return []

    cx = sum(c[inplane_axes[0]] for _, c in face) / float(len(face))
    cy = sum(c[inplane_axes[1]] for _, c in face) / float(len(face))
    ordered = sorted(
        face,
        key=lambda item: math.atan2(item[1][inplane_axes[1]] - cy,
                                   item[1][inplane_axes[0]] - cx),
    )
    return [(c[0], c[1], c[2]) for _, c in ordered]


def _element_xy_polygon(inst, node_coords, elem_label, normal_axis=2):
    elem_obj = None
    for elem in inst.elements:
        if elem.label == elem_label:
            elem_obj = elem
            break
    if elem_obj is None:
        return []
    return _element_xy_polygon_from_element(elem_obj, node_coords, normal_axis=normal_axis)


def _polygon_area_xy(poly, axes=(0, 1)):
    if len(poly) < 3:
        return 0.0
    area = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i][axes[0]], poly[i][axes[1]]
        x2, y2 = poly[(i + 1) % len(poly)][axes[0]], poly[(i + 1) % len(poly)][axes[1]]
        area += x1 * y2 - x2 * y1
    return abs(area) * 0.5


def _top_face_area_map(odb, labels):
    inst_name, centroids, top_labels, meta = _element_centroid_maps(odb)
    if not inst_name:
        return {}
    inst = odb.rootAssembly.instances[inst_name]
    node_coords = {n.label: n.coordinates for n in inst.nodes}
    label_set = set(labels)
    top_axis = int(meta.get('top_axis', 2))
    inplane_axes = _inplane_axes_from_meta(meta)
    areas = {}
    for elem in inst.elements:
        if elem.label not in label_set:
            continue
        poly = _element_xy_polygon_from_element(elem, node_coords, normal_axis=top_axis)
        areas[elem.label] = _polygon_area_xy(poly, axes=inplane_axes)
    return areas


def _median_xy_spacing(labels, centroids, axes=(0, 1)):
    pts = []
    for lbl in labels:
        if lbl in centroids:
            c = centroids[lbl]
            pts.append((c[axes[0]], c[axes[1]]))
    max_pts = _env_int('POSTPROC_SPACING_SAMPLE_MAX', 1500)
    if max_pts > 0 and len(pts) > max_pts:
        stride = int(math.ceil(float(len(pts)) / float(max_pts)))
        pts = pts[::stride]
    nearest = []
    for i, p0 in enumerate(pts):
        best = None
        for j, p1 in enumerate(pts):
            if i == j:
                continue
            d = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            if d <= 1e-9:
                continue
            if best is None or d < best:
                best = d
        if best is not None:
            nearest.append(best)
    if not nearest:
        return 2.0
    nearest = sorted(nearest)
    return nearest[len(nearest) // 2]


def _connected_xy_components(labels, centroids, spacing_labels=None, axes=(0, 1)):
    label_set = set(lbl for lbl in labels if lbl in centroids)
    if not label_set:
        return []
    spacing = _median_xy_spacing(spacing_labels if spacing_labels is not None else label_set,
                                 centroids, axes=axes)
    conn_radius = max(1e-6, 1.6 * spacing)
    cell_size = conn_radius
    grid = {}
    for lbl in label_set:
        x, y = centroids[lbl][axes[0]], centroids[lbl][axes[1]]
        key = (int(math.floor(x / cell_size)), int(math.floor(y / cell_size)))
        grid.setdefault(key, set()).add(lbl)

    def _remove(lbl):
        x, y = centroids[lbl][axes[0]], centroids[lbl][axes[1]]
        key = (int(math.floor(x / cell_size)), int(math.floor(y / cell_size)))
        bucket = grid.get(key)
        if bucket is not None:
            bucket.discard(lbl)

    components = []
    while label_set:
        seed = label_set.pop()
        _remove(seed)
        comp = [seed]
        stack = [seed]
        while stack:
            lbl = stack.pop()
            x0, y0 = centroids[lbl][axes[0]], centroids[lbl][axes[1]]
            neighbors = []
            ix = int(math.floor(x0 / cell_size))
            iy = int(math.floor(y0 / cell_size))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for other in list(grid.get((ix + dx, iy + dy), ())):
                        x1, y1 = centroids[other][axes[0]], centroids[other][axes[1]]
                        if math.hypot(x1 - x0, y1 - y0) <= conn_radius:
                            neighbors.append(other)
            for other in neighbors:
                if other not in label_set:
                    continue
                label_set.remove(other)
                _remove(other)
                stack.append(other)
                comp.append(other)
        components.append(comp)
    return components


def _cluster_center(labels, centroids):
    pts = [centroids[lbl] for lbl in labels if lbl in centroids]
    if not pts:
        return 0.0, 0.0, 0.0
    n = float(len(pts))
    return (
        sum(p[0] for p in pts) / n,
        sum(p[1] for p in pts) / n,
        sum(p[2] for p in pts) / n,
    )


#==============================================================================
#  MAIN
#==============================================================================

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: abaqus python postproc.py -- <path/to/job.odb>')
        sys.exit(1)
    odb_path = sys.argv[-1]
    out_dir = os.path.dirname(os.path.abspath(odb_path))
    field_data = extract_strain_path(odb_path)
    elout_data = extract_elout(odb_path)
    write_elout_csv(out_dir, elout_data)
    write_global_csv(out_dir, field_data)
