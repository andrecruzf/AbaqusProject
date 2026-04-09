# -*- coding: mbcs -*-
# Do not delete the following import lines
from abaqus import *
from abaqusConstants import *
import __main__

def Open():
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
    openMdb(pathName='Y:/Semester_Project/Base/geometries/W50.cae')
    session.viewports['Viewport: 1'].setValues(displayedObject=None)
    upgradeMdb("Y:/Semester_Project/Base/geometries/W50-6.14-1.cae", 
        "Y:/Semester_Project/Base/geometries/W50.cae", )
    session.viewports['Viewport: 1'].setValues(displayedObject=None)
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
    p = mdb.models['Model-1'].parts['Part-1']
    p.regenerate()
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
    session.viewports['Viewport: 1'].view.setValues(nearPlane=120.383, 
        farPlane=191.392, width=46.2803, height=22.1249, viewOffsetX=-7.12544, 
        viewOffsetY=-6.86714)
    session.viewports['Viewport: 1'].view.setValues(nearPlane=120.647, 
        farPlane=191.127, width=46.382, height=22.1735, viewOffsetX=-7.4276, 
        viewOffsetY=-7.58312)
    session.viewports['Viewport: 1'].view.setValues(nearPlane=142.99, 
        farPlane=180.792, width=54.9716, height=26.2799, cameraPosition=(
        121.704, 33.4699, 127.567), cameraUpVector=(-0.433411, 0.899576, 
        -0.0540168), cameraTarget=(23.7066, 36.7714, 6.24902), 
        viewOffsetX=-8.80314, viewOffsetY=-8.98746)
    session.viewports['Viewport: 1'].view.setValues(nearPlane=139.922, 
        farPlane=191.927, width=53.7923, height=25.7161, cameraPosition=(
        82.397, -21.1003, 146.155), cameraUpVector=(-0.799038, 0.549794, 
        0.243444), cameraTarget=(16.1951, 34.7117, 16.4059), 
        viewOffsetX=-8.61428, viewOffsetY=-8.79465)
    session.viewports['Viewport: 1'].view.setValues(nearPlane=144.925, 
        farPlane=186.924, width=2.85835, height=1.36647, viewOffsetX=-33.0759, 
        viewOffsetY=-11.5288)
    p1 = mdb.models['Model-1'].parts['Part-1']
    session.viewports['Viewport: 1'].setValues(displayedObject=p1)
    session.viewports['Viewport: 1'].view.setValues(nearPlane=158.286, 
        farPlane=218.713, width=3.12187, height=1.49245, cameraPosition=(
        35.453, -122.237, 110.762), cameraUpVector=(-0.711852, 0.542647, 
        0.445871), cameraTarget=(17.2124, 12.4907, 34.2879), 
        viewOffsetX=-36.1253, viewOffsetY=-12.5916)
    session.viewports['Viewport: 1'].view.setValues(nearPlane=158.261, 
        farPlane=218.739, width=3.12137, height=1.49221, viewOffsetX=-36.1195, 
        viewOffsetY=-12.5896)
    p = mdb.models['Model-1'].parts['Part-1']
    e = p.elements
    elements = e.getSequenceFromMask(mask=('[#0:269 #8000 ]', ), )
    p.Set(elements=elements, name='ELOUT')


