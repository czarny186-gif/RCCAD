"""Visible native tests of the HTML contracts, including animation evidence."""
import os,sys,unittest
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt,QPoint,QCoreApplication
QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
from PySide6.QtTest import QTest
from PySide6.QtGui import QFont
from PIL import Image
import test_classic_ui as base
from rccad import interaction as g

class VisibleClassicTests(base.ClassicUiTests):
    def setUp(self):
        self.app.setFont(QFont('Segoe UI',10));super().setUp();self.w.show();QTest.qWait(100)
        self.assertTrue(self.w.view.context() and self.w.view.context().isValid())
    def test_animation_and_preview_recording(self):
        folder=Path(sys.argv[1] if len(sys.argv)>1 else '/tmp/rccad-classic');folder.mkdir(parents=True,exist_ok=True)
        frames=[]
        def capture(name=None):
            path=folder/(name or f'frame_{len(frames):02d}.png');self.w.grab().save(str(path));frames.append(Image.open(path).convert('RGB').copy())
        QTest.mouseClick(self.s.buttons['sketch'],Qt.LeftButton);self.assertTrue(self.w.view.plane_mode)
        capture('RCCAD_04_plaszczyzny.png')
        self.assertEqual(self.s.buttons['sketch'].pulse.state(),self.s.buttons['sketch'].pulse.State.Running)
        self.s.select_plane('XY')
        for _ in range(6):QTest.qWait(50);capture()
        self.s.choose_shape('circle');self.click_world((0,0,0))
        for radius in [2,4,6,8,10,12]:
            xy=self.w.view.project_points(np.array([g.world_point(self.s.frame,(radius,0))]))[0][0]
            QTest.mouseMove(self.w.view,QPoint(round(xy[0]),round(xy[1])),30);QTest.qWait(50);capture()
        QTest.keyClick(self.w.view,Qt.Key_Tab);self.s.exact_u.setValue(24);capture('RCCAD_04_wymiary.png')
        QTest.keyClick(self.s.exact_u,Qt.Key_Return);self.wait()
        self.s.begin_extrude();self.s.direction.setCurrentIndex(self.s.direction.findData('two'));self.s.second.setValue(3);self.wait();capture('RCCAD_04_wyciagniecie.png')
        for depth in [4,6,8,10,12]:self.s.depth.setValue(depth);self.wait();QTest.qWait(40);capture()
        self.s.apply_extrude();self.wait();self.s.close_tool();QTest.qWait(400);capture('RCCAD_04_bryla.png')
        self.s.notify('Podgląd oblicza OpenCascade. Model zapisuje dopiero Zastosuj.')
        for _ in range(4):QTest.qWait(50);capture()
        frames[0].save(folder/'RCCAD_04_animacje.gif',save_all=True,append_images=frames[1:],duration=100,loop=0,optimize=True)
        self.assertFalse(self.unexpected)

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(VisibleClassicTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
