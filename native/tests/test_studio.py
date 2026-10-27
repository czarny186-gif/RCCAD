"""Mouse-driven HTML-style workspace using native Qt and exact CAD."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen' if not os.environ.get('DISPLAY') and os.name!='nt' else '')
import time
import unittest
from unittest.mock import patch
import numpy as np
from PySide6.QtCore import Qt,QPoint,QAbstractAnimation
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox
from rccad.window import MainWindow
from rccad.document import Body
from rccad import kernel as k,interaction as g

class StudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.w=MainWindow();self.w.resize(1380,900);self.w.layout().activate();self.s=self.w.studio
        self.w.view.resize(1380,820)
        self.unexpected=[];self.exception_hook=patch('sys.excepthook',side_effect=lambda kind,value,tb:self.unexpected.append(str(value)));self.exception_hook.start()
        self.warn=patch.object(QMessageBox,'warning',return_value=QMessageBox.Ok);self.warning=self.warn.start()
        self.info=patch.object(QMessageBox,'information',return_value=QMessageBox.Ok);self.info.start()
    def wait(self):
        end=time.monotonic()+15
        while (self.w.busy or self.s.preview_running or self.s.preview_timer.isActive() or self.s.auto_blend_timer.isActive() or self.s.trim_timer.isActive() or self.w.view.camera_animation.state()==QAbstractAnimation.State.Running) and time.monotonic()<end:
            self.app.processEvents();QTest.qWait(5)
        self.app.processEvents();self.assertFalse(self.w.busy);self.assertFalse(self.s.preview_running)
    def tearDown(self):
        self.s.preview_timer.stop();self.s.auto_blend_timer.stop();self.s.trim_timer.stop();self.s.generation+=1;self.wait();self.w.pool.waitForDone(5000)
        self.w.document._saved_revision=self.w.document._revision;self.w.close();self.app.processEvents();self.warn.stop();self.info.stop();self.exception_hook.stop();self.assertFalse(self.unexpected)
    def click_world(self,point):
        self.wait()
        xy=self.w.view.project_points(np.array([point]))[0][0]
        QTest.mouseClick(self.w.view,Qt.LeftButton,Qt.NoModifier,QPoint(round(xy[0]),round(xy[1])))
    def draw(self,kind,points):
        self.s.shape.setCurrentIndex(self.s.shape.findData(kind))
        for p in points:self.click_world(g.world_point(self.s.frame,p))
        if kind=='polyline':self.s.finish_polyline()
        self.wait()
    def test_draw_extrude_face_sketch_cut_undo(self):
        self.s.begin_sketch();self.s.select_plane('XY');self.draw('rectangle',[(0,0),(30,30)])
        sketch=self.w.document.bodies[-1];self.assertEqual(sketch.kind,'sketch')
        self.assertTrue(sketch.shape.IsClosed())
        self.s.close_tool();self.s.begin_extrude();self.s.depth.setValue(20);self.wait()
        self.assertTrue(self.w.view.preview_items)
        self.s.apply_extrude();self.wait()
        solid=next(b for b in self.w.document.bodies if b.kind=='solid')
        self.assertAlmostEqual(solid.shape.Volume(),18000,places=3)
        self.assertFalse(self.w.document.get(sketch.id).visible)
        self.s.begin_sketch();self.s.select_plane('XY');self.s.choose_face();self.w.view.fit_all();self.click_world((15,15,20))
        self.assertEqual(self.s.support,solid.id)
        self.draw('circle',[(0,0),(3,0)])
        profile=self.w.document.bodies[-1];self.assertEqual(profile.support_id,solid.id)
        self.s.begin_extrude();self.s.operation.setCurrentIndex(self.s.operation.findData('subtract'));self.s.depth.setValue(40);self.wait()
        self.assertEqual(self.s.target.currentData(),solid.id)
        self.s.apply_extrude();self.wait()
        cut=self.w.document.get(solid.id)
        self.assertAlmostEqual(cut.shape.Volume(),18000-180*np.pi,delta=1)
        self.assertTrue(cut.shape.isValid());self.assertEqual(self.warning.call_count,0)
        self.w.undo();self.assertAlmostEqual(self.w.document.get(solid.id).shape.Volume(),18000,places=4)
        self.assertTrue(self.w.document.get(profile.id).visible)
        self.w.redo();self.assertLess(self.w.document.get(solid.id).shape.Volume(),18000)
    def test_pick_profile_interior_and_close_cancel(self):
        self.s.begin_sketch();self.s.select_plane('XY');self.draw('circle',[(0,0),(10,0)])
        body=self.w.document.bodies[-1];self.s.begin_extrude()
        self.w.clear_selection();self.click_world((0,0,0))
        self.assertEqual(self.w.selected,[body.id]);self.wait()
        self.s.close_tool();self.assertFalse(self.w.view.preview_items);self.assertFalse(self.w.view.sketch_mode)
        self.s.begin_sketch();self.s.select_plane('XY');self.click_world((0,0,0));self.assertEqual(len(self.s.points),1)
        QTest.keyClick(self.w.view,Qt.Key_Escape);self.assertEqual(self.s.points,[])
        QTest.keyClick(self.w.view,Qt.Key_Escape);self.assertIsNone(self.s.mode)
    def test_all_closed_graphical_tools_and_polyline(self):
        self.s.begin_sketch();self.s.select_plane('XY')
        examples=[('center_rectangle',[(0,0),(8,6)]),('ellipse',[(0,0),(8,6)]),('polygon',[(0,0),(8,0)]),('slot',[(0,0),(10,0),(5,2)]),('polyline',[(0,0),(10,0),(10,10),(0,10)])]
        for kind,pts in examples:
            self.draw(kind,pts);self.assertTrue(self.w.document.bodies[-1].shape.IsClosed(),kind)
        self.assertEqual(len(self.w.document.bodies),5);self.assertEqual(self.warning.call_count,0)
    def test_preview_never_changes_document_and_late_preview_is_ignored(self):
        self.s.begin_sketch();self.s.select_plane('XY');self.draw('rectangle',[(0,0),(10,10)])
        before=self.w.document._revision;self.s.begin_extrude();self.s.depth.setValue(12);self.wait()
        self.assertEqual(self.w.document._revision,before);self.assertEqual(len(self.w.document.bodies),1)
        self.s.depth.setValue(17);self.s.preview_extrusion();self.s.close_tool();self.wait()
        self.assertFalse(self.w.view.preview_items);self.assertIsNone(self.w.view.handle)
    def test_bad_cut_and_open_line_do_not_change_history(self):
        self.s.begin_sketch();self.s.select_plane('XY');self.draw('line',[(0,0),(10,0)])
        revision=self.w.document._revision;self.s.begin_extrude();self.s.apply_extrude();self.wait()
        self.assertEqual(self.w.document._revision,revision);self.assertIn('pozostał bez zmian',self.s.last_notice)
    def test_dimensioned_profile_from_clicked_anchor(self):
        self.s.begin_sketch();self.s.select_plane('XY');self.click_world((0,0,0));self.s.exact_u.setValue(12);self.s.exact_v.setValue(8);self.s.dimensioned_profile();self.wait()
        shape=self.w.document.bodies[-1].shape;b=k.bounds(shape)
        self.assertAlmostEqual(b.xlen,12,places=5);self.assertAlmostEqual(b.ylen,8,places=5)

    def test_graphical_edge_panel_fillet_and_chamfer_apply(self):
        from PySide6.QtWidgets import QPushButton
        for mode in ['fillet','chamfer']:
            body=Body('Kostka',k.box(30,30,30)).prepared();self.w.document.commit([body]);self.w.selected=[body.id];self.w.refresh(True)
            self.s.begin_blend();self.w.blend_type.setCurrentIndex(self.w.blend_type.findData(mode));self.w.edge_clicked(body.id,0,False)
            self.assertIsNotNone(self.w.view.handle)
            self.w.blend_size.setValue(2)
            revision=self.w.document._revision
            self.s.preview_blend();self.wait()
            self.assertEqual(self.w.document._revision,revision)
            self.assertIsNotNone(self.w.view.preview_replacement)
            self.assertLess(self.w.view.preview_replacement[1].size,100)
            button=next(b for b in self.w.blend_panel.findChildren(QPushButton) if b.text()=='Zastosuj')
            QTest.mouseClick(button,Qt.LeftButton);self.wait()
            result=self.w.document.get(body.id).shape
            self.assertTrue(result.isValid());self.assertLess(result.Volume(),27000)
            self.s.close_tool()
        self.assertEqual(self.warning.call_count,0)
