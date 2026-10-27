"""Actual displayed native workspace, mouse drawing and handles (requires OpenGL)."""
import sys
import unittest
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt,QPoint,QCoreApplication
QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
from PySide6.QtTest import QTest
from test_studio import StudioTests

class DisplayedStudioTests(StudioTests):
    def setUp(self):
        super().setUp();self.w.show();QTest.qWait(100)
        assert self.w.view.context() and self.w.view.context().isValid()

    def drag_handle(self,delta):
        point,normal,kind=self.w.view.handle
        xy=self.w.view.project_points(np.array([point,point+normal*delta]))[0]
        a,b=[QPoint(round(q[0]),round(q[1])) for q in xy]
        if (a-b).manhattanLength()<3:b=a+QPoint(0,-40)
        QTest.mousePress(self.w.view,Qt.LeftButton,Qt.NoModifier,a)
        QTest.mouseMove(self.w.view,b,40)
        QTest.mouseRelease(self.w.view,Qt.LeftButton,Qt.NoModifier,b)
        self.wait()

    def test_extrude_and_transform_handles_and_snapshot(self):
        self.s.begin_sketch();self.s.select_plane('XY');self.draw('rectangle',[(0,0),(30,20)])
        self.s.begin_extrude();self.wait();self.assertIsNotNone(self.w.view.handle)
        before=self.s.depth.value();self.drag_handle(8)
        self.assertGreater(self.s.depth.value(),before+5)
        revision=self.w.document._revision;self.assertEqual(len(self.w.document.bodies),1)
        self.s.apply_extrude();self.wait();solid=next(b for b in self.w.document.bodies if b.kind=='solid')
        self.s.begin_transform();self.wait();self.assertIsNotNone(self.w.view.handle)
        self.drag_handle(6);self.assertGreater(self.s.move_fields[0].value(),4)
        self.assertAlmostEqual(self.w.document.get(solid.id).shape.Center().x,15,places=4)
        self.s.apply_transform();self.wait()
        self.assertGreater(self.w.document.get(solid.id).shape.Center().x,19)
        self.s.begin_blend()
        body=self.w.document.get(solid.id)
        for index,points in body.mesh.edges.items():
            xy=self.w.view.project_points(points)[0];mid=(xy[0]+xy[-1])/2
            hit=self.w.view.nearest_edge(*mid)
            if hit:
                QTest.mouseClick(self.w.view,Qt.LeftButton,Qt.NoModifier,QPoint(round(mid[0]),round(mid[1])));break
        self.assertTrue(self.w.edges);self.assertIsNotNone(self.w.view.handle)
        old=self.w.blend_size.value();self.drag_handle(1)
        self.assertGreater(self.w.blend_size.value(),old+.3)
        folder=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/tmp')
        folder.mkdir(parents=True,exist_ok=True)
        self.w.grab().save(str(folder/'RCCAD_Studio_krawedzie.png'))
        self.s.begin_sketch();self.s.select_plane('XY');self.s.choose_face();self.w.view.fit_all()
        top=max(body.shape.Faces(),key=lambda f:f.Center().z)
        self.click_world(top.Center().toTuple())
        self.assertEqual(self.s.support,body.id)
        self.s.shape.setCurrentIndex(self.s.shape.findData('circle'))
        self.click_world(self.s.frame[0]);self.s.sketch_move(self.w.view.width()*.62,self.w.view.height()*.5)
        self.w.grab().save(str(folder/'RCCAD_Studio_szkic.png'))
        self.s.cancel_points();self.s.close_tool()

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(DisplayedStudioTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
