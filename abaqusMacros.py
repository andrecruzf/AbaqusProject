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
