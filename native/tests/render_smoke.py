"""Run with an actual display/OpenGL driver; validates native rendering and picking."""
from pathlib import Path
import sys
from PySide6.QtCore import Qt,QPoint
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from rccad import kernel as k
from rccad.document import Body
from rccad.window import MainWindow

app=QApplication([])
window=MainWindow();window.resize(1380,900)
shape=k.hole(k.box(40,40,30),6,20,20)
shape=k.blend(shape,range(len(shape.Edges())),2)
window.document.commit([Body('Przykład — otwór i zaokrąglenia',shape).prepared()])
window.selected=[window.document.bodies[0].id]
window.refresh(True);window.show();QTest.qWait(700)
image=window.view.grabFramebuffer()
assert window.view.context() and window.view.context().isValid(), 'OpenGL context invalid'
assert not image.isNull(), 'Viewport did not render'
image_path=Path(sys.argv[1] if len(sys.argv)>1 else '/tmp/RCCAD-Desktop.png')
window.grab().save(str(image_path))
# Validate real mouse events against an unrounded box with pickable CAD edges.
body=Body('Test wyboru',k.box(30,30,30)).prepared();window.document.commit([body]);window.selected=[body.id];window.refresh(True);window.start_blend('fillet');QTest.qWait(100)
point=None
for index,points in body.mesh.edges.items():
    xy,_,_=window.view.project_points(points)
    mid=(xy[0]+xy[-1])/2
    hit=window.view.nearest_edge(*mid)
    if hit is not None:
        point=mid;break
assert point is not None,'No visible CAD edge can be picked'
QTest.mouseClick(window.view,Qt.LeftButton,Qt.NoModifier,QPoint(round(point[0]),round(point[1])))
assert sum(map(len,window.edges.values()))==1, 'Mouse click did not select one edge'
window.blend_size.setValue(2);window.apply_blend()
for _ in range(500):
    app.processEvents();QTest.qWait(10)
    if not window.busy:break
assert not window.busy and window.document.bodies[0].shape.Volume()<27000
assert window.document.bodies[0].shape.isValid()
window.document._saved_revision=window.document._revision
window.close();app.processEvents()
print('Native OpenGL render, CAD edge picking and apply: PASS',image_path)
