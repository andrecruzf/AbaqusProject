# -*- coding: mbcs -*-
# Do not delete the following import lines
from abaqus import *
from abaqusConstants import *
import __main__
import visualization
import xyPlot
import displayGroupOdbToolset as dgo
o1 = session.openOdb(
    name='D:/engsen/Nakazima_Abaqus/W12_v3/nakazima.odb',
    readOnly=False)
session.viewports['Viewport: 1'].setValues(displayedObject=o1)
session.viewports['Viewport: 1'].odbDisplay.display.setValues(plotState=(
    CONTOURS_ON_DEF, ))
session.viewports['Viewport: 1'].view.setProjection(projection=PARALLEL)
session.viewports['Viewport: 1'].view.setValues(session.views['Front'])
session.viewports['Viewport: 1'].odbDisplay.commonOptions.setValues(
    visibleEdges=FEATURE)
session.viewports['Viewport: 1'].odbDisplay.setFrame(step=0, frame=41 )
session.viewports['Viewport: 1'].odbDisplay.setPrimaryVariable(
    variableLabel='SDV_EQPS', outputPosition=INTEGRATION_POINT, )
session.viewports['Viewport: 1'].view.setValues(nearPlane=396.447, 
    farPlane=493.176, width=57.2603, height=39.2972, cameraPosition=(
    0.616447, 0.818273, 486.136), cameraTarget=(0.616447, 0.818273, 
    41.325))
session.viewports['Viewport: 1'].view.setValues(nearPlane=389.385, 
        farPlane=500.415, cameraPosition=(-1.71102, 51.0389, 483.286), 
        cameraUpVector=(-0.030164, 0.993136, -0.11301), cameraTarget=(0.616447, 
        0.818268, 41.325))
session.viewports['Viewport: 1'].view.setValues(session.views['Front'])
session.viewports['Viewport: 1'].view.setValues(nearPlane=336.617, 
        farPlane=553.005, cameraPosition=(-46.7038, -280.152, 383.657), 
        cameraUpVector=(0.0490697, 0.769665, 0.63656), cameraTarget=(
        2.67029e-005, 2.86102e-005, 41.325))
session.viewports['Viewport: 1'].view.setValues(session.views['Front'])
session.viewports['Viewport: 1'].view.setValues(nearPlane=395.541, 
        farPlane=494.082, width=90.0106, height=50.3327, cameraPosition=(
        -27.824, 23.9132, 486.136), cameraTarget=(-27.824, 23.9132, 41.325))
session.viewports['Viewport: 1'].view.setValues(nearPlane=393.112, 
        farPlane=495.274, cameraPosition=(-29.0003, 11.0437, 485.949), 
        cameraUpVector=(0.000289846, 0.999581, 0.0289332), cameraTarget=(
        -27.824, 23.9132, 41.325))
session.viewports['Viewport: 1'].view.setValues(session.views['Front'])
session.viewports['Viewport: 1'].view.setValues(nearPlane=395.541, 
        farPlane=494.082, width=90.0106, height=50.3327, cameraPosition=(
        -27.8974, 22.8879, 486.136), cameraTarget=(-27.8974, 22.8879, 41.325))
session.viewports['Viewport: 1'].view.setValues(cameraPosition=(-28.0031, 
        24.7404, 486.136), cameraTarget=(-28.0031, 24.7404, 41.325))
session.viewports['Viewport: 1'].view.setValues(cameraPosition=(-28.0031, 
        24.3699, 486.136), cameraTarget=(-28.0031, 24.3699, 41.325))
session.viewports['Viewport: 1'].view.setValues(cameraPosition=(-15.5666, 
        13.7106, 486.136), cameraTarget=(-15.5666, 13.7106, 41.325))
session.viewports['Viewport: 1'].view.setValues(nearPlane=409.866, 
    farPlane=448.924, width=74.7614, height=48.6682, cameraPosition=(
    -16.37, 13.039, 486.136), cameraTarget=(-16.37, 13.039, 41.325))
session.viewports['Viewport: 1'].view.setValues(cameraPosition=(-20.1541, 
    13.602, 486.136), cameraTarget=(-20.1541, 13.602, 41.325))
session.viewports['Viewport: 1'].view.setValues(nearPlane=409.866, 
    farPlane=448.924, width=66.0591, height=43.0033, cameraPosition=(
    -18.8089, 11.7226, 486.136), cameraTarget=(-18.8089, 11.7226, 41.325))
session.viewports['Viewport: 1'].view.setValues(cameraPosition=(-20.7518, 
    14.8879, 486.136), cameraTarget=(-20.7518, 14.8879, 41.325))
session.viewports['Viewport: 1'].view.setValues(nearPlane=410.656, 
    farPlane=448.134, width=58.3699, height=37.9977, cameraPosition=(
    -18.4061, 12.7378, 486.136), cameraTarget=(-18.4061, 12.7378, 41.325))
session.viewports['Viewport: 1'].view.setValues(cameraPosition=(-20.4023, 
    13.5369, 486.136), cameraTarget=(-20.4023, 13.5369, 41.325))
session.viewports['Viewport: 1'].view.setValues(nearPlane=405.518, 
    farPlane=453.272, width=122.646, height=79.8405, cameraPosition=(
    -27.8539, 23.0307, 486.136), cameraTarget=(-27.8539, 23.0307, 41.325))
session.viewports['Viewport: 1'].odbDisplay.basicOptions.setValues(
    mirrorAboutXzPlane=True, mirrorAboutYzPlane=True)
session.viewports['Viewport: 1'].view.setValues(nearPlane=402.333, 
    farPlane=456.458, width=139.371, height=90.7278, cameraPosition=(
    6.07084, 5.21813, 486.136), cameraTarget=(6.07084, 5.21813, 41.325))
session.viewports['Viewport: 1'].view.setValues(cameraPosition=(-1.74614, 
    3.40548, 486.136), cameraTarget=(-1.74614, 3.40548, 41.325))
session.viewports['Viewport: 1'].view.setValues(cameraPosition=(0.637092, 
    3.9779, 486.136), cameraTarget=(0.637092, 3.9779, 41.325))
session.viewports['Viewport: 1'].view.setValues(nearPlane=407.924, 
    farPlane=450.866, width=84.9562, height=55.3049, cameraPosition=(
    0.794806, 9.83454, 486.136), cameraTarget=(0.794806, 9.83454, 41.325))
session.viewports['Viewport: 1'].view.setValues(cameraPosition=(-1.99446, 
    5.24034, 486.136), cameraTarget=(-1.99446, 5.24034, 41.325))
session.viewports['Viewport: 1'].view.setValues(cameraPosition=(-2.40123, 
    4.42618, 486.136), cameraTarget=(-2.40123, 4.42618, 41.325))
session.viewports['Viewport: 1'].view.setValues(cameraPosition=(0.852901, 
    4.6588, 486.136), cameraTarget=(0.852901, 4.6588, 41.325))
session.viewports['Viewport: 1'].view.setValues(cameraPosition=(-0.832276, 
    4.6588, 486.136), cameraTarget=(-0.832276, 4.6588, 41.325))
session.viewports['Viewport: 1'].view.setValues(cameraPosition=(-0.657944, 
        0.529833, 486.136), cameraTarget=(-0.657944, 0.529833, 41.325))
session.viewports['Viewport: 1'].view.setValues(nearPlane=395.772, 
    farPlane=493.85, width=75.0673, height=48.8674, cameraPosition=(
    -0.551394, 0.453453, 486.136), cameraTarget=(-0.551394, 0.453453, 
    41.325))
session.viewports['Viewport: 1'].view.setValues(cameraPosition=(-0.500049, 
    -0.831179, 486.136), cameraTarget=(-0.500049, -0.831179, 41.325))
session.viewports['Viewport: 1'].view.setValues(cameraPosition=(-0.551395, 
    0.556224, 486.136), cameraTarget=(-0.551395, 0.556224, 41.325))
session.viewports['Viewport: 1'].view.setValues(cameraPosition=(-0.551395, 
    -0.317326, 486.136), cameraTarget=(-0.551395, -0.317326, 41.325))
session.viewports['Viewport: 1'].view.setValues(cameraPosition=(-0.551395, 
    0.145141, 486.136), cameraTarget=(-0.551395, 0.145141, 41.325))
session.printToFile(
    fileName='D:/engsen/Nakazima_Abaqus/W12_v3/W12v3', 
    format=PNG, canvasObjects=(session.viewports['Viewport: 1'], ))