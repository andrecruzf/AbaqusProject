# -*- coding: mbcs -*-
# Do not delete the following import lines
from abaqus import *
from abaqusConstants import *
import __main__
import visualization
import xyPlot
import displayGroupOdbToolset as dgo
odb = session.odbs['D:/engsen/Nakazima_Abaqus/W02_90/nakazima.odb']
xy0 = session.XYDataFromHistory(name='XYData-1', odb=odb, 
    outputVariableName='Equivalent Plastic Strain: SDV_EQPS PI: PART-1-1 Element 17800 Int Point 1 in ELSET ELOUT', 
    steps=('Step-1', ), )
c0 = session.Curve(xyData=xy0)
xy1 = session.XYDataFromHistory(name='XYData-2', odb=odb, 
    outputVariableName='Lode parameter: SDV_LODE PI: PART-1-1 Element 17800 Int Point 1 in ELSET ELOUT', 
    steps=('Step-1', ), )
c1 = session.Curve(xyData=xy1)
xy2 = session.XYDataFromHistory(name='XYData-3', odb=odb, 
    outputVariableName='Triaxiality: SDV_TRIAX PI: PART-1-1 Element 17800 Int Point 1 in ELSET ELOUT', 
    steps=('Step-1', ), )
c2 = session.Curve(xyData=xy2)
xy3 = session.XYDataFromHistory(name='LEP1', odb=odb, 
    outputVariableName='Principal logarithmic strains: LEP1 PI: PART-1-1 Element 17800 Int Point 1 in ELSET ELOUT', 
    steps=('Step-1', ), )
c3 = session.Curve(xyData=xy3)
xy4 = session.XYDataFromHistory(name='LEP2', odb=odb, 
    outputVariableName='Principal logarithmic strains: LEP2 PI: PART-1-1 Element 17800 Int Point 1 in ELSET ELOUT', 
    steps=('Step-1', ), )
c4 = session.Curve(xyData=xy4)
xy5 = session.XYDataFromHistory(name='LEP3', odb=odb, 
    outputVariableName='Principal logarithmic strains: LEP3 PI: PART-1-1 Element 17800 Int Point 1 in ELSET ELOUT', 
    steps=('Step-1', ), )
c5 = session.Curve(xyData=xy5)
xy6 = session.XYDataFromHistory(name='FORCE', odb=odb, 
    outputVariableName='Reaction force: RF3 PI: PART-1-1 Node 1000000 in NSET RP_PUNCH', 
    steps=('Step-1', ), )
c6 = session.Curve(xyData=xy6)
xyp = session.XYPlot('XYPlot-1')
chartName = xyp.charts.keys()[0]
chart = xyp.charts[chartName]
chart.setValues(curvesToPlot=(c0, c1, c2, c3, c4, c5, c6, ), )
session.viewports['Viewport: 1'].setValues(displayedObject=xyp)
odb = session.odbs['D:/engsen/Nakazima_Abaqus/W02_90/nakazima.odb']
xy1 = xyPlot.XYDataFromHistory(odb=odb, 
    outputVariableName='Equivalent Plastic Strain: SDV_EQPS PI: PART-1-1 Element 17800 Int Point 1 in ELSET ELOUT', 
    steps=('Step-1', ), suppressQuery=True)
c1 = session.Curve(xyData=xy1)
xy2 = xyPlot.XYDataFromHistory(odb=odb, 
    outputVariableName='Lode parameter: SDV_LODE PI: PART-1-1 Element 17800 Int Point 1 in ELSET ELOUT', 
    steps=('Step-1', ), suppressQuery=True)
c2 = session.Curve(xyData=xy2)
xy3 = xyPlot.XYDataFromHistory(odb=odb, 
    outputVariableName='Triaxiality: SDV_TRIAX PI: PART-1-1 Element 17800 Int Point 1 in ELSET ELOUT', 
    steps=('Step-1', ), suppressQuery=False)
c3 = session.Curve(xyData=xy3)
xy4 = xyPlot.XYDataFromHistory(odb=odb, 
    outputVariableName='Principal logarithmic strains: LEP1 PI: PART-1-1 Element 17800 Int Point 1 in ELSET ELOUT', 
    steps=('Step-1', ), suppressQuery=False)
c4 = session.Curve(xyData=xy4)
xy5 = xyPlot.XYDataFromHistory(odb=odb, 
    outputVariableName='Principal logarithmic strains: LEP2 PI: PART-1-1 Element 17800 Int Point 1 in ELSET ELOUT', 
    steps=('Step-1', ), suppressQuery=False)
c5 = session.Curve(xyData=xy5)
xy6 = xyPlot.XYDataFromHistory(odb=odb, 
    outputVariableName='Principal logarithmic strains: LEP3 PI: PART-1-1 Element 17800 Int Point 1 in ELSET ELOUT', 
    steps=('Step-1', ), suppressQuery=False)
c6 = session.Curve(xyData=xy6)
xy7 = xyPlot.XYDataFromHistory(odb=odb, 
    outputVariableName='Reaction force: RF3 PI: PART-1-1 Node 1000000 in NSET RP_PUNCH', 
    steps=('Step-1', ), suppressQuery=False)
c7 = session.Curve(xyData=xy7)
xyp = session.xyPlots['XYPlot-1']
chartName = xyp.charts.keys()[0]
chart = xyp.charts[chartName]
chart.setValues(curvesToPlot=(c1, c2, c3, c4, c5, c6, c7, ), )
x0 = session.xyDataObjects['XYData-1']
x1 = session.xyDataObjects['XYData-2']
x2 = session.xyDataObjects['XYData-3']
x3 = session.xyDataObjects['LEP1']
x4 = session.xyDataObjects['LEP2']
x5 = session.xyDataObjects['LEP3']
x6 = session.xyDataObjects['FORCE']
session.xyReportOptions.setValues(numDigits=8, numberFormat=SCIENTIFIC)
session.writeXYReport(fileName='17800.csv', appendMode=OFF, xyData=(x0, x1, 
    x2, x3, x4, x5, x6))