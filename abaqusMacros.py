# -*- coding: mbcs -*-
# Do not delete the following import lines
from abaqus import *
from abaqusConstants import *
import __main__

def Macro1():
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
    pass


def Macro2():
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
    pass


def Macro3():
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
    s = mdb.models['Model-1'].ConstrainedSketch(name='__profile__', sheetSize=50.0)
    g, v, d, c = s.geometry, s.vertices, s.dimensions, s.constraints
    s.setPrimaryObject(option=STANDALONE)
    s.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(4.0, 2.25))
    s.RadialDimension(curve=g[2], textPoint=(7.63561248779297, 3.49449634552002), 
        radius=13.25)
    session.viewports['Viewport: 1'].view.setValues(nearPlane=44.1752, 
        farPlane=50.1057, width=85.082, height=46.5281, cameraPosition=(
        15.9849, 12.9109, 47.1405), cameraTarget=(15.9849, 12.9109, 0))
    session.viewports['Viewport: 1'].view.setValues(cameraPosition=(3.84073, 
        5.59516, 47.1405), cameraTarget=(3.84073, 5.59516, 0))
    p = mdb.models['Model-1'].Part(name='Part-1', dimensionality=THREE_D, 
        type=DEFORMABLE_BODY)
    p = mdb.models['Model-1'].parts['Part-1']
    p.BaseShellExtrude(sketch=s, depth=120.0)
    s.unsetPrimaryObject()
    p = mdb.models['Model-1'].parts['Part-1']
    session.viewports['Viewport: 1'].setValues(displayedObject=p)
    del mdb.models['Model-1'].sketches['__profile__']
    session.viewports['Viewport: 1'].view.setValues(nearPlane=197.219, 
        farPlane=305.645, width=138.742, height=75.8727, cameraPosition=(
        144.809, 143.226, 207.459), cameraTarget=(-0.35556, -1.93866, 62.2942))
    session.viewports['Viewport: 1'].partDisplay.setValues(mesh=ON)
    session.viewports['Viewport: 1'].partDisplay.meshOptions.setValues(
        meshTechnique=ON)
    session.viewports['Viewport: 1'].partDisplay.geometryOptions.setValues(
        referenceRepresentation=OFF)
    p = mdb.models['Model-1'].parts['Part-1']
    p.seedPart(size=2.0, deviationFactor=0.1, minSizeFactor=0.1)
    p = mdb.models['Model-1'].parts['Part-1']
    p.seedPart(size=1.0, deviationFactor=0.1, minSizeFactor=0.1)
    p = mdb.models['Model-1'].parts['Part-1']
    p.generateMesh()


def Macro4():
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
    session.viewports['Viewport: 1'].view.setValues(nearPlane=221.341, 
        farPlane=330.971, width=136.905, height=82.6596, viewOffsetX=9.95346, 
        viewOffsetY=2.88144)
    session.viewports['Viewport: 1'].partDisplay.setValues(mesh=OFF)
    session.viewports['Viewport: 1'].partDisplay.meshOptions.setValues(
        meshTechnique=OFF)
    session.viewports['Viewport: 1'].partDisplay.geometryOptions.setValues(
        referenceRepresentation=ON)
    a = mdb.models['Model-1'].rootAssembly
    session.viewports['Viewport: 1'].setValues(displayedObject=a)
    session.viewports['Viewport: 1'].assemblyDisplay.setValues(mesh=OFF)
    session.viewports['Viewport: 1'].assemblyDisplay.meshOptions.setValues(
        meshTechnique=OFF)
    p = mdb.models['Model-1'].parts['Part-1']
    session.viewports['Viewport: 1'].setValues(displayedObject=p)
    session.viewports['Viewport: 1'].view.setValues(nearPlane=222.52, 
        farPlane=329.791, width=92.2585, height=55.4829, viewOffsetX=12.2419, 
        viewOffsetY=6.08095)
    p = mdb.models['Model-1'].parts['Part-1']
    v = p.vertices
    p.WirePolyLine(points=((v[0], v[1]), ), mergeType=IMPRINT, meshable=ON)
    p = mdb.models['Model-1'].parts['Part-1']
    e = p.edges
    edges = e.getSequenceFromMask(mask=('[#2 ]', ), )
    p.Set(edges=edges, name='Wire-1-Set-1')
    session.viewports['Viewport: 1'].partDisplay.setValues(mesh=ON)
    session.viewports['Viewport: 1'].partDisplay.meshOptions.setValues(
        meshTechnique=ON)
    session.viewports['Viewport: 1'].partDisplay.geometryOptions.setValues(
        referenceRepresentation=OFF)
    session.viewports['Viewport: 1'].view.setValues(nearPlane=222.257, 
        farPlane=330.054, width=98.4326, height=59.431, viewOffsetX=8.13565, 
        viewOffsetY=-11.7748)
    p = mdb.models['Model-1'].parts['Part-1']
    e = p.edges
    pickedEdges = e.getSequenceFromMask(mask=('[#1 ]', ), )
    p.seedEdgeBySize(edges=pickedEdges, size=0.4, deviationFactor=0.1, 
        minSizeFactor=0.1, constraint=FINER)
    p = mdb.models['Model-1'].parts['Part-1']
    e = p.edges
    pickedEdges = e.getSequenceFromMask(mask=('[#2 ]', ), )
    p.seedEdgeBySize(edges=pickedEdges, size=0.6, deviationFactor=0.1, 
        minSizeFactor=0.1, constraint=FINER)
    p = mdb.models['Model-1'].parts['Part-1']
    p.generateMesh()


def Macro5():
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
    session.viewports['Viewport: 1'].view.setValues(nearPlane=223.422, 
        farPlane=328.89, width=69.7289, height=42.4167, viewOffsetX=12.6985, 
        viewOffsetY=2.80205)
    p = mdb.models['Model-1'].parts['Part-1']
    v = p.vertices
    p.WirePolyLine(points=((v[0], v[1]), ), mergeType=IMPRINT, meshable=ON)
    p = mdb.models['Model-1'].parts['Part-1']
    e = p.edges
    edges = e.getSequenceFromMask(mask=('[#2 ]', ), )
    p.Set(edges=edges, name='Wire-1-Set-1')
    session.viewports['Viewport: 1'].view.setValues(nearPlane=220.73, 
        farPlane=331.582, width=154.618, height=94.0553, viewOffsetX=39.3517, 
        viewOffsetY=4.4408)
    session.viewports['Viewport: 1'].partDisplay.setValues(mesh=ON)
    session.viewports['Viewport: 1'].partDisplay.meshOptions.setValues(
        meshTechnique=ON)
    session.viewports['Viewport: 1'].partDisplay.geometryOptions.setValues(
        referenceRepresentation=OFF)
    p = mdb.models['Model-1'].parts['Part-1']
    e = p.edges
    pickedEdges = e.getSequenceFromMask(mask=('[#1 ]', ), )
    p.seedEdgeBySize(edges=pickedEdges, size=0.4, deviationFactor=0.1, 
        minSizeFactor=0.1, constraint=FINER)
    p = mdb.models['Model-1'].parts['Part-1']
    e = p.edges
    pickedEdges = e.getSequenceFromMask(mask=('[#2 ]', ), )
    p.seedEdgeBySize(edges=pickedEdges, size=0.6, deviationFactor=0.1, 
        minSizeFactor=0.1, constraint=FINER)
    p = mdb.models['Model-1'].parts['Part-1']
    p.generateMesh()


def Macro6():
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
    p = mdb.models['Model-1'].parts['Part-1']
    p.generateMesh()


def Macro7():
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
    p = mdb.models['Model-1'].parts['Part-1']
    e = p.edges
    pickedEdges = e.getSequenceFromMask(mask=('[#1 ]', ), )
    p.seedEdgeBySize(edges=pickedEdges, size=0.4, deviationFactor=0.1, 
        minSizeFactor=0.1, constraint=FINER)
    p = mdb.models['Model-1'].parts['Part-1']
    e = p.edges
    pickedEdges = e.getSequenceFromMask(mask=('[#2 ]', ), )
    p.seedEdgeBySize(edges=pickedEdges, size=0.6, deviationFactor=0.1, 
        minSizeFactor=0.1, constraint=FINER)
    p = mdb.models['Model-1'].parts['Part-1']
    p.generateMesh()


def Macro8():
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
    p = mdb.models['Model-1'].parts['Part-1']
    e = p.edges
    pickedEdges = e.getSequenceFromMask(mask=('[#1 ]', ), )
    p.seedEdgeBySize(edges=pickedEdges, size=0.4, deviationFactor=0.1, 
        constraint=FINER)
    p = mdb.models['Model-1'].parts['Part-1']
    e = p.edges
    pickedEdges = e.getSequenceFromMask(mask=('[#2 ]', ), )
    p.seedEdgeBySize(edges=pickedEdges, size=0.6, deviationFactor=0.1, 
        constraint=FINER)
    p = mdb.models['Model-1'].parts['Part-1']
    p.generateMesh()


def Macro9():
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
    p = mdb.models['Model-1'].parts['Part-1']
    v1 = p.vertices
    p.WirePolyLine(points=((v1[0], v1[1]), ), mergeType=IMPRINT, meshable=ON)
    p = mdb.models['Model-1'].parts['Part-1']
    e = p.edges
    edges = e.getSequenceFromMask(mask=('[#2 ]', ), )
    p.Set(edges=edges, name='Wire-1-Set-1')
    session.viewports['Viewport: 1'].partDisplay.setValues(mesh=ON)
    session.viewports['Viewport: 1'].partDisplay.meshOptions.setValues(
        meshTechnique=ON)
    session.viewports['Viewport: 1'].partDisplay.geometryOptions.setValues(
        referenceRepresentation=OFF)
    p = mdb.models['Model-1'].parts['Part-1']
    e = p.edges
    pickedEdges = e.getSequenceFromMask(mask=('[#1 ]', ), )
    p.seedEdgeBySize(edges=pickedEdges, size=0.4, deviationFactor=0.1, 
        constraint=FINER)
    p = mdb.models['Model-1'].parts['Part-1']
    e = p.edges
    pickedEdges = e.getSequenceFromMask(mask=('[#2 ]', ), )
    p.seedEdgeBySize(edges=pickedEdges, size=0.6, deviationFactor=0.1, 
        constraint=FINER)
    p = mdb.models['Model-1'].parts['Part-1']
    p.generateMesh()
    p = mdb.models['Model-1'].parts['Part-1']
    p.generateMesh()


def Macro10():
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
    p = mdb.models['Model-1'].parts['Part-1']
    v = p.vertices
    p.WirePolyLine(points=((v[0], v[1]), ), mergeType=IMPRINT, meshable=ON)
    p = mdb.models['Model-1'].parts['Part-1']
    e = p.edges
    edges = e.getSequenceFromMask(mask=('[#2 ]', ), )
    p.Set(edges=edges, name='Wire-1-Set-1')
    session.viewports['Viewport: 1'].partDisplay.setValues(mesh=ON)
    session.viewports['Viewport: 1'].partDisplay.meshOptions.setValues(
        meshTechnique=ON)
    session.viewports['Viewport: 1'].partDisplay.geometryOptions.setValues(
        referenceRepresentation=OFF)
    p = mdb.models['Model-1'].parts['Part-1']
    e = p.edges
    pickedEdges = e.getSequenceFromMask(mask=('[#1 ]', ), )
    p.seedEdgeBySize(edges=pickedEdges, size=0.4, deviationFactor=0.1, 
        minSizeFactor=0.1, constraint=FINER)
    p = mdb.models['Model-1'].parts['Part-1']
    e = p.edges
    pickedEdges = e.getSequenceFromMask(mask=('[#2 ]', ), )
    p.seedEdgeBySize(edges=pickedEdges, size=0.6, deviationFactor=0.1, 
        minSizeFactor=0.1, constraint=FINER)
    p = mdb.models['Model-1'].parts['Part-1']
    p.generateMesh()


def nt6():
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
    s1 = mdb.models['Model-1'].ConstrainedSketch(name='__profile__', 
        sheetSize=200.0)
    g, v, d, c = s1.geometry, s1.vertices, s1.dimensions, s1.constraints
    s1.setPrimaryObject(option=STANDALONE)
    s1.Line(point1=(0.0, 0.0), point2=(0.0, 20.0))
    s1.VerticalConstraint(entity=g[2], addUndoState=False)
    s1.ObliqueDimension(vertex1=v[0], vertex2=v[1], textPoint=(-12.4758033752441, 
        8.35483932495117), value=15.0)
    s1.Line(point1=(0.0, 5.0), point2=(5.0, 5.0))
    s1.HorizontalConstraint(entity=g[3], addUndoState=False)
    s1.PerpendicularConstraint(entity1=g[2], entity2=g[3], addUndoState=False)
    s1.Line(point1=(0.0, 20.0), point2=(10.0, 20.0))
    s1.HorizontalConstraint(entity=g[4], addUndoState=False)
    s1.PerpendicularConstraint(entity1=g[2], entity2=g[4], addUndoState=False)
    s1.Line(point1=(10.0, 20.0), point2=(10.0, 15.0))
    s1.VerticalConstraint(entity=g[5], addUndoState=False)
    s1.PerpendicularConstraint(entity1=g[4], entity2=g[5], addUndoState=False)
    s1.ObliqueDimension(vertex1=v[1], vertex2=v[3], textPoint=(4.12096786499023, 
        24.6128997802734), value=10.0)
    s1.ObliqueDimension(vertex1=v[0], vertex2=v[2], textPoint=(2.31451797485352, 
        1.12903213500977), value=5.0)
    s1.ObliqueDimension(vertex1=v[3], vertex2=v[4], textPoint=(15.6370964050293, 
        17.0483856201172), value=15.0)
    s1.Line(point1=(5.0, 5.0), point2=(14.1693534851074, 5.0))
    s1.HorizontalConstraint(entity=g[6], addUndoState=False)
    s1.ParallelConstraint(entity1=g[3], entity2=g[6], addUndoState=False)
    s1.ObliqueDimension(vertex1=v[2], vertex2=v[5], textPoint=(9.65322494506836, 
        -1.91935348510742), value=6.67)
    s1.ArcByCenterEnds(center=(11.67, 5.0), point1=(5.0, 5.0), point2=(10.0, 
        11.7419357299805), direction=CLOCKWISE)
    s1.CoincidentConstraint(entity1=v[6], entity2=g[5], addUndoState=False)
    session.viewports['Viewport: 1'].view.setValues(nearPlane=186.515, 
        farPlane=190.609, width=51.0646, height=31.3156, cameraPosition=(
        4.36914, 2.88913, 188.562), cameraTarget=(4.36914, 2.88913, 0))
    s1.delete(objectList=(g[6], ))
    session.viewports['Viewport: 1'].view.setValues(nearPlane=186.515, 
        farPlane=190.609, width=51.0646, height=31.3156, cameraPosition=(
        3.73626, 2.85501, 188.562), cameraTarget=(3.73626, 2.85501, 0))
    s1.delete(objectList=(g[5], ))
    s1.Line(point1=(10.0, 20.0), point2=(10.0, 11.4575537163852))
    s1.VerticalConstraint(entity=g[8], addUndoState=False)
    s1.PerpendicularConstraint(entity1=g[4], entity2=g[8], addUndoState=False)
    session.viewports['Viewport: 1'].view.setValues(nearPlane=185.761, 
        farPlane=191.363, width=79.0675, height=50.209, cameraPosition=(11.005, 
        6.74167, 188.562), cameraTarget=(11.005, 6.74167, 0))
    p = mdb.models['Model-1'].Part(name='Part-1', dimensionality=THREE_D, 
        type=DEFORMABLE_BODY)
    p = mdb.models['Model-1'].parts['Part-1']
    p.BaseSolidExtrude(sketch=s1, depth=1.0)
    s1.unsetPrimaryObject()
    p = mdb.models['Model-1'].parts['Part-1']
    session.viewports['Viewport: 1'].setValues(displayedObject=p)
    del mdb.models['Model-1'].sketches['__profile__']


def Import():
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
    session.viewports['Viewport: 1'].view.setValues(nearPlane=144.557, 
        farPlane=232.216, width=69.8116, height=33.283, viewOffsetX=-4.0242, 
        viewOffsetY=-20.4299)
    session.viewports['Viewport: 1'].partDisplay.setValues(mesh=OFF)
    mdb.openAuxMdb(pathName='Y:/Semester_Project/W50.cae')
    mdb.copyAuxMdbModel(fromName='Model-1', toName='Model-1')
    mdb.closeAuxMdb()
    mdb.models['Model-1'].rootAssembly.unlock()
    p1 = mdb.models['Model-1'].parts['Part-1']
    session.viewports['Viewport: 1'].setValues(displayedObject=p1)
    p = mdb.models['Model-1'].Part(name='Part-1-failed', 
        objectToCopy=mdb.models['Model-1'].parts['Part-1'])
    mdb.models['Model-1'].parts['Part-1-failed'].Unlock(reportWarnings=False)
    del mdb.models['Model-1'].parts['Part-1']
    mdb.models['Model-1'].parts.changeKey(fromName='Part-1-failed', 
        toName='Part-1')
    import assembly
    mdb.models['Model-1'].rootAssembly.regenerate()
    p1 = mdb.models['Model-1'].parts['Part-1']
    session.viewports['Viewport: 1'].setValues(displayedObject=p1)
    p = mdb.models['Model-1'].parts['Part-1']
    session.viewports['Viewport: 1'].setValues(displayedObject=p)
    p = mdb.models['Model-1'].parts['Part-1']
    p.features['Solid extrude-1'].setValues(depth=1.0)
    p = mdb.models['Model-1'].parts['Part-1']
    p.regenerate()
    session.viewports['Viewport: 1'].partDisplay.setValues(mesh=ON)
    session.viewports['Viewport: 1'].partDisplay.meshOptions.setValues(
        meshTechnique=ON)
    session.viewports['Viewport: 1'].partDisplay.geometryOptions.setValues(
        referenceRepresentation=OFF)
    p = mdb.models['Model-1'].parts['Part-1']
    p.generateMesh()
    p1 = mdb.models['Model-1'].parts['Part-1']
    session.viewports['Viewport: 1'].setValues(displayedObject=p1)
    session.viewports['Viewport: 1'].view.setValues(nearPlane=124.932, 
        farPlane=186.842, width=2.04657, height=0.978391, viewOffsetX=-11.0078, 
        viewOffsetY=-12.1541)
    p = mdb.models['Model-1'].parts['Part-1']
    e = p.elements
    elements = e.getSequenceFromMask(mask=('[#0:269 #c000 ]', ), )
    p.Set(elements=elements, name='ELOUT')


