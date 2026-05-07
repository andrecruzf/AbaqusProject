# -*- coding: utf-8 -*-
# Do not delete the following import lines
from abaqus import *
from abaqusConstants import *
import __main__

def Movie():
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
    session.linkedViewportCommands.setValues(_highlightLinkedViewports=True)
    leaf = dgo.LeafFromConstraintNames(name=("RigidBody_DIE-1        1", 
        "RigidBody_MATRIX-1        1", "RigidBody_PUNCH-1        1", ), 
        type=RIGID_BODY)
    dg = session.DisplayGroup(leaf=leaf, name='Rigid Bodies')
    leaf = dgo.LeafFromSurfaceSets(surfaceSets=("SPECIMEN-1.ZMAX", 
        "SPECIMEN-1.ZMIN", ))
    dg = session.DisplayGroup(leaf=leaf, name='Specimen')
    dg1= session.displayGroups['Rigid Bodies']
    session.viewports['Viewport: 1'].odbDisplay.setValues(visibleDisplayGroups=(
        dg1, ))
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        DEFORMED, ))
    session.viewports['Viewport: 1'].odbDisplay.commonOptions.setValues(
        translucency=ON, translucencyFactor=0.15)
    session.viewports['Viewport: 1'].odbDisplay.displayGroupInstances['Rigid Bodies'].setValues(
        lockOptions=ON)
    dg1= session.displayGroups['Specimen']
    dg2= session.displayGroups['Rigid Bodies']
    session.viewports['Viewport: 1'].odbDisplay.setValues(visibleDisplayGroups=(
        dg1, dg2, ))
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        CONTOURS_ON_DEF, ))
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        UNDEFORMED, ))
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        CONTOURS_ON_DEF, ))
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        DEFORMED, ))
    session.viewports['Viewport: 1'].odbDisplay.commonOptions.setValues(
        renderStyle=FILLED, visibleEdges=NONE)
    session.viewports['Viewport: 1'].odbDisplay.commonOptions.setValues(
        translucency=OFF)
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        CONTOURS_ON_DEF, ))
    session.viewports['Viewport: 1'].odbDisplay.setPrimaryVariable(
        variableLabel='SDV1', outputPosition=INTEGRATION_POINT, )
    session.viewports['Viewport: 1'].odbDisplay.basicOptions.setValues(
        mirrorAboutXzPlane=True, mirrorAboutYzPlane=True)
    session.viewports['Viewport: 1'].odbDisplay.displayGroupInstances['Specimen'].setValues(
        lockOptions=ON)
    session.viewports['Viewport: 1'].animationController.setValues(
        animationType=SCALE_FACTOR)
    session.viewports['Viewport: 1'].animationController.play(
        duration=UNLIMITED)
    session.viewports['Viewport: 1'].animationController.setValues(
        animationType=NONE)


def Movie_PiP():
    import displayGroupOdbToolset as dgo
    session.linkedViewportCommands.setValues(_highlightLinkedViewports=True)
    leaf = dgo.LeafFromConstraintNames(name=("RigidBody_DIE-1        1",
        "RigidBody_MATRIX-1        1", "RigidBody_PUNCH1-1        1",
        "RigidBody_PUNCH2-1        1", ),
        type=RIGID_BODY)
    dg = session.DisplayGroup(leaf=leaf, name='Rigid Bodies')
    leaf = dgo.LeafFromSurfaceSets(surfaceSets=("SPECIMEN-1.ZMAX",
        "SPECIMEN-1.ZMIN", ))
    dg = session.DisplayGroup(leaf=leaf, name='Specimen')
    dg1= session.displayGroups['Rigid Bodies']
    session.viewports['Viewport: 1'].odbDisplay.setValues(visibleDisplayGroups=(
        dg1, ))
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        DEFORMED, ))
    session.viewports['Viewport: 1'].odbDisplay.commonOptions.setValues(
        translucency=ON, translucencyFactor=0.15)
    session.viewports['Viewport: 1'].odbDisplay.displayGroupInstances['Rigid Bodies'].setValues(
        lockOptions=ON)
    dg1= session.displayGroups['Specimen']
    dg2= session.displayGroups['Rigid Bodies']
    session.viewports['Viewport: 1'].odbDisplay.setValues(visibleDisplayGroups=(
        dg1, dg2, ))
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        CONTOURS_ON_DEF, ))
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        UNDEFORMED, ))
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        CONTOURS_ON_DEF, ))
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        DEFORMED, ))
    session.viewports['Viewport: 1'].odbDisplay.commonOptions.setValues(
        renderStyle=FILLED, visibleEdges=NONE)
    session.viewports['Viewport: 1'].odbDisplay.commonOptions.setValues(
        translucency=OFF)
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        CONTOURS_ON_DEF, ))
    session.viewports['Viewport: 1'].odbDisplay.setPrimaryVariable(
        variableLabel='SDV1', outputPosition=INTEGRATION_POINT, )
    session.viewports['Viewport: 1'].odbDisplay.basicOptions.setValues(
        mirrorAboutXzPlane=True, mirrorAboutYzPlane=True)
    session.viewports['Viewport: 1'].odbDisplay.displayGroupInstances['Specimen'].setValues(
        lockOptions=ON)
    session.viewports['Viewport: 1'].animationController.setValues(
        animationType=SCALE_FACTOR)
    session.viewports['Viewport: 1'].animationController.play(
        duration=UNLIMITED)
    session.viewports['Viewport: 1'].animationController.setValues(
        animationType=NONE)
def Post_Pro_movie():
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
    session.linkedViewportCommands.setValues(_highlightLinkedViewports=True)
    leaf = dgo.LeafFromSurfaceSets(surfaceSets=("SPECIMEN-1.ZMAX",
        "SPECIMEN-1.ZMIN", ))
    dg = session.DisplayGroup(leaf=leaf, name='OpaqueSpecimen')
    leaf = dgo.LeafFromSurfaceSets(surfaceSets=("DIE-1.ASSEMBLY_DIE-1_OUTER",
        "DIE-1.OUTER", "MATRIX-1.ASSEMBLY_MATRIX-1_OUTER", "MATRIX-1.OUTER",
        "PUNCH-1.ASSEMBLY_PUNCH-1_OUTER", "PUNCH-1.OUTER", ))
    dg = session.DisplayGroup(leaf=leaf, name='Translucent')
    leaf = dgo.LeafFromConstraintNames(name=("RigidBody_DIE-1        1",
        "RigidBody_MATRIX-1        1", "RigidBody_PUNCH-1        1", ),
        type=RIGID_BODY)
    dg = session.DisplayGroup(leaf=leaf, name='RigidBodies')
    dg1= session.displayGroups['RigidBodies']
    session.viewports['Viewport: 1'].odbDisplay.setValues(visibleDisplayGroups=(
        dg1, ))
    session.viewports['Viewport: 1'].odbDisplay.commonOptions.setValues(
        visibleEdges=FEATURE)
    session.viewports['Viewport: 1'].odbDisplay.commonOptions.setValues(
        visibleEdges=FREE)
    session.viewports['Viewport: 1'].odbDisplay.commonOptions.setValues(
        translucency=ON, translucencyFactor=0.15)
    dg1= session.displayGroups['OpaqueSpecimen']
    session.viewports['Viewport: 1'].odbDisplay.setValues(visibleDisplayGroups=(
        dg1, ))
    dg1= session.displayGroups['RigidBodies']
    session.viewports['Viewport: 1'].odbDisplay.setValues(visibleDisplayGroups=(
        dg1, ))
    dg1= session.displayGroups['OpaqueSpecimen']
    dg2= session.displayGroups['RigidBodies']
    session.viewports['Viewport: 1'].odbDisplay.setValues(visibleDisplayGroups=(
        dg1, dg2, ))
    session.viewports['Viewport: 1'].odbDisplay.displayGroupInstances['RigidBodies'].setValues(
        lockOptions=ON)
    session.viewports['Viewport: 1'].odbDisplay.displayGroupInstances.syncOptions(
        name='OpaqueSpecimen', updateInstances=OFF)
    session.viewports['Viewport: 1'].odbDisplay.commonOptions.setValues(
        renderStyle=FILLED)
    dg1= session.displayGroups['OpaqueSpecimen']
    session.viewports['Viewport: 1'].odbDisplay.setValues(visibleDisplayGroups=(
        dg1, ))
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        CONTOURS_ON_DEF, ))
    session.viewports['Viewport: 1'].odbDisplay.basicOptions.setValues(
        mirrorAboutXzPlane=True, mirrorAboutYzPlane=True)
    dg1= session.displayGroups['OpaqueSpecimen']
    session.viewports['Viewport: 1'].odbDisplay.setValues(visibleDisplayGroups=(
        dg1, ))
    dg1= session.displayGroups['OpaqueSpecimen']
    session.viewports['Viewport: 1'].odbDisplay.setValues(visibleDisplayGroups=(
        dg1, ))
    dg1= session.displayGroups['OpaqueSpecimen']
    session.viewports['Viewport: 1'].odbDisplay.setValues(visibleDisplayGroups=(
        dg1, ))
    dg1= session.displayGroups['Translucent']
    session.viewports['Viewport: 1'].odbDisplay.setValues(visibleDisplayGroups=(
        dg1, ))
    dg1= session.displayGroups['OpaqueSpecimen']
    session.viewports['Viewport: 1'].odbDisplay.setValues(visibleDisplayGroups=(
        dg1, ))
    session.viewports['Viewport: 1'].odbDisplay.commonOptions.setValues(
        translucency=OFF)
    dg1= session.displayGroups['Translucent']
    dg2= session.displayGroups['OpaqueSpecimen']
    session.viewports['Viewport: 1'].odbDisplay.setValues(visibleDisplayGroups=(
        dg1, dg2, ))
    dg1= session.displayGroups['RigidBodies']
    dg2= session.displayGroups['Translucent']
    dg3= session.displayGroups['OpaqueSpecimen']
    session.viewports['Viewport: 1'].odbDisplay.setValues(visibleDisplayGroups=(
        dg1, dg2, dg3, ))
    session.viewports['Viewport: 1'].odbDisplay.displayGroupInstances['OpaqueSpecimen'].setValues(
        lockOptions=ON)
    session.viewports['Viewport: 1'].odbDisplay.displayGroupInstances['Translucent'].setValues(
        lockOptions=ON)
    session.viewports['Viewport: 1'].animationController.setValues(
        animationType=SCALE_FACTOR)
    session.viewports['Viewport: 1'].animationController.play(
        duration=UNLIMITED)
    session.viewports['Viewport: 1'].animationController.setValues(
        animationType=NONE)
    session.viewports['Viewport: 1'].odbDisplay.setPrimaryVariable(
        variableLabel='SDV1', outputPosition=INTEGRATION_POINT, )
    session.viewports['Viewport: 1'].animationController.setValues(
        animationType=SCALE_FACTOR)
    session.viewports['Viewport: 1'].animationController.play(
        duration=UNLIMITED)
    session.viewports['Viewport: 1'].animationController.setValues(
        animationType=NONE)


def Post_pro():
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
    session.viewports['Viewport: 1'].view.setValues(nearPlane=368.829,
        farPlane=690.781, width=339.647, height=168.699, viewOffsetX=20.9549,
        viewOffsetY=8.51964)
    session.linkedViewportCommands.setValues(_highlightLinkedViewports=True)
    leaf = dgo.LeafFromConstraintNames(name=("RigidBody_DIE-1        1",
        "RigidBody_MATRIX-1        1", "RigidBody_PUNCH-1        1", ),
        type=RIGID_BODY)
    dg = session.DisplayGroup(leaf=leaf, name='Rigid_Bodies')
    leaf = dgo.LeafFromSurfaceSets(surfaceSets=("SPECIMEN-1.ZMAX",
        "SPECIMEN-1.ZMIN", ))
    dg = session.DisplayGroup(leaf=leaf, name='specimenSurfaces')
    dg1= session.displayGroups['Rigid_Bodies']
    session.viewports['Viewport: 1'].odbDisplay.setValues(visibleDisplayGroups=(
        dg1, ))
    session.viewports['Viewport: 1'].odbDisplay.displayGroupInstances['Rigid_Bodies'].setValues(
        lockOptions=ON)
    dg1= session.displayGroups['specimenSurfaces']
    session.viewports['Viewport: 1'].odbDisplay.setValues(visibleDisplayGroups=(
        dg1, ))
    session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
        CONTOURS_ON_DEF, ))
    session.viewports['Viewport: 1'].odbDisplay.commonOptions.setValues(
        translucency=OFF)
    dg1= session.displayGroups['Rigid_Bodies']
    dg2= session.displayGroups['specimenSurfaces']
    session.viewports['Viewport: 1'].odbDisplay.setValues(visibleDisplayGroups=(
        dg1, dg2, ))
    session.viewports['Viewport: 1'].odbDisplay.displayGroupInstances['specimenSurfaces'].setValues(
        lockOptions=ON)
    session.viewports['Viewport: 1'].animationController.setValues(
        animationType=SCALE_FACTOR)
    session.viewports['Viewport: 1'].animationController.play(
        duration=UNLIMITED)
    session.viewports['Viewport: 1'].animationController.setValues(
        animationType=NONE)


