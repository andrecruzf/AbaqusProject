# -*- coding: utf-8 -*-
"""
postproc.py  —  Extract FLC strain path from a Nakazima/Marciniak ODB.

Standalone:
    adb>

From pipeline (run_cluster.sh):
    abaqus python postproc.py -- <OUTPUT_DIR>/<JOB_NAME>.odb

Output:
    <odb_dir>/strain_path.csv      columns: time_s, eps1_major, eps2_minor, EQPS, D, fracture_type
    <odb_dir>/forming_limits.csv   one row for the fracture limit, when fracture occurs in the dome zone
    <odb_dir>/energy_data.csv      ALLKE / ALLIE history
    <odb_dir>/punch_fd.csv         punch force-displacement history
    <odb_dir>/global.csv           dashboard-friendly merged global history
    <odb_dir>/elout.csv            ELOUT element history, when present

Algorithm:
    1. Build the dome zone: all elements whose undeformed centroid lies within
       R_DOME mm of the punch axis (X=Y=0).  R_DOME = PUNCH_RADIUS / 2 by
       default — physically ties the observation zone to the tool geometry and
       is consistent across all specimen widths.  The sample does not always
       crack at the centreline, so the zone must be wide enough to capture
       off-centre failure bands (e.g. narrow strip specimens).
    2. Find the first frame where any dome-zone element has STATUS < 0.5
       (fracture frame).
    3. Critical element: the dome-zone element with STATUS < 0.5 at the fracture frame.
       Tiebreaker (multiple simultaneous fractures): highest EQPS at frame f-1.
       Fallback (STATUS not in field output): max EQPS at frame f-1.
    4. Extract the full (eps1_major, eps2_minor, EQPS, D) history of that element
       up to fracture. Also collect dome-zone max SDV6 per frame.
       Principal strains are computed from the LE tensor (eigenvalues).
    5. Write CSV files only. Necking criteria, including Volk-Hora, are intentionally
       disabled in this baseline and should be rebuilt in a separate, clean module.

Environment variables:
    PUNCH_RADIUS : punch hemisphere radius in mm (default 50).
"""
import sys
import os
import csv
import math

# ── Dome zone radius ──────────────────────────────────────────────────────────
R_DOME_DEFAULT = 25.0   # mm — ISO 12004-2: 15% of punch diameter (Ø100 mm punch)
MIN_FRACTURE_CLUSTER_CELLS = 20

# Instance names to try for the blank in the ODB assembly
_INST_NAMES = ('SPECIMEN-1', 'Specimen-1', 'BLANK-1', 'Blank-1')


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

    # Build node position maps once
    node_coords = {n.label: n.coordinates for n in inst.nodes}
    node_xy     = {lbl: (c[0], c[1]) for lbl, c in node_coords.items()}

    # Dome-zone elements (centroid within r_dome)
    r_sq        = r_dome * r_dome
    dome_labels = set()
    dome_radii  = {}
    for elem in inst.elements:
        xs = [node_xy[n][0] for n in elem.connectivity if n in node_xy]
        ys = [node_xy[n][1] for n in elem.connectivity if n in node_xy]
        if not xs:
            continue
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        r_sq_elem = cx * cx + cy * cy
        if r_sq_elem < r_sq:
            dome_labels.add(elem.label)
            dome_radii[elem.label] = math.sqrt(r_sq_elem)

    print('  Dome zone   : R < %.1f mm  (%d elements)' % (r_dome, len(dome_labels)))
    return dome_labels, inst.name, dome_radii


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

    z_values = sorted(set(round(c[2], 6) for c in centroids.values()))
    if len(z_values) > 1:
        dz_min = min(abs(z_values[i + 1] - z_values[i]) for i in range(len(z_values) - 1))
        top_tol = max(1e-6, 0.25 * dz_min)
    else:
        top_tol = 1e-6
    z_top = max(c[2] for c in centroids.values()) if centroids else 0.0
    top_labels = set(lbl for lbl, c in centroids.items() if abs(c[2] - z_top) <= top_tol)
    return inst.name, centroids, top_labels, {'z_top': z_top, 'top_tol': top_tol}


def _write_specimen_outline_csv(odb, out_dir):
    """
    Export the actual top-view FE specimen outline from top-layer boundary edges.
    """
    inst_name, centroids, top_labels, meta = _element_centroid_maps(odb)
    if not inst_name or not top_labels:
        print('  Specimen outline: skipped (no top-surface elements)')
        return None

    inst = odb.rootAssembly.instances[inst_name]
    node_coords = {n.label: n.coordinates for n in inst.nodes}
    edge_counts = {}
    node_z_values = sorted(set(round(c[2], 6) for c in node_coords.values()))
    z_node_top = max(c[2] for c in node_coords.values())
    if len(node_z_values) > 1:
        dz_node_min = min(abs(node_z_values[i + 1] - node_z_values[i])
                          for i in range(len(node_z_values) - 1)
                          if abs(node_z_values[i + 1] - node_z_values[i]) > 1e-9)
        node_top_tol = max(1e-6, 0.25 * dz_node_min)
    else:
        node_top_tol = 1e-6

    for elem in inst.elements:
        if elem.label not in top_labels:
            continue
        conn = list(elem.connectivity)
        top_nodes = [
            n for n in conn
            if n in node_coords and abs(node_coords[n][2] - z_node_top) <= node_top_tol
        ]
        if len(top_nodes) < 3:
            continue

        local_edges = set()
        n_top = len(top_nodes)
        if n_top == 4:
            cx = sum(node_coords[n][0] for n in top_nodes) / 4.0
            cy = sum(node_coords[n][1] for n in top_nodes) / 4.0
            ordered = sorted(top_nodes, key=lambda n: math.atan2(node_coords[n][1] - cy,
                                                                 node_coords[n][0] - cx))
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
            writer.writerow([c1[0], c1[1], c1[2], c2[0], c2[1], c2[2], idx])

    print('  Specimen outline: %d top boundary edges -> %s' % (len(boundary_edges), out_csv))
    return out_csv


def _element_xy_polygon_from_element(elem_obj, node_coords):
    """
    Return an ordered XY footprint polygon for an element object.
    Uses the element's highest-z face, so bottom-layer deleted elements still
    get a top-view cell footprint.
    """
    coords = [(n, node_coords[n]) for n in elem_obj.connectivity if n in node_coords]
    if len(coords) < 3:
        return []
    zmax = max(c[2] for _, c in coords)
    zvals = sorted(set(round(c[2], 6) for _, c in coords))
    if len(zvals) > 1:
        dz_min = min(abs(zvals[i + 1] - zvals[i]) for i in range(len(zvals) - 1)
                     if abs(zvals[i + 1] - zvals[i]) > 1e-9)
        ztol = max(1e-6, 0.25 * dz_min)
    else:
        ztol = 1e-6
    face = [(n, c) for n, c in coords if abs(c[2] - zmax) <= ztol]
    if len(face) < 3:
        return []

    cx = sum(c[0] for _, c in face) / float(len(face))
    cy = sum(c[1] for _, c in face) / float(len(face))
    ordered = sorted(face, key=lambda item: math.atan2(item[1][1] - cy, item[1][0] - cx))
    return [(c[0], c[1], c[2]) for _, c in ordered]


def _element_xy_polygon(inst, node_coords, elem_label):
    elem_obj = None
    for elem in inst.elements:
        if elem.label == elem_label:
            elem_obj = elem
            break
    if elem_obj is None:
        return []
    return _element_xy_polygon_from_element(elem_obj, node_coords)


def _polygon_area_xy(poly):
    if len(poly) < 3:
        return 0.0
    area = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i][0], poly[i][1]
        x2, y2 = poly[(i + 1) % len(poly)][0], poly[(i + 1) % len(poly)][1]
        area += x1 * y2 - x2 * y1
    return abs(area) * 0.5


def _top_face_area_map(odb, labels):
    inst_name, centroids, top_labels, meta = _element_centroid_maps(odb)
    if not inst_name:
        return {}
    inst = odb.rootAssembly.instances[inst_name]
    node_coords = {n.label: n.coordinates for n in inst.nodes}
    label_set = set(labels)
    areas = {}
    for elem in inst.elements:
        if elem.label not in label_set:
            continue
        areas[elem.label] = _polygon_area_xy(_element_xy_polygon_from_element(elem, node_coords))
    return areas


def _median_xy_spacing(labels, centroids):
    pts = []
    for lbl in labels:
        if lbl in centroids:
            c = centroids[lbl]
            pts.append((c[0], c[1]))
    max_pts = int(os.environ.get('POSTPROC_SPACING_SAMPLE_MAX', '1500'))
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


def _connected_xy_components(labels, centroids, spacing_labels=None):
    label_set = set(lbl for lbl in labels if lbl in centroids)
    if not label_set:
        return []
    spacing = _median_xy_spacing(spacing_labels if spacing_labels is not None else label_set,
                                 centroids)
    conn_radius = max(1e-6, 1.6 * spacing)
    cell_size = conn_radius
    grid = {}
    for lbl in label_set:
        x, y = centroids[lbl][0], centroids[lbl][1]
        key = (int(math.floor(x / cell_size)), int(math.floor(y / cell_size)))
        grid.setdefault(key, set()).add(lbl)

    def _remove(lbl):
        x, y = centroids[lbl][0], centroids[lbl][1]
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
            x0, y0 = centroids[lbl][0], centroids[lbl][1]
            neighbors = []
            ix = int(math.floor(x0 / cell_size))
            iy = int(math.floor(y0 / cell_size))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for other in list(grid.get((ix + dx, iy + dy), ())):
                        x1, y1 = centroids[other][0], centroids[other][1]
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


def _largest_deleted_component(labels, centroids, spacing_labels=None):
    comps = _connected_xy_components(labels, centroids, spacing_labels=spacing_labels)
    if not comps:
        return set()
    return set(max(comps, key=len))


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

    rows = []

    def add_polygon(label, role, rank):
        poly = _element_xy_polygon(inst, node_coords, label)
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
    if not selected_labels:
        print('  %s: skipped (no selected top-surface labels)' % method_name)
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
                eps1, eps2, method_name,
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


def _select_cluster_elements(odb, frames, failure_frame_idx, dome_labels,
                             fracture_cluster_labels=None, fracture_center=None,
                             center_label=None, keep_count=5, search_radius=5.0):
    """
    Return ranked list of (label, {ip, eps1, eps2}) for the top-surface alive elements
    nearest the fracture zone at the pre-fracture frame.
    Shared by the averaging loop and _write_strain_cluster_csv.
    """
    if failure_frame_idx is None or failure_frame_idx <= 0:
        return []
    inst_name, centroids, top_labels, _ = _element_centroid_maps(odb)
    if not centroids or not top_labels:
        return []

    fracture_cluster_labels = set(fracture_cluster_labels or [])
    fracture_centers = [centroids[lbl] for lbl in fracture_cluster_labels if lbl in centroids]
    if fracture_center is not None:
        cx0, cy0 = fracture_center[0], fracture_center[1]
    elif fracture_centers:
        cx0, cy0, _ = _cluster_center(fracture_cluster_labels, centroids)
    elif center_label is not None and center_label in centroids:
        cx0, cy0 = centroids[center_label][0], centroids[center_label][1]
    else:
        cx0, cy0 = 0.0, 0.0
    search_r_sq = search_radius * search_radius

    pre_frame = frames[failure_frame_idx - 1]
    if 'LE' not in pre_frame.fieldOutputs.keys():
        return []

    alive_labels = None
    if 'STATUS' in pre_frame.fieldOutputs.keys():
        alive_labels = set()
        for val in pre_frame.fieldOutputs['STATUS'].values:
            if val.data >= 0.5:
                alive_labels.add(val.elementLabel)

    candidates = {}
    for val in pre_frame.fieldOutputs['LE'].values:
        lbl = val.elementLabel
        if dome_labels is not None and lbl not in dome_labels:
            continue
        if lbl not in top_labels:
            continue
        if alive_labels is not None and lbl not in alive_labels:
            continue
        cx, cy = centroids.get(lbl, (0.0, 0.0, 0.0))[:2]
        if fracture_centers:
            dist_sq = min((cx - fc[0]) ** 2 + (cy - fc[1]) ** 2 for fc in fracture_centers)
        else:
            dist_sq = (cx - cx0) ** 2 + (cy - cy0) ** 2
        if dist_sq > search_r_sq:
            continue
        eps1, eps2 = _principal_strains_from_LE(val)
        thinning = eps1 + eps2   # = -ε₃ > 0, thinning magnitude; highest = most necked
        old = candidates.get(lbl)
        if old is None or thinning > old['thinning']:
            candidates[lbl] = {'ip': val.integrationPoint, 'eps1': eps1, 'eps2': eps2,
                                'thinning': thinning}

    ranked = sorted(candidates.items(), key=lambda item: item[1]['thinning'], reverse=True)
    return ranked[:min(max(1, int(keep_count)), len(ranked))]


def _write_strain_cluster_csv(odb, frames, failure_frame_idx, dome_labels, out_dir,
                              center_label=None, keep_count=5, search_radius=5.0,
                              fracture_cluster_labels=None, fracture_center=None):
    """
    Write a DIC-like diagnostic cluster:
      top-surface elements near the first deleted fracture-element cluster, alive at
      pre-fracture, highest major strain elements at the pre-fracture frame.
    """
    out_csv = os.path.join(out_dir, 'strain_cluster.csv')
    if failure_frame_idx is None or failure_frame_idx <= 0:
        return None

    selected = _select_cluster_elements(
        odb, frames, failure_frame_idx, dome_labels,
        fracture_cluster_labels=fracture_cluster_labels,
        fracture_center=fracture_center,
        center_label=center_label,
        keep_count=keep_count,
        search_radius=search_radius,
    )
    if not selected:
        print('  Cluster paths : skipped (no top-surface candidates within %.2f mm of element %s)'
              % (search_radius, str(center_label)))
        return None

    _, centroids, _, _ = _element_centroid_maps(odb)
    n_keep         = len(selected)
    selected_keys  = set((lbl, rec['ip']) for lbl, rec in selected)
    candidate_keys = selected_keys
    area_map = _top_face_area_map(odb, [lbl for lbl, _ in selected])
    rank_map = {(lbl, rec['ip']): idx + 1 for idx, (lbl, rec) in enumerate(selected)}

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
    for fi in range(failure_frame_idx):
        frame = frames[fi]
        eqps = {}
        if 'SDV1' in frame.fieldOutputs.keys():
            for val in frame.fieldOutputs['SDV1'].values:
                key = (val.elementLabel, val.integrationPoint)
                if key in candidate_keys:
                    eqps[key] = val.data
        eqps_by_frame.append(eqps)

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
            eps1, eps2 = _principal_strains_from_LE(val)
            cx, cy, cz = centroids.get(val.elementLabel, (0.0, 0.0, 0.0))
            area = area_map.get(val.elementLabel, 1.0)
            if fracture_centers:
                dist = math.sqrt(min(
                    (cx - fc[0]) * (cx - fc[0]) + (cy - fc[1]) * (cy - fc[1])
                    for fc in fracture_centers
                ))
            else:
                dist = math.sqrt((cx - center_x) * (cx - center_x) +
                                 (cy - center_y) * (cy - center_y))
            if key in selected_keys:
                base_row = (
                    t, val.elementLabel, val.integrationPoint, rank_map[key],
                    float(rank_map[key]) / float(n_keep),
                    cx, cy, cz, area, dist, center_label, center_x, center_y, center_z,
                    len(fracture_cluster_labels),
                    eps1, eps2,
                    eqps_by_frame[fi].get(key, 0.0),
                    'top_surface_near_first_fracture_element_cluster_r%.1fmm_thinning_top%d' % (search_radius, n_keep),
                )
                rows.append(base_row)
            neighborhood_rows.append((
                t, val.elementLabel, val.integrationPoint,
                rank_map.get(key, 0),
                1 if key in selected_keys else 0,
                cx, cy, cz, area, dist, center_label, center_x, center_y, center_z,
                len(fracture_cluster_labels),
                eps1, eps2,
                eqps_by_frame[fi].get(key, 0.0),
                'top_surface_near_first_fracture_element_cluster_r%.1fmm_all_candidates' % search_radius,
            ))

    with open(out_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow([
            'time_s', 'element_label', 'integration_point', 'selection_rank',
            'selection_fraction_rank', 'centroid_x', 'centroid_y', 'centroid_z',
            'top_face_area', 'distance_to_fracture_center', 'fracture_center_element',
            'fracture_center_x', 'fracture_center_y', 'fracture_center_z',
            'fracture_cluster_size',
            'eps1_major', 'eps2_minor', 'EQPS', 'selection_method',
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
            'eps1_major', 'eps2_minor', 'EQPS', 'selection_method',
        ])
        writer.writerows(neighborhood_rows)

    print('  Cluster paths : %d elements (within %.1f mm of first fracture-element cluster, anchor %s, cluster n=%d) -> %s'
          % (n_keep, search_radius,
             str(center_label), len(fracture_cluster_labels), out_csv))
    print('  Neighborhood  : %d rows for %d candidate elements -> %s'
          % (len(neighborhood_rows), n_keep, neigh_csv))
    _write_strain_cluster_faces_csv(odb, out_dir, selected, center_label,
                                    fracture_cluster_labels=fracture_cluster_labels)
    return out_csv


def extract_strain_path(odb_path, out_csv=None, r_dome=None):
    from odbAccess import openOdb

    odb_path = os.path.abspath(odb_path)
    if out_csv is None:
        out_csv = os.path.join(os.path.dirname(odb_path), 'strain_path.csv')
    if r_dome is None:
        r_dome = R_DOME_DEFAULT

    print('=' * 60)
    print('  postproc.py — strain path extraction')
    print('  ODB    : %s' % odb_path)
    print('  R_DOME : %.1f mm  (= PUNCH_RADIUS / 2)' % r_dome)
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

    # ── 2. Find first failure frame in dome zone ──────────────
    fracture_type     = 'dome'
    failure_frame_idx = None
    all_centroids = {}
    fracture_cluster_labels = set()
    first_deletion_frame_idx = None
    first_deletion_labels = set()
    min_cluster_cells = int(os.environ.get(
        'MIN_FRACTURE_CLUSTER_CELLS',
        str(MIN_FRACTURE_CLUSTER_CELLS),
    ))
    _, all_centroids, _, _ = _element_centroid_maps(odb)
    spacing_labels = dome_labels if dome_labels is not None else all_centroids.keys()

    for i, frame in enumerate(frames):
        deleted = _deleted_labels_in_frame(frame, dome_labels)
        if not deleted:
            continue
        if first_deletion_frame_idx is None:
            first_deletion_frame_idx = i
            first_deletion_labels = set(deleted)
        comp = _largest_deleted_component(deleted, all_centroids, spacing_labels=spacing_labels)
        if len(comp) >= min_cluster_cells:
            failure_frame_idx = i
            fracture_cluster_labels = comp
            break

    if failure_frame_idx is None and first_deletion_frame_idx is not None:
        failure_frame_idx = first_deletion_frame_idx
        fracture_cluster_labels = _largest_deleted_component(
            first_deletion_labels, all_centroids, spacing_labels=spacing_labels,
        )
        print('  WARNING: no dome fracture cluster reached %d cells; using first deletion cluster (%d cells).'
              % (min_cluster_cells, len(fracture_cluster_labels)))

    # Fallback: check for any deletion outside dome
    if failure_frame_idx is None:
        outer_fail = None
        for i, frame in enumerate(frames):
            if 'STATUS' not in frame.fieldOutputs.keys():
                continue
            for val in frame.fieldOutputs['STATUS'].values:
                if val.data < 0.5:
                    outer_fail = i
                    break
            if outer_fail is not None:
                break

        if outer_fail is not None:
            print('  WARNING: fracture OUTSIDE dome zone at frame %d (t = %.4f s).'
                  % (outer_fail, frames[outer_fail].frameValue))
            print('           Likely base/edge artefact — endpoint snapped to that frame.')
            failure_frame_idx = outer_fail
            fracture_type     = 'base'
        else:
            print('  WARNING: no deleted elements found — using last frame.')
            failure_frame_idx = n_frames - 1
            fracture_type     = 'none'

    if failure_frame_idx == 0:
        print('  ERROR: failure at frame 0 — check ODB.')
        odb.close()
        return None

    if fracture_type == 'dome':
        print('  Fracture type  : dome  (frame %d, t = %.4f s, cluster threshold=%d cells)'
              % (failure_frame_idx, frames[failure_frame_idx].frameValue, min_cluster_cells))
    elif fracture_type == 'base':
        print('  Fracture type  : BASE (artefact) — endpoint = frame %d'
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
                                         spacing_labels=spacing_labels)
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
            node_xy  = {n.label: (n.coordinates[0], n.coordinates[1])
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

    # ── 4. Build diagnostic cluster using the same logic as strain_cluster export.
    # This is kept as supplementary scatter/validation data. The primary FLC
    # strain path below uses the single critical element/IP, not a cluster average.
    _cluster_selected = _select_cluster_elements(
        odb, frames, failure_frame_idx, dome_labels,
        fracture_cluster_labels=fracture_cluster_labels,
        fracture_center=fracture_center,
        center_label=crit_label,
        keep_count=5,
        search_radius=5.0,
    )
    if not _cluster_selected:
        print('  Diagnostic cluster: no neighbours found; strain_cluster may be skipped')
    else:
        print('  Diagnostic cluster: %d top-surface elements (strain_cluster export)'
              % len(_cluster_selected))
    cluster_eps1 = [rec['eps1'] for _, rec in _cluster_selected if rec.get('eps1') is not None]
    cluster_eps2 = [rec['eps2'] for _, rec in _cluster_selected if rec.get('eps2') is not None]

    # ── 5. Extract CSV quantities for the single critical element/IP ──────────
    # This is the physical material-point trajectory used for forming_limits.csv.
    # The five-element cluster remains available in strain_cluster.csv but is not
    # averaged into the headline FLC point.
    def _is_crit_value(val):
        if val.elementLabel != crit_label:
            return False
        return crit_ip is None or val.integrationPoint == crit_ip

    records     = []
    times_list  = []
    d_dome_list = []

    sdv6_in_odb = True
    sdv4_in_odb = True

    for fi in range(failure_frame_idx):
        frame = frames[fi]
        t     = frame.frameValue
        eps1 = None
        eps2 = None
        eqps = None
        triax = None
        d_crit = None
        d_dome = 0.0

        for val in frame.fieldOutputs['LE'].values:
            if _is_crit_value(val):
                e1, e2 = _principal_strains_from_LE(val)
                if e1 is not None:
                    eps1 = e1
                    eps2 = e2
                    break

        if 'SDV1' in frame.fieldOutputs.keys():
            for val in frame.fieldOutputs['SDV1'].values:
                if _is_crit_value(val):
                    eqps = val.data
                    break

        if sdv4_in_odb and 'SDV4' in frame.fieldOutputs.keys():
            for val in frame.fieldOutputs['SDV4'].values:
                if _is_crit_value(val):
                    triax = val.data
                    break
        elif sdv4_in_odb and fi == 0:
            sdv4_in_odb = False
            print('  WARNING: SDV4 (TRIAX) not found in ODB — TRIAX column set to zero.')

        if sdv6_in_odb and 'SDV6' in frame.fieldOutputs.keys():
            for val in frame.fieldOutputs['SDV6'].values:
                if _is_crit_value(val):
                    d_crit = val.data
                in_dome = (dome_labels is None) or (val.elementLabel in dome_labels)
                if in_dome and val.data > d_dome:
                    d_dome = val.data
        elif sdv6_in_odb and fi == 0:
            sdv6_in_odb = False
            print('  WARNING: SDV6 not found in ODB — D columns set to zero.')

        if eps1 is not None:
            records.append((t, eps1, eps2,
                            eqps or 0.0,
                            d_crit or 0.0,
                            fracture_type, d_dome,
                            triax or 0.0))
            times_list.append(t)
            d_dome_list.append(d_dome)

    print('  Primary path  : critical element %d IP %s (%d points)'
          % (crit_label, str(crit_ip), len(records)))

    # ── 5. Fracture limit only. Necking methods will be rebuilt cleanly later.
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
    # For 'base'/'none': stored with the fracture_type label so the app can flag them.
    lim_frac = _lim(len(records) - 1)

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
    print('')

    out_dir = os.path.dirname(out_csv)

    # ── 6. Write strain_path.csv ──────────────────────────────
    with open(out_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['time_s', 'eps1_major', 'eps2_minor', 'EQPS', 'D', 'fracture_type', 'd_dome_max', 'TRIAX'])
        writer.writerows(records)

    print('  Written %d points -> %s' % (len(records), out_csv))

    # ── 7. Write energy_data.csv and punch_fd.csv ────────────
    # punch_fd is written first so we can interpolate U3_mm at fracture time.
    e_times, ke_vals, ie_vals = _write_energy_csv(odb, out_dir)
    p_times, u3_vals, rf3_vals = _write_punch_fd_csv(odb, out_dir)

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

    # ── 8. Write forming_limits.csv ───────────────────────────
    limits_csv = os.path.join(out_dir, 'forming_limits.csv')
    with open(limits_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['method', 'eps1_major', 'eps2_minor', 'EQPS', 'D',
                         'time_s', 'U3_mm', 'fracture_type',
                         'path_source', 'critical_element', 'critical_ip',
                         'cluster_n', 'cluster_eps1_min', 'cluster_eps1_max',
                         'cluster_eps2_min', 'cluster_eps2_max'])
        if lim_frac:
            writer.writerow(['fracture',
                             lim_frac[0], lim_frac[1], lim_frac[2], lim_frac[3],
                             lim_frac[4],
                             '' if u3_frac is None else round(u3_frac, 4),
                             fracture_type,
                             'critical_element',
                             crit_label,
                             '' if crit_ip is None else crit_ip,
                             len(_cluster_selected),
                             '' if not cluster_eps1 else min(cluster_eps1),
                             '' if not cluster_eps1 else max(cluster_eps1),
                             '' if not cluster_eps2 else min(cluster_eps2),
                             '' if not cluster_eps2 else max(cluster_eps2)])
    print('  Forming limits -> %s' % limits_csv)

    # ── 9. Write top-surface strain-path cluster ─────────────
    _write_strain_cluster_csv(odb, frames, failure_frame_idx, dome_labels, out_dir,
                              center_label=crit_label, keep_count=5,
                              search_radius=5.0,
                              fracture_cluster_labels=fracture_cluster_labels,
                              fracture_center=fracture_center)

    # ── 10. Write specimen outline for cluster-location diagnostics ─────────
    _write_specimen_outline_csv(odb, out_dir)

    # ── 11. Write whole-dome top-surface field for independent V&H ──────────
    if dome_labels is not None:
        _write_top_surface_history_csv(
            odb, frames, failure_frame_idx, dome_labels, out_dir,
            'strain_dome.csv', 'top_surface_dome_all_candidates',
        )

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
        for reg_name, region in step.historyRegions.items():
            ho = region.historyOutputs.keys()
            if 'U3' not in ho or 'RF3' not in ho:
                continue
            u3_data  = region.historyOutputs['U3'].data
            rf3_data = region.historyOutputs['RF3'].data
            if reg_name not in candidates:
                candidates[reg_name] = []
            for (t, u3), (_, rf3) in zip(u3_data, rf3_data):
                candidates[reg_name].append([step.name, t_offset + t, u3, rf3])
        t_offset += step.timePeriod

    if not candidates:
        print('  WARNING: no history region with U3+RF3 found — punch_fd.csv not written.')
        return [], [], []

    def _u3_range(rows):
        u3s = [r[2] for r in rows]
        return max(u3s) - min(u3s)

    best = max(candidates.keys(), key=lambda n: _u3_range(candidates[n]))
    rows = candidates[best]
    print('  Punch F-d: region "%s"  (%d points)' % (best, len(rows)))

    with open(out_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['step_name', 'total_time_s', 'U3_mm', 'RF3_N'])
        writer.writerows(rows)

    print('  Punch F-d data  -> %s' % out_csv)
    return [r[1] for r in rows], [r[2] for r in rows], [r[3] for r in rows]


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

    eqps_list = data.get('SDV1', [0.0] * len(times))
    d_list    = data.get('SDV6', [0.0] * len(times))
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

    times_c = times[:n]; e1_c = eps1_list[:n]; e2_c = eps2_list[:n]
    eqps_c  = eqps_list[:n]; d_c = d_list[:n]

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
    d_dome_max and CoV are matched by nearest field-output frame time.
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
