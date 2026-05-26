from abaqus import *
from abaqusConstants import *
import __main__

import section
import regionToolset
import displayGroupMdbToolset as dgm
import part
import material
import assembly
import step
import interaction
import load
import mesh
import optimization
import job
import sketch
import visualization
import xyPlot
import displayGroupOdbToolset as dgo
import connectorBehavior
import math
import sympy as sp
import os


session.journalOptions.setValues(replayGeometry=COORDINATE, recoverGeometry=COORDINATE)
# ----------------
# ---Parameters---

#Has to be >= 0.02mm
Thickness = 1.75

Mirror = False #assumes symmetry along X and Y axis to only simulation 1/4. Not correct for 45deg material orientation (but could be neglectable).

#20, 50, 80, 90, 100, 120, 200
# Geometry = 20
# Geometry = 50
# Geometry = 80
# Geometry = 90
# Geometry = 100
# Geometry = 120
Geometry = 200

# --- Partitions ---

if Geometry == 20:
    # X-Distance for the inner partition (must be smaller than the 1/2*Geometry)
    P_inner_x = 5.0
    # Radius of the curve in the middle
    P_inner_r = 150.0
    # Radius of the Circle (must intersect the flat part in W20 and W50)
    P_circle_r = 55.0
    # Y-distance from zero for XZplane partition (must be smaller than 12.5mm)
    P_XZplane_1 = 5.0

if Geometry == 50:
    # X-Distance for the inner partition (must be smaller than the 1/2*Geometry)
    P_inner_x = 10.0
    # Radius of the curve in the middle
    P_inner_r = 120.0
    # Radius of the Circle (must intersect the flat part in W20 and W50)
    P_circle_r = 65.0
    # Y-distance from zero for XZplane partition (must be smaller than 12.5mm)
    P_XZplane_1 = 5.0

if Geometry == 80:
    # X-Distance for the inner partition (must be smaller than the 1/2*Geometry)
    P_inner_x = 10.0
    # Radius of the curve in the middle
    P_inner_r = 120.0
    # Radius of the Circle (must intersect the flat part in W20 and W50)
    P_circle_r = 65.0
    # Y-distance from zero for XZplane partition (must be smaller than 12.5mm)
    P_XZplane_1 = 5.0

if Geometry == 90:
    # X-Distance for the inner partition (must be smaller than the 1/2*Geometry)
    P_inner_x = 10.0
    # Radius of the curve in the middle
    P_inner_r = 120.0
    # Radius of the Circle (must intersect the flat part in W20 and W50)
    P_circle_r = 65.0
    # Y-distance from zero for XZplane partition (must be smaller than 12.5mm)
    P_XZplane_1 = 5.0

if Geometry == 100:
    # X-Distance for the inner partition (must be smaller than the 1/2*Geometry)
    P_inner_x = 10.0
    # Radius of the curve in the middle
    P_inner_r = 120.0
    # Radius of the Circle (must intersect the flat part in W20 and W50)
    P_circle_r = 65.0
    # Y-distance from zero for XZplane partition (must be smaller than 12.5mm)
    P_XZplane_1 = 5.0

if Geometry == 120:
    # X-Distance for the inner partition (must be smaller than the 1/2*Geometry)
    P_inner_x = 10.0
    # Radius of the curve in the middle
    P_inner_r = 120.0
    # Radius of the Circle (must intersect the flat part in W20 and W50)
    P_circle_r = 65.0
    # Y-distance from zero for XZplane partition (must be smaller than 12.5mm)
    P_XZplane_1 = 5.0

if Geometry == 200:
    # X-Distance for the inner partition (must be smaller than the 1/2*Geometry)
    P_inner_x = 10.0
    # Radius of the curve in the middle
    P_inner_r = 120.0
    # Radius of the Circle (must intersect the flat part in W20 and W50)
    P_circle_r = 65.0
    # Y-distance from zero for XZplane partition (must be smaller than 12.5mm)
    P_XZplane_1 = 5.0
    # ------
    #For W200:
    P_section1_y = 10
    P_section2_r = 20 #Must be bigger than root(2)*P_section3_r
    P_section3_r = 50

# -----------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------

# --- fine Mesh ---
#Size of elements (Script later calculates the number of elements for more robustness)
M_s_section1_x = 0.2
M_s_section1_y = 0.2
M_s_section2_x = 0.4
M_s_section2_y = 0.4

M_s_section3_y = 0.8
M_s_section3_1_y = 0.8 #only W20 & W50 second most outer section, make same size as M_s_section3_y for similar meshing as the other geometries.

M_s_section4_y = 1.2

#For W200:
M_s_section1 = 0.2
M_s_section2 = 0.4
M_s_section3 = 0.8
M_s_section4 = 0.4

#Number of elements
M_n_thickness = 16

# -----------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------
# # --- fast Mesh ---
# #Size of elements (Script later calculates the number of elements for more robustness)
# M_s_section1_x = 1.0
# M_s_section1_y = 1.0
#
# M_s_section2_x = 3.0
# M_s_section2_y = 3.0
#
# M_s_section3_y = 3.0
# M_s_section3_1_y = 3.0 #only W20 & W50 second most outer section, make same size as M_s_section3_y for similar meshing as the other geometries.
#
# M_s_section4_y = 3.0
#
# #For W200:
# M_s_section1 = 0.5
# M_s_section2 = 1.0
# M_s_section3 = 2.0
# M_s_section4 = 4.0
#
# #Number of elements
# M_n_thickness = 1

# -----------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------

#---Calculations, don't change!---
Width = Geometry / 2.0
P_curve_x = P_inner_x+P_inner_r-(P_inner_r**2-0.1**2)**0.5
P_circle_y1 = (P_circle_r**2-1)**0.5
P_XZplane_3 = 39.77178

#intersection point two circles
y2 = 12.5
r1 = P_circle_r
r2 = P_inner_r
x2 = P_inner_x+P_inner_r

# (Don't Change, calculated from size for more robustness)
M_n_section1_x = int(math.ceil(P_inner_x / M_s_section1_x))
M_n_section2_x = int(math.ceil((Width - P_inner_x) / M_s_section2_x))
M_n_section1_y = int(math.ceil(P_XZplane_1 / M_s_section1_y))
M_n_section2_y = int(math.ceil((12.5 - P_XZplane_1) / M_s_section2_y))
M_n_section3_y = int(math.ceil((P_circle_r - 12.5) / M_s_section3_y))
M_n_section4_y = int(math.ceil((70.0 - P_circle_r) / M_s_section4_y))

#For W200:
M_n_section1 = int(math.ceil(P_section1_y / M_s_section1))
M_n_section2 = int(math.ceil((P_section2_r-P_section1_y) / M_s_section2))
M_n_section3 = int(math.ceil((P_section3_r-P_section2_r) / M_s_section3))
M_n_section4 = int(math.ceil((70-P_section3_r) / M_s_section4))

if Geometry == 20:
    M_n_section3_y = int(math.ceil((48.35 - 12.5) / M_s_section3_y))
    M_n_section3_1_y = int(math.ceil((P_circle_r - 48.35) / M_s_section3_1_y))
if Geometry == 50:
    M_n_section3_y = int(math.ceil((58.21 - 12.5) / M_s_section3_y))
    M_n_section3_1_y = int(math.ceil((P_circle_r - 58.21) / M_s_section3_1_y))

session.viewports['Viewport: 1'].disableRefresh()


def circle_intersections(r1, r2, x2, y2):
    x1, y1 = 0.0, 0.0

    dx = x2 - x1
    dy = y2 - y1
    d = math.hypot(dx, dy)

    # Edge cases
    if d > r1 + r2:
        return []
    if d < abs(r1 - r2):
        return []
    if d == 0 and r1 == r2:
        return []

    a = (r1**2 - r2**2 + d**2) / (2 * d)
    h_sq = r1**2 - a**2
    h = math.sqrt(max(h_sq, 0.0))

    xm = x1 + a * dx / d
    ym = y1 + a * dy / d

    rx = -dy * (h / d)
    ry = dx * (h / d)

    p1 = (xm + rx, ym + ry)
    p2 = (xm - rx, ym - ry)

    return [p1, p2]

def Specimen_Geometry():

    #Creates W200
    s = mdb.models['Model-1'].ConstrainedSketch(name='__profile__',
                                                sheetSize=200.0)
    g, v, d, c = s.geometry, s.vertices, s.dimensions, s.constraints
    session.viewports['Viewport: 1'].disableRefresh()
    s.setPrimaryObject(option=STANDALONE)
    s.Line(point1=(0.0, 0.0), point2=(70.0, 0.0))
    s.Line(point1=(0.0, 0.0), point2=(0.0, 70.0))
    s.ArcByCenterEnds(center=(0.0, 0.0), point1=(0.0, 70.0), point2=(70.0, 0.0),
                      direction=CLOCKWISE)
    p = mdb.models['Model-1'].Part(name='Specimen', dimensionality=THREE_D,
                                   type=DEFORMABLE_BODY)
    p = mdb.models['Model-1'].parts['Specimen']
    p.BaseSolidExtrude(sketch=s, depth=Thickness)
    s.unsetPrimaryObject()
    p = mdb.models['Model-1'].parts['Specimen']
    del mdb.models['Model-1'].sketches['__profile__']
    session.viewports['Viewport: 1'].setValues(displayedObject=p)

    # Flat Cutout (only in simulation region for W20 & W50)
    if Geometry == 20:
        p = mdb.models['Model-1'].parts['Specimen']
        session.viewports['Viewport: 1'].disableRefresh()
        f1, e1 = p.faces, p.edges
        t = p.MakeSketchTransform(sketchPlane=f1.findAt(coordinates=(46.429166,
                                                                     3.32068, Thickness)),
                                  sketchUpEdge=e1.findAt(coordinates=(0.0, 17.5, Thickness)),
                                  sketchPlaneSide=SIDE1, sketchOrientation=LEFT, origin=(0.0, 0.0, Thickness))
        s1 = mdb.models['Model-1'].ConstrainedSketch(name='__profile__',
                                                     sheetSize=198.01, gridSpacing=4.95, transform=t)
        g, v, d, c = s1.geometry, s1.vertices, s1.dimensions, s1.constraints
        s1.setPrimaryObject(option=SUPERIMPOSE)
        p = mdb.models['Model-1'].parts['Specimen']
        p.projectReferencesOntoSketch(sketch=s1, filter=COPLANAR_EDGES)
        s1.rectangle(point1=(100.0, 0.0), point2=(27.5, 100.0))
        p = mdb.models['Model-1'].parts['Specimen']
        f, e = p.faces, p.edges
        p.CutExtrude(sketchPlane=f.findAt(coordinates=(46.429166, 3.32068, Thickness)),
                     sketchUpEdge=e.findAt(coordinates=(0.0, 17.5, Thickness)),
                     sketchPlaneSide=SIDE1, sketchOrientation=LEFT, sketch=s1,
                     flipExtrudeDirection=OFF)
        s1.unsetPrimaryObject()
        del mdb.models['Model-1'].sketches['__profile__']

    # Flat Cutout (only in simulation region for W20 & W50)
    if Geometry == 50:
        p = mdb.models['Model-1'].parts['Specimen']
        session.viewports['Viewport: 1'].disableRefresh()
        f1, e1 = p.faces, p.edges
        t = p.MakeSketchTransform(sketchPlane=f1.findAt(coordinates=(46.429166,
                                                                     3.32068, Thickness)),
                                  sketchUpEdge=e1.findAt(coordinates=(0.0, 17.5, Thickness)),
                                  sketchPlaneSide=SIDE1, sketchOrientation=LEFT, origin=(0.0, 0.0, Thickness))
        s = mdb.models['Model-1'].ConstrainedSketch(name='__profile__',
                                                    sheetSize=198.01, gridSpacing=4.95, transform=t)
        g, v, d, c = s.geometry, s.vertices, s.dimensions, s.constraints
        s.setPrimaryObject(option=SUPERIMPOSE)
        p = mdb.models['Model-1'].parts['Specimen']
        p.projectReferencesOntoSketch(sketch=s, filter=COPLANAR_EDGES)
        s.rectangle(point1=(100.0, 100.0), point2=(42.5, 0.0))
        p = mdb.models['Model-1'].parts['Specimen']
        f, e = p.faces, p.edges
        p.CutExtrude(sketchPlane=f.findAt(coordinates=(46.429166, 3.32068, Thickness)),
                     sketchUpEdge=e.findAt(coordinates=(0.0, 17.5, Thickness)),
                     sketchPlaneSide=SIDE1, sketchOrientation=LEFT, sketch=s,
                     flipExtrudeDirection=OFF)
        s.unsetPrimaryObject()
        del mdb.models['Model-1'].sketches['__profile__']

    # Cutout Size (W200 cuts into nothing)
    p = mdb.models['Model-1'].parts['Specimen']
    f1, e1 = p.faces, p.edges
    session.viewports['Viewport: 1'].disableRefresh()
    t = p.MakeSketchTransform(sketchPlane=f1.findAt(coordinates=(1.0, 1.0, Thickness)),
                              sketchUpEdge=e1.findAt(coordinates=(0.0, 17.5, Thickness)),
                              sketchPlaneSide=SIDE1, sketchOrientation=LEFT, origin=(0.0, 0.0, Thickness))
    s = mdb.models['Model-1'].ConstrainedSketch(name='__profile__',
                                                sheetSize=198.01, gridSpacing=4.95, transform=t)
    g, v, d, c = s.geometry, s.vertices, s.dimensions, s.constraints
    s.setPrimaryObject(option=SUPERIMPOSE)
    p = mdb.models['Model-1'].parts['Specimen']
    p.projectReferencesOntoSketch(sketch=s, filter=COPLANAR_EDGES)
    s.Line(point1=(Width, 0.0), point2=(Width, 12.5))
    s.ArcByCenterEnds(center=(Width+30.0, 12.5), point1=(Width, 12.5), point2=(Width+30.0, 42.5), direction=CLOCKWISE)
    s.Line(point1=(Width+30.0, 42.5), point2=(200.0, 42.5))
    s.Line(point1=(200.0, 42.5), point2=(200.0, 0.0))
    s.Line(point1=(200.0, 0.0), point2=(Width, 0.0))
    p = mdb.models['Model-1'].parts['Specimen']
    f, e = p.faces, p.edges
    p.CutExtrude(sketchPlane=f.findAt(coordinates=(1.0, 1.0, Thickness)),
                 sketchUpEdge=e.findAt(coordinates=(0.0, 17.5, Thickness)),
                 sketchPlaneSide=SIDE1, sketchOrientation=LEFT, sketch=s,
                 flipExtrudeDirection=OFF)
    s.unsetPrimaryObject()
    del mdb.models['Model-1'].sketches['__profile__']

    #Create Sets
    p = mdb.models['Model-1'].parts['Specimen']
    f = p.faces
    faces = f.findAt(((0.1, (70**2-0.1**2)**0.5, 0.01), ))
    p.Set(faces=faces, name='EDGE')

    p = mdb.models['Model-1'].parts['Specimen']
    f = p.faces
    faces = f.findAt(((0.1, 0.0, 0.01), ))
    p.Set(faces=faces, name='YSYMM')

    p = mdb.models['Model-1'].parts['Specimen']
    f = p.faces
    faces = f.findAt(((0.0, 0.1, 0.01), ))
    p.Set(faces=faces, name='XSYMM')

    # p = mdb.models['Model-1'].parts['Specimen']
    # f = p.faces
    # faces = f.findAt(((0.1, 0.1, 0.0),))
    # p.Set(faces=faces, name='_ZMIN_S1')

    # p = mdb.models['Model-1'].parts['Specimen']
    # f = p.faces
    # faces = f.findAt(((0.1, 0.1, Thickness),))
    # p.Set(faces=faces, name='_ZMAX_S2')

    p = mdb.models['Model-1'].parts['Specimen']
    c = p.cells
    cells = c.findAt(((0.1, 0.1, 0.01),))
    p.Set(cells=cells, name='ELALL')

    #Surface
    p = mdb.models['Model-1'].parts['Specimen']
    s = p.faces
    side1Faces = s.findAt(((0.1, 0.1, 0.0),))
    p.Surface(side1Faces=side1Faces, name='ZMIN')

    p = mdb.models['Model-1'].parts['Specimen']
    s = p.faces
    side1Faces = s.findAt(((0.1, 0.1, Thickness),))
    p.Surface(side1Faces=side1Faces, name='ZMAX')

    #Sets for Output: top and bottom element in the middle of the Specimen
    p = mdb.models['Model-1'].parts['Specimen']
    v = p.vertices
    verts = v.findAt(((0.0, 0.0, 1.75), ))
    p.Set(vertices=verts, name='Out_Zmax')

    p = mdb.models['Model-1'].parts['Specimen']
    v = p.vertices
    verts = v.findAt(((0.0, 0.0, 0.0), ))
    p.Set(vertices=verts, name='Out_Zmin')

def Partitioning():
    if Geometry != 200:
        #Partition of the beginning of the curve---
        p = mdb.models['Model-1'].parts['Specimen']
        c = p.cells
        pickedCells = c.findAt(((0.01, 0.01, 0.01), ))
        e, d2 = p.edges, p.datums
        pickedEdges =(e.findAt(coordinates=(Width, 12.5, 0.01)), )
        p.PartitionCellByExtrudeEdge(line=e.findAt(coordinates=(0.01, 0.0, 0.0)),
            cells=pickedCells, edges=pickedEdges, sense=REVERSE)


        #Partition of the middle curve and straight part---
        p = mdb.models['Model-1'].parts['Specimen']
        f, e1, d1 = p.faces, p.edges, p.datums
        t = p.MakeSketchTransform(sketchPlane=f.findAt(coordinates=(6.846946, 14.39026, Thickness)),
                                  sketchUpEdge=e1.findAt(coordinates=(Width, 3.125, Thickness)),
                                  sketchPlaneSide=SIDE1, origin=(0.0, 0.0, Thickness))
        s1 = mdb.models['Model-1'].ConstrainedSketch(name='__profile__',
                                                     sheetSize=198.01, gridSpacing=4.95, transform=t)
        g, v, d, c = s1.geometry, s1.vertices, s1.dimensions, s1.constraints
        s1.setPrimaryObject(option=SUPERIMPOSE)
        p = mdb.models['Model-1'].parts['Specimen']
        p.projectReferencesOntoSketch(sketch=s1, filter=COPLANAR_EDGES)
        s1.unsetPrimaryObject()
        del mdb.models['Model-1'].sketches['__profile__']
        p = mdb.models['Model-1'].parts['Specimen']
        f1, e, d2 = p.faces, p.edges, p.datums
        t = p.MakeSketchTransform(sketchPlane=f1.findAt(coordinates=(6.846946, 14.39026, Thickness)),
                                  sketchUpEdge=e.findAt(coordinates=(0.0, 3.125, Thickness)), sketchPlaneSide=SIDE1,
                                  sketchOrientation=LEFT, origin=(0.0, 0.0, Thickness))
        s = mdb.models['Model-1'].ConstrainedSketch(name='__profile__',
                                                    sheetSize=198.01, gridSpacing=4.95, transform=t)
        g, v, d, c = s.geometry, s.vertices, s.dimensions, s.constraints
        s.setPrimaryObject(option=SUPERIMPOSE)
        p = mdb.models['Model-1'].parts['Specimen']
        p.projectReferencesOntoSketch(sketch=s, filter=COPLANAR_EDGES)
        s.Line(point1=(P_inner_x, 0.0), point2=(P_inner_x, 12.5))
        s.ArcByCenterEnds(center=(P_inner_x+P_inner_r, 12.5), point1=(P_inner_x, 12.5), point2=(P_inner_x+2*P_inner_r, 12.5), direction=CLOCKWISE)
        p = mdb.models['Model-1'].parts['Specimen']
        f = p.faces
        pickedFaces = f.findAt(((0.1, 13.0, Thickness),), ((0.1, 0.1, Thickness),))
        e1, d1 = p.edges, p.datums
        p.PartitionFaceBySketch(sketchUpEdge=e1.findAt(coordinates=(0.0, 3.125, Thickness)), faces=pickedFaces, sketchOrientation=LEFT, sketch=s)
        s.unsetPrimaryObject()
        del mdb.models['Model-1'].sketches['__profile__']

        p = mdb.models['Model-1'].parts['Specimen']
        c = p.cells
        pickedCells = c.findAt(((0.01, 0.01, Thickness),), ((0.0, 13.0, 0.01),))
        e, d2 = p.edges, p.datums
        pickedEdges = (e.findAt(coordinates=(P_inner_x, 3.125, Thickness)), e.findAt(coordinates=(P_curve_x, 12.6, Thickness)))
        p.PartitionCellByExtrudeEdge(line=e.findAt(coordinates=(0.0, 0.0, 0.01)),cells=pickedCells, edges=pickedEdges, sense=REVERSE)


        #Circle Partition---
        p = mdb.models['Model-1'].parts['Specimen']
        f1, e, d2 = p.faces, p.edges, p.datums
        t = p.MakeSketchTransform(sketchPlane=f1.findAt(coordinates=(0.1, 12.6, Thickness)),
                                  sketchUpEdge=e.findAt(coordinates=(0.0, 0.1, Thickness)), sketchPlaneSide=SIDE1,
                                  sketchOrientation=LEFT, origin=(0.0, 0.0, Thickness))
        s1 = mdb.models['Model-1'].ConstrainedSketch(name='__profile__',sheetSize=171.33, gridSpacing=4.28, transform=t)
        g, v, d, c = s1.geometry, s1.vertices, s1.dimensions, s1.constraints
        s1.setPrimaryObject(option=SUPERIMPOSE)
        p = mdb.models['Model-1'].parts['Specimen']
        p.projectReferencesOntoSketch(sketch=s1, filter=COPLANAR_EDGES)
        s1.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(0.0, P_circle_r))
        p = mdb.models['Model-1'].parts['Specimen']
        f = p.faces
        pickedFaces = f.findAt(((0.1, 12.6, Thickness),), ((P_inner_x+0.1, 12.6, Thickness),))
        e1, d1 = p.edges, p.datums
        p.PartitionFaceBySketch(sketchUpEdge=e1.findAt(coordinates=(0.0, 0.1,Thickness)), faces=pickedFaces, sketchOrientation=LEFT, sketch=s1)
        s1.unsetPrimaryObject()
        del mdb.models['Model-1'].sketches['__profile__']

        #Circle intersection calculation---
        points = circle_intersections(r1, r2, x2, y2)
        if not points:
            raise ValueError("No valid intersection between circles")
        # Select TOP intersection (highest y)
        top_point = max(points, key=lambda p: p[1])
        # Separate parameters
        p_intersect_x_top = top_point[0]
        p_intersect_y_top = top_point[1]

        P_intersect_x_right = p_intersect_x_top+0.1
        P_intersect_y_right = (P_circle_r**2-P_intersect_x_right**2)**0.5

        p = mdb.models['Model-1'].parts['Specimen']
        c = p.cells
        pickedCells = c.findAt(((0.1, 12.6, Thickness),), ((P_inner_x+0.1, 12.6, Thickness),))
        e, d2 = p.edges, p.datums
        pickedEdges = (e.findAt(coordinates=(1.0, P_circle_y1, Thickness)), e.findAt(coordinates=(P_intersect_x_right, P_intersect_y_right, Thickness)))
        p.PartitionCellByExtrudeEdge(line=e.findAt(coordinates=(0.0, 0.0, 0.01)),cells=pickedCells, edges=pickedEdges, sense=REVERSE)

        #Smaller Partition XY Plane below 12.5mm
        p = mdb.models['Model-1'].parts['Specimen']
        f, e, d = p.faces, p.edges, p.datums
        t = p.MakeSketchTransform(sketchPlane=f.findAt(coordinates=(0.1, 0.1, Thickness)),
                                  sketchUpEdge=e.findAt(coordinates=(0.0, 0.1, Thickness)),
                                  sketchPlaneSide=SIDE1, sketchOrientation=LEFT, origin=(0.0, 0.0, Thickness))
        s = mdb.models['Model-1'].ConstrainedSketch(name='__profile__',
                                                    sheetSize=29.68, gridSpacing=0.74, transform=t)
        g, v, d1, c = s.geometry, s.vertices, s.dimensions, s.constraints
        s.setPrimaryObject(option=SUPERIMPOSE)
        p = mdb.models['Model-1'].parts['Specimen']
        p.projectReferencesOntoSketch(sketch=s, filter=COPLANAR_EDGES)
        s.Line(point1=(0.0, P_XZplane_1), point2=(Width, P_XZplane_1))
        p = mdb.models['Model-1'].parts['Specimen']
        f = p.faces
        pickedFaces = f.findAt(((P_inner_x-0.1, P_XZplane_1, Thickness),), ((P_inner_x+0.1, P_XZplane_1, Thickness),))
        e1, d2 = p.edges, p.datums
        p.PartitionFaceBySketch(sketchUpEdge=e1.findAt(coordinates=(0.0, 0.1, Thickness)), faces=pickedFaces, sketchOrientation=LEFT,sketch=s)
        s.unsetPrimaryObject()
        del mdb.models['Model-1'].sketches['__profile__']
        p = mdb.models['Model-1'].parts['Specimen']
        c = p.cells
        pickedCells = c.findAt(((P_inner_x-0.1, P_XZplane_1, Thickness),), ((P_inner_x+0.1, P_XZplane_1, Thickness),))
        e = p.edges
        pickedEdges = (e.findAt(coordinates=(P_inner_x-0.1, P_XZplane_1, Thickness)), e.findAt(coordinates=(P_inner_x+0.1, P_XZplane_1, Thickness)))
        p.PartitionCellBySweepEdge(sweepPath=e.findAt(coordinates=(0.0, 0.0, 0.01)), cells=pickedCells, edges=pickedEdges)

    if Geometry == 20:
        p = mdb.models['Model-1'].parts['Specimen']
        f1, e, d2 = p.faces, p.edges, p.datums
        s = mdb.models['Model-1'].ConstrainedSketch(name='__profile__',
                                                    sheetSize=137.77, gridSpacing=3.44, transform=t)
        g, v, d, c = s.geometry, s.vertices, s.dimensions, s.constraints
        s.setPrimaryObject(option=SUPERIMPOSE)
        p = mdb.models['Model-1'].parts['Specimen']
        p.projectReferencesOntoSketch(sketch=s, filter=COPLANAR_EDGES)
        s.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(27.5, 39.7717802865893))
        p = mdb.models['Model-1'].parts['Specimen']
        f = p.faces
        pickedFaces = f.findAt(((P_inner_x+0.1, 12.6, Thickness),), ((0.1, 12.6, Thickness),))
        e1, d1 = p.edges, p.datums
        p.PartitionFaceBySketch(sketchUpEdge=e1.findAt(coordinates=(0.0, 0.1, Thickness)),
                                faces=pickedFaces, sketchOrientation=LEFT, sketch=s)
        s.unsetPrimaryObject()
        del mdb.models['Model-1'].sketches['__profile__']
        p = mdb.models['Model-1'].parts['Specimen']
        c = p.cells
        pickedCells = c.findAt(((P_inner_x+0.1, 12.6, Thickness),), ((0.1, 12.6, Thickness),))
        e, d2 = p.edges, p.datums
        #only works for W20
        pickedEdges = (e.findAt(coordinates=(102.E-06,48.35333,Thickness)), e.findAt(coordinates=(23.145248, 42.453999, Thickness)))
        p.PartitionCellByExtrudeEdge(line=e.findAt(coordinates=(0.0, 0.0, 0.01)),cells=pickedCells, edges=pickedEdges, sense=REVERSE)

    if Geometry == 50:
        p = mdb.models['Model-1'].parts['Specimen']
        f, e1, d1 = p.faces, p.edges, p.datums
        s1 = mdb.models['Model-1'].ConstrainedSketch(name='__profile__',
                                                     sheetSize=152.25, gridSpacing=3.8, transform=t)
        g, v, d, c = s1.geometry, s1.vertices, s1.dimensions, s1.constraints
        s1.setPrimaryObject(option=SUPERIMPOSE)
        p = mdb.models['Model-1'].parts['Specimen']
        p.projectReferencesOntoSketch(sketch=s1, filter=COPLANAR_EDGES)
        s1.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(42.5, 39.7717802865893))
        p = mdb.models['Model-1'].parts['Specimen']
        f = p.faces
        pickedFaces = f.findAt(((P_inner_x+0.1, 12.6, Thickness),), ((0.1, 12.6, Thickness),))
        e, d2 = p.edges, p.datums
        p.PartitionFaceBySketch(sketchUpEdge=e.findAt(coordinates=(0.0, 0.1, Thickness)),
                                faces=pickedFaces, sketchOrientation=LEFT, sketch=s1)
        s1.unsetPrimaryObject()
        del mdb.models['Model-1'].sketches['__profile__']
        p = mdb.models['Model-1'].parts['Specimen']
        c = p.cells
        pickedCells = c.findAt(((P_inner_x+0.1, 12.6, Thickness),), ((0.1, 12.6, Thickness),))
        e1, d1 = p.edges, p.datums
        pickedEdges = (e1.findAt(coordinates=(42.495014,39.777108, Thickness)), e1.findAt(coordinates=(5.46E-03,58.206911, Thickness)))
        p.PartitionCellByExtrudeEdge(line=e1.findAt(coordinates=(0.0, 0.0, 0.01)),
                                     cells=pickedCells, edges=pickedEdges, sense=REVERSE)

    if Geometry == 200:
        #Partitioning for the W200 Geometry
        p = mdb.models['Model-1'].parts['Specimen']
        f, e1, d1 = p.faces, p.edges, p.datums
        t = p.MakeSketchTransform(sketchPlane=f.findAt(coordinates=(46.429166, 3.32068, Thickness)),
                                  sketchUpEdge=e1.findAt(coordinates=(0.0, 17.5, Thickness)),
                                  sketchPlaneSide=SIDE1, sketchOrientation=LEFT, origin=(0.0, 0.0, Thickness))
        s = mdb.models['Model-1'].ConstrainedSketch(name='__profile__',
                                                    sheetSize=197.98, gridSpacing=4.94, transform=t)
        g, v, d, c = s.geometry, s.vertices, s.dimensions, s.constraints
        s.setPrimaryObject(option=SUPERIMPOSE)
        p = mdb.models['Model-1'].parts['Specimen']
        p.projectReferencesOntoSketch(sketch=s, filter=COPLANAR_EDGES)
        s.rectangle(point1=(0.0, 0.0), point2=(P_section1_y, P_section1_y))
        s.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(P_section2_r, 0.0))
        s.Line(point1=(P_section1_y, P_section1_y), point2=(70.0/(2**0.5), 70.0/(2**0.5)))
        s.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(P_section3_r, 0.0))
        p = mdb.models['Model-1'].parts['Specimen']
        f = p.faces
        pickedFaces = f.findAt(((46.429166, 3.32068, Thickness),))
        e, d2 = p.edges, p.datums
        p.PartitionFaceBySketch(sketchUpEdge=e.findAt(coordinates=(0.0, 17.5, Thickness)),
                                faces=pickedFaces, sketchOrientation=LEFT, sketch=s)
        s.unsetPrimaryObject()
        del mdb.models['Model-1'].sketches['__profile__']

        #1
        p = mdb.models['Model-1'].parts['Specimen']
        c = p.cells
        pickedCells = c.findAt(((0.1, 0.1, Thickness),))
        e, d1 = p.edges, p.datums
        pickedEdges = (e.findAt(coordinates=(0.1, P_section1_y, Thickness)),
                       e.findAt(coordinates=(P_section1_y, 0.1, Thickness)),)
        p.PartitionCellByExtrudeEdge(line=e.findAt(coordinates=(0.0, 0.0, 0.01)),
                                     cells=pickedCells, edges=pickedEdges, sense=REVERSE)

        #2
        p = mdb.models['Model-1'].parts['Specimen']
        c = p.cells
        pickedCells = c.findAt(((P_section1_y+0.1, P_section1_y+0.1, Thickness),))
        e, d1 = p.edges, p.datums
        pickedEdges = (e.findAt(coordinates=(0.1, P_section1_y, Thickness)),
                       e.findAt(coordinates=(P_section1_y, 0.1, Thickness)),
                       e.findAt(coordinates=(0.1, (P_section2_r ** 2 - (0.1) ** 2) ** 0.5, Thickness)),
                       e.findAt(coordinates=((P_section2_r ** 2 - (0.1) ** 2) ** 0.5, 0.1, Thickness)))
        p.PartitionCellByExtrudeEdge(line=e.findAt(coordinates=(0.0, 0.0, 0.01)),
                                     cells=pickedCells, edges=pickedEdges, sense=REVERSE)

        #3
        p = mdb.models['Model-1'].parts['Specimen']
        c = p.cells
        pickedCells = c.findAt(((P_section1_y+0.1, P_section1_y+0.1, Thickness),))
        e, d1 = p.edges, p.datums
        pickedEdges = (e.findAt(coordinates=(P_section1_y + 0.01, P_section1_y + 0.01, Thickness)))
        p.PartitionCellByExtrudeEdge(line=e.findAt(coordinates=(0.0, 0.0, 0.01)),
                                     cells=pickedCells, edges=pickedEdges, sense=REVERSE)

        #4
        p = mdb.models['Model-1'].parts['Specimen']
        c = p.cells
        pickedCells = c.findAt(((P_section3_r, 0.0, Thickness),))
        e, d1 = p.edges, p.datums
        pickedEdges = (e.findAt(coordinates=((P_section3_r ** 2 - (0.1) ** 2) ** 0.5, 0.1, Thickness)))
        p.PartitionCellByExtrudeEdge(line=e.findAt(coordinates=(0.0, 0.0, 0.01)),
                                     cells=pickedCells, edges=pickedEdges, sense=REVERSE)

        #5
        p = mdb.models['Model-1'].parts['Specimen']
        c = p.cells
        pickedCells = c.findAt(((0.0, P_section3_r, Thickness),))
        e, d1 = p.edges, p.datums
        pickedEdges = (e.findAt(coordinates=(0.1, (P_section3_r ** 2 - (0.1) ** 2) ** 0.5, Thickness)))
        p.PartitionCellByExtrudeEdge(line=e.findAt(coordinates=(0.0, 0.0, 0.01)),
                                     cells=pickedCells, edges=pickedEdges, sense=REVERSE)

        #6
        p = mdb.models['Model-1'].parts['Specimen']
        c = p.cells
        pickedCells = c.findAt(((P_section2_r/(2**0.5)+0.1, P_section2_r/(2**0.5)+0.1, Thickness),))
        e, d1 = p.edges, p.datums
        pickedEdges = (e.findAt(coordinates=(P_section2_r/(2**0.5)+0.01, P_section2_r/(2**0.5)+0.01, Thickness)))
        p.PartitionCellByExtrudeEdge(line=e.findAt(coordinates=(0.0, 0.0, 0.01)),
                                     cells=pickedCells, edges=pickedEdges, sense=REVERSE)

        #7
        p = mdb.models['Model-1'].parts['Specimen']
        c = p.cells
        pickedCells = c.findAt(((P_section3_r/(2**0.5)+0.1, P_section3_r/(2**0.5)+0.1, Thickness),))
        e, d1 = p.edges, p.datums
        pickedEdges = (e.findAt(coordinates=(P_section3_r/(2**0.5)+0.01, P_section3_r/(2**0.5)+0.01, Thickness)))
        p.PartitionCellByExtrudeEdge(line=e.findAt(coordinates=(0.0, 0.0, 0.01)),
                                     cells=pickedCells, edges=pickedEdges, sense=REVERSE)

def Mesh_control():
    if Geometry != 200:
        #Mesh Control---
        p = mdb.models['Model-1'].parts['Specimen']
        c = p.cells
        pickedCells = c.getByBoundingBox(
            xMin=-100.0, xMax=100.0,
            yMin=-100.0, yMax=100.0,
            zMin=-100.0, zMax=100.0
            )
        f1 = p.faces
        p.assignStackDirection(referenceRegion=f1.findAt(coordinates=(0.1, 0.0,
            0.01)), cells=pickedCells)
        p = mdb.models['Model-1'].parts['Specimen']
        c = p.cells
        pickedRegions = c.getByBoundingBox(
            xMin=-100.0, xMax=100.0,
            yMin=-100.0, yMax=100.0,
            zMin=-100.0, zMax=100.0
            )
        p.setMeshControls(regions=pickedRegions, technique=SWEEP,
            algorithm=ADVANCING_FRONT)
        #1
        p = mdb.models['Model-1'].parts['Specimen']
        c1, e1 = p.cells, p.edges
        p.setSweepPath(region=c1.findAt(coordinates=(0.1,0.1,0.0)),
            edge=e1.findAt(coordinates=(0.0, 0.1, 0.0)), sense=FORWARD)
        #2
        p = mdb.models['Model-1'].parts['Specimen']
        c2, e = p.cells, p.edges
        p.setSweepPath(region=c2.findAt(coordinates=(P_inner_x+0.1, 0.1, 0.0)),
            edge=e.findAt(coordinates=(P_inner_x, P_XZplane_1-0.1, 0.0)), sense=REVERSE)
        #3
        p = mdb.models['Model-1'].parts['Specimen']
        c1, e1 = p.cells, p.edges
        p.setSweepPath(region=c1.findAt(coordinates=(0.1, P_XZplane_1+0.1, 0.0)),
            edge=e1.findAt(coordinates=(0.0, P_XZplane_1+0.1, 0.0)), sense=FORWARD)
        #4
        p = mdb.models['Model-1'].parts['Specimen']
        c2, e = p.cells, p.edges
        p.setSweepPath(region=c2.findAt(coordinates=(P_inner_x+0.1, P_XZplane_1+0.1, 0.0)),
            edge=e.findAt(coordinates=(P_inner_x, P_XZplane_1+0.1, 0.0)), sense=REVERSE)
        #5
        p = mdb.models['Model-1'].parts['Specimen']
        c1, e1 = p.cells, p.edges
        p.setSweepPath(region=c1.findAt(coordinates=(0.1, 12.6, 0.0)),
            edge=e1.findAt(coordinates=(0.0, 12.6, 0.0)), sense=FORWARD)

        #6 Structured Mesh for curvature Part (6) (more robust)
        p = mdb.models['Model-1'].parts['Specimen']
        c = p.cells
        pickedRegions = c.findAt(((P_inner_x + 0.1, 12.6, 0.0),))
        p.setMeshControls(regions=pickedRegions, technique=STRUCTURED)

        if Geometry == 20:
            #6_1
            p = mdb.models['Model-1'].parts['Specimen']
            c1, e1 = p.cells, p.edges
            p.setSweepPath(region=c1.findAt(coordinates=(0.1, 48.35333, 0.0)),
                           edge=e1.findAt(coordinates=(0.0, 48.4, 0.0)), sense=FORWARD)
            #6_2
            p = mdb.models['Model-1'].parts['Specimen']
            c1, e1 = p.cells, p.edges
            p.setSweepPath(region=c1.findAt(coordinates=(27.4,39.9, 0.0)),
                           edge=e1.findAt(coordinates=(27.5,39.8, 0.0)), sense=REVERSE)
        if Geometry == 50:
            #6_1
            p = mdb.models['Model-1'].parts['Specimen']
            c1, e1 = p.cells, p.edges
            p.setSweepPath(region=c1.findAt(coordinates=(0.1, 58.3, 0.0)),
                           edge=e1.findAt(coordinates=(0.0, 58.3, 0.0)), sense=FORWARD)
            #6_2
            p = mdb.models['Model-1'].parts['Specimen']
            c1, e1 = p.cells, p.edges
            p.setSweepPath(region=c1.findAt(coordinates=(42.4,39.9, 0.0)),
                           edge=e1.findAt(coordinates=(42.5,39.9, 0.0)), sense=REVERSE)
        #7
        p = mdb.models['Model-1'].parts['Specimen']
        c1, e1 = p.cells, p.edges
        p.setSweepPath(region=c1.findAt(coordinates=(0.1, P_circle_r+0.1, 0.0)),
            edge=e1.findAt(coordinates=(0.0, P_circle_r+0.1, 0.0)), sense=FORWARD)
        #8
        p = mdb.models['Model-1'].parts['Specimen']
        c2, e = p.cells, p.edges
        #calculation
        # Circle intersection calculation---
        points = circle_intersections(r1, r2, x2, y2)
        if not points:
            raise ValueError("No valid intersection between circles")
        # Select TOP intersection (highest y)
        top_point = max(points, key=lambda p: p[1])
        # Separate parameters
        p_intersect_x_top = top_point[0]
        p_intersect_y_top = top_point[1]
        P_intersect_y_above = p_intersect_y_top+0.1
        P_intersect_x_above = P_inner_x+P_inner_r-(P_inner_r**2-(P_intersect_y_above-12.5)**2)**0.5
        p.setSweepPath(region=c2.findAt(coordinates=(p_intersect_x_top+0.1, p_intersect_y_top, 0.0)),
            edge=e.findAt(coordinates=(P_intersect_x_above, P_intersect_y_above, 0.0)), sense=REVERSE)

    if Geometry == 200:
        p = mdb.models['Model-1'].parts['Specimen']
        c = p.cells
        pickedRegions = c.getByBoundingBox(
                xMin=-100.0, xMax=100.0,
                yMin=-100.0, yMax=100.0,
                zMin=-100.0, zMax=100.0
            )
        p.setMeshControls(regions=pickedRegions, technique=STRUCTURED)

def Mesh_seed():
    #Seed Thickness
    p = mdb.models['Model-1'].parts['Specimen']
    e = p.edges
    pickedEdges = e.findAt(((0.0, 0.0, 0.01), ))
    p.seedEdgeByNumber(edges=pickedEdges, number=M_n_thickness, constraint=FIXED)
    # p = mdb.models['Model-1'].parts['Specimen']
    # e = p.edges
    # edges = e.findAt(((0.0, 0.0, 0.01), ))
    # p.Set(edges=edges, name='Edge Seeds-Thickness')

    if Geometry != 200:
        #Seed Section 1y
        p = mdb.models['Model-1'].parts['Specimen']
        e = p.edges
        pickedEdges = e.findAt(((0.0, 0.1, 0.0), ))
        p.seedEdgeByNumber(edges=pickedEdges, number=M_n_section1_y, constraint=FIXED)
        # p = mdb.models['Model-1'].parts['Specimen']
        # e = p.edges
        # edges = e.findAt(((0.0, 0.1, 0.0), ))
        # p.Set(edges=edges, name='Edge Seeds-Section1y')

        #Seed Section 2y
        p = mdb.models['Model-1'].parts['Specimen']
        e = p.edges
        pickedEdges = e.findAt(((0.0, P_XZplane_1+0.1, 0.0), ))
        p.seedEdgeByNumber(edges=pickedEdges, number=M_n_section2_y, constraint=FIXED)
        # p = mdb.models['Model-1'].parts['Specimen']
        # e = p.edges
        # edges = e.findAt(((0.0, P_XZplane_1+0.1, 0.0), ))
        # p.Set(edges=edges, name='Edge Seeds-Section2y')

        # Seed Section 3y
        p = mdb.models['Model-1'].parts['Specimen']
        e = p.edges
        pickedEdges = e.findAt(((0.0, 12.6, 0.0), ))
        p.seedEdgeByNumber(edges=pickedEdges, number=M_n_section3_y, constraint=FIXED)
        # p = mdb.models['Model-1'].parts['Specimen']
        # e = p.edges
        # edges = e.findAt(((0.0, 12.6, 0.0), ))
        # p.Set(edges=edges, name='Edge Seeds-Section3y')

        if Geometry == 20:
            # Seed Section 3_1y
            p = mdb.models['Model-1'].parts['Specimen']
            e = p.edges
            pickedEdges = e.findAt(((0.0, 48.36, 0.0),))
            p.seedEdgeByNumber(edges=pickedEdges, number=M_n_section3_1_y, constraint=FIXED)
            # p = mdb.models['Model-1'].parts['Specimen']
            # e = p.edges
            # edges = e.findAt(((0.0, 48.35, 0.0),))
            # p.Set(edges=edges, name='Edge Seeds-Section3_1y')

        if Geometry == 50:
            # Seed Section 3_1y
            p = mdb.models['Model-1'].parts['Specimen']
            e = p.edges
            pickedEdges = e.findAt(((0.0, 58.21, 0.0),))
            p.seedEdgeByNumber(edges=pickedEdges, number=M_n_section3_1_y, constraint=FIXED)
            # p = mdb.models['Model-1'].parts['Specimen']
            # e = p.edges
            # edges = e.findAt(((0.0, 58.21, 0.0),))
            # p.Set(edges=edges, name='Edge Seeds-Section3_1y')

        # Seed Section 4y
        p = mdb.models['Model-1'].parts['Specimen']
        e = p.edges
        pickedEdges = e.findAt(((0.0, P_circle_r+0.1, 0.0),))
        p.seedEdgeByNumber(edges=pickedEdges, number=M_n_section4_y, constraint=FIXED)
        # p = mdb.models['Model-1'].parts['Specimen']
        # e = p.edges
        # edges = e.findAt(((0.0, P_circle_r+0.1, 0.0),))
        # p.Set(edges=edges, name='Edge Seeds-Section4y')

        # Seed Section 1x
        p = mdb.models['Model-1'].parts['Specimen']
        e = p.edges
        pickedEdges = e.findAt(((0.1, 0.0, 0.0), ), ((0.1, 0.0, Thickness),))
        p.seedEdgeByNumber(edges=pickedEdges, number=M_n_section1_x, constraint=FIXED)
        # p = mdb.models['Model-1'].parts['Specimen']
        # e = p.edges
        # edges = e.findAt(((0.1, 0.0, 0.0), ))
        # p.Set(edges=edges, name='Edge Seeds-section1x')

        # Seed Section 2x
        p = mdb.models['Model-1'].parts['Specimen']
        e = p.edges
        pickedEdges = e.findAt(((P_inner_x+0.1, 0.0, 0.0),), ((P_inner_x+0.1, 0.0, Thickness),))
        p.seedEdgeByNumber(edges=pickedEdges, number=M_n_section2_x, constraint=FIXED)
        # p = mdb.models['Model-1'].parts['Specimen']
        # e = p.edges
        # edges = e.findAt(((P_inner_x+0.1, 0.0, 0.0),))
        # p.Set(edges=edges, name='Edge Seeds-section2x')

    if Geometry == 200:
        #Section 1
        p = mdb.models['Model-1'].parts['Specimen']
        e = p.edges
        pickedEdges = e.findAt(((0.1, 0.0, 0.0),), ((0.0, 0.1, 0.0),))
        p.seedEdgeByNumber(edges=pickedEdges, number=M_n_section1, constraint=FIXED)
        # p = mdb.models['Model-1'].parts['Specimen']
        # e = p.edges
        # edges = e.findAt(((0.1, 0.0, 0.0),), ((0.0, 0.1, 0.0),))
        # p.Set(edges=edges, name='Edge Seeds-Section1')

        #Section 2
        p = mdb.models['Model-1'].parts['Specimen']
        e = p.edges
        pickedEdges = e.findAt(((0.0, P_section1_y+0.1, 0.0),), ((P_section1_y+0.1, 0.0, 0.0),))
        p.seedEdgeByNumber(edges=pickedEdges, number=M_n_section2, constraint=FIXED)
        # p = mdb.models['Model-1'].parts['Specimen']
        # e = p.edges
        # edges = e.findAt(((0.0, P_section1_y+0.1, 0.0),), ((P_section1_y+0.1, 0.0, 0.0),))
        # p.Set(edges=edges, name='Edge Seeds-Section2')

        #Section 3
        p = mdb.models['Model-1'].parts['Specimen']
        e = p.edges
        pickedEdges = e.findAt(((P_section2_r+0.1, 0.0, 0.0),), ((0.0, P_section2_r+0.1, 0.0),))
        p.seedEdgeByNumber(edges=pickedEdges, number=M_n_section3, constraint=FIXED)
        # p = mdb.models['Model-1'].parts['Specimen']
        # e = p.edges
        # edges = e.findAt(((P_section2_r+0.1, 0.0, 0.0),), ((0.0, P_section2_r+0.1, 0.0),))
        # p.Set(edges=edges, name='Edge Seeds-Section3')

        #Section 4
        p = mdb.models['Model-1'].parts['Specimen']
        e = p.edges
        pickedEdges = e.findAt(((0.0, P_section3_r+0.1, 0.0),), ((P_section3_r+0.1, 0.0, 0.0),))
        p.seedEdgeByNumber(edges=pickedEdges, number=M_n_section4, constraint=FIXED)
        # p = mdb.models['Model-1'].parts['Specimen']
        # e = p.edges
        # edges = e.findAt(((0.0, P_section3_r+0.1, 0.0),), ((P_section3_r+0.1, 0.0, 0.0),))
        # p.Set(edges=edges, name='Edge Seeds-Section4')

    #Generate Mesh
    p = mdb.models['Model-1'].parts['Specimen']
    p.seedPart(size=0.5, deviationFactor=0.1, minSizeFactor=0.1)
    p = mdb.models['Model-1'].parts['Specimen']
    p.generateMesh()

    #Create Set for Output
    # p = mdb.models['Model-1'].parts['Specimen']
    # v = p.vertices
    # verts = v.findAt(((0.0, 0.0, Thickness),))
    # p.Set(vertices=verts, name='ELOUT_geo')

    p = mdb.models['Model-1'].parts['Specimen']
    e = p.elements
    elements = e[397:398]
    p.Set(elements=elements, name='ELOUT')

def Assembly():
    a = mdb.models['Model-1'].rootAssembly
    a.DatumCsysByDefault(CARTESIAN)
    p = mdb.models['Model-1'].parts['Specimen']
    a.Instance(name='Assembly_Specimen', part=p, dependent=ON)

def Punch():
    #Creation punch geometry (analytical)
    s1 = mdb.models['Model-1'].ConstrainedSketch(name='__profile__', sheetSize=200.0)
    g, v, d, c = s1.geometry, s1.vertices, s1.dimensions, s1.constraints
    s1.setPrimaryObject(option=STANDALONE)
    s1.ConstructionLine(point1=(0.0, -100.0), point2=(0.0, 100.0))
    s1.FixedConstraint(entity=g.findAt((0.0, 0.0)))
    s1.ArcByCenterEnds(center=(0.0, -50.0), point1=(0.0, 0.0), point2=(50.0, -50.0), direction=CLOCKWISE)
    p = mdb.models['Model-1'].Part(name='Punch', dimensionality=THREE_D, type=ANALYTIC_RIGID_SURFACE)
    p.AnalyticRigidSurfRevolve(sketch=s1)
    s1.unsetPrimaryObject()
    del mdb.models['Model-1'].sketches['__profile__']

    #rotate punch in assembly
    a = mdb.models['Model-1'].rootAssembly
    a.Instance(name='Assembly_PUNCH', part=p, dependent=ON)
    a.rotate(instanceList=('Assembly_PUNCH',), axisPoint=(0.0, 0.0, 0.0), axisDirection=(1.0, 0.0, 0.0), angle=90.0)

    #Assign surface
    p = mdb.models['Model-1'].parts['Punch']
    s = p.faces
    side2Faces = s.findAt(((0.0, 0.0, 0.0), ))
    p.Surface(side2Faces=side2Faces, name='SPunch')

    #Reference Point
    p = mdb.models['Model-1'].parts['Punch']
    v1, e, d1, n = p.vertices, p.edges, p.datums, p.nodes
    p.ReferencePoint(point=v1.findAt(coordinates=(50.0, -50.0, 0.0)))

def Die():
    #Create die geometry not translated for thickness (analytical)
    p1 = mdb.models['Model-1'].parts['Punch']
    s1 = mdb.models['Model-1'].ConstrainedSketch(name='__profile__',
        sheetSize=200.0)
    g, v, d, c = s1.geometry, s1.vertices, s1.dimensions, s1.constraints
    s1.setPrimaryObject(option=STANDALONE)
    s1.ConstructionLine(point1=(0.0, -100.0), point2=(0.0, 100.0))
    s1.FixedConstraint(entity=g.findAt((0.0, 0.0)))
    s1.ArcByCenterEnds(center=(70.0, 15.0), point1=(70.0, 0.0), point2=(55.0,
        15.0), direction=CLOCKWISE)
    p = mdb.models['Model-1'].Part(name='Die', dimensionality=THREE_D,
        type=ANALYTIC_RIGID_SURFACE)
    p = mdb.models['Model-1'].parts['Die']
    p.AnalyticRigidSurfRevolve(sketch=s1)
    s1.unsetPrimaryObject()
    p = mdb.models['Model-1'].parts['Die']
    del mdb.models['Model-1'].sketches['__profile__']

    #Assign surface
    p = mdb.models['Model-1'].parts['Die']
    s = p.faces
    side2Faces = s.findAt(((70.0, 0.0, 0.0), ))
    p.Surface(side2Faces=side2Faces, name='SDie')
    a = mdb.models['Model-1'].rootAssembly
    p = mdb.models['Model-1'].parts['Die']
    a.Instance(name='Assembly_Die', part=p, dependent=ON)
    a.rotate(instanceList=('Assembly_Die', ), axisPoint=(0.0, 0.0, 0.0),
        axisDirection=(1.0, 0.0, 0.0), angle=90.0)
    a.translate(instanceList=('Assembly_Die', ), vector=(0.0, 0.0, Thickness))

    #Reference point
    p = mdb.models['Model-1'].parts['Die']
    v2, e1, d2, n1 = p.vertices, p.edges, p.datums, p.nodes
    p.ReferencePoint(point=v2.findAt(coordinates=(70.0, 0.0, 0.0)))

def Job_creation():
    #Job name is taken from the Geometry parameter and is adjusted so 200 => W20 and 20 => W02 for example
    mdb.Job(name="W" + "{:02d}".format(Geometry // 10), model='Model-1', description='', type=ANALYSIS,
        atTime=None, waitMinutes=0, waitHours=0, queue=None, memory=90,
        memoryUnits=PERCENTAGE, getMemoryFromAnalysis=True,
        explicitPrecision=SINGLE, nodalOutputPrecision=SINGLE, echoPrint=OFF,
        modelPrint=OFF, contactPrint=OFF, historyPrint=OFF, userSubroutine='',
        scratch='', resultsFormat=ODB, numDomains=1,
        activateLoadBalancing=False, numThreadsPerMpiProcess=1,
        multiprocessingMode=DEFAULT, numCpus=1, numGPUs=0)



Specimen_Geometry()
Partitioning()
Mesh_control()
Mesh_seed()
Assembly()
# Punch()
# Die()
Job_creation()


session.viewports['Viewport: 1'].enableRefresh()
# p = mdb.models['Model-1'].parts['Die']
# session.viewports['Viewport: 1'].setValues(displayedObject=p)
a = mdb.models['Model-1'].rootAssembly
session.viewports['Viewport: 1'].setValues(displayedObject=a)
session.viewports['Viewport: 1'].view.setValues(session.views['Iso'])