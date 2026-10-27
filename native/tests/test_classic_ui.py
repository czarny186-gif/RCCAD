"""Contracts copied from the HTML new-body workflow, tested through native inputs."""
import hashlib,json,re,tempfile
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from rccad import interaction as g,kernel as k
from rccad.document import Document
from rccad.artwork import ROOT,CATALOG,icon
import test_studio as base

class ClassicUiTests(base.StudioTests):
    # Run only the new contracts here; inherited legacy tests stay in test_studio.
    def test_click_plane_in_view_and_original_tool_graphics(self):
        self.s.begin_sketch();self.assertTrue(self.w.view.plane_mode);self.assertIsNone(self.s.frame)
        found=None
        for name in ['XY','XZ','YZ']:
            for uv in [(10,10),(20,10),(10,25),(25,25)]:
                world=g.world_point(g.frame_for(name),uv);xy=self.w.view.project_points(np.array([world]))[0][0]
                if self.w.view.pick_plane(*xy)==name:found=(name,xy);break
            if found:break
        self.assertIsNotNone(found);name,xy=found
        QTest.mouseClick(self.w.view,Qt.LeftButton,Qt.NoModifier,QPoint(round(xy[0]),round(xy[1])));self.wait()
        self.assertFalse(self.w.view.plane_mode);self.assertTrue(self.w.view.sketch_mode);self.assertEqual(self.s.frame,g.frame_for(name))
        for name,info in CATALOG['buttons'].items():self.assertFalse(icon(name).isNull(),name)
        for item in CATALOG['images']:self.assertEqual(hashlib.sha256((ROOT/item['file']).read_bytes()).hexdigest(),item['sha256'])
    def test_tab_dimensions_enter_and_edit_existing_without_recreating(self):
        self.s.begin_sketch();self.s.select_plane('XY');self.s.choose_shape('rectangle');self.click_world((0,0,0));self.s.hover=(10,8)
        QTest.keyClick(self.w.view,Qt.Key_Tab);self.assertTrue(self.s.dim_active)
        self.s.exact_u.setValue(24);self.s.exact_v.setValue(13)
        QTest.keyClick(self.s.exact_v,Qt.Key_Return);self.wait();body=self.w.document.bodies[-1]
        self.assertAlmostEqual(k.bounds(body.shape).xlen,24,places=5);self.assertAlmostEqual(k.bounds(body.shape).ylen,13,places=5)
        edge=body.shape.Edges()[0];point=edge.Center().toTuple();xy=self.w.view.project_points(np.array([point]))[0][0]
        self.s.edit_dimension_at(*xy);self.assertEqual(self.s.edit_id,body.id)
        self.s.exact_u.setValue(32);self.s.accept_inline();self.wait()
        self.assertEqual(len(self.w.document.bodies),1);self.assertEqual(self.w.document.bodies[0].id,body.id)
        self.assertAlmostEqual(k.bounds(self.w.document.bodies[0].shape).xlen,32,places=5)
        self.w.undo();self.assertAlmostEqual(k.bounds(self.w.document.bodies[0].shape).xlen,24,places=5)
    def test_three_point_figures_construction_and_closed_lines(self):
        self.s.begin_sketch();self.s.select_plane('XY')
        for kind,pts in [('rect3',[(0,0),(10,0),(0,5)]),('circle2',[(20,0),(30,0)]),('circle3',[(40,0),(45,5),(50,0)]),('point',[(60,0)]),('construction',[(0,0),(20,20)])]:
            self.draw(kind,pts)
        self.assertEqual(len(self.w.document.bodies),5)
        self.assertEqual(self.warning.call_count,0)
    def test_text_is_native_profile_and_extrudes(self):
        self.s.begin_sketch();self.s.select_plane('XY');self.s.choose_shape('text')
        self.s.text_value.setText('B');self.s.text_font.setCurrentIndex(self.s.text_font.findData('bold'));self.s.exact_u.setValue(10);self.s.accept_inline();self.click_world((0,0,0));self.wait()
        body=self.w.document.bodies[-1];self.assertEqual(body.sketch_data['type'],'text')
        self.assertEqual(len(body.shape.Faces()[0].innerWires()),2)
        self.s.text_font.setCurrentIndex(self.s.text_font.findData('sans'));point=body.shape.Edges()[0].Center().toTuple();xy=self.w.view.project_points(np.array([point]))[0][0];self.s.edit_dimension_at(*xy)
        self.assertEqual(self.s.text_font.currentData(),'bold');self.s.cancel_inline()
        self.s.begin_extrude();self.s.depth.setValue(4);self.s.apply_extrude();self.wait()
        self.assertTrue(any(b.kind=='solid' for b in self.w.document.bodies));self.assertEqual(self.warning.call_count,0)
    def test_multi_profile_two_sided_ui(self):
        self.s.begin_sketch();self.s.select_plane('XY');self.draw('rectangle',[(0,0),(10,10)]);a=self.w.document.bodies[-1]
        self.draw('circle',[(20,0),(22,0)]);b=self.w.document.bodies[-1]
        self.s.begin_extrude();self.wait();self.w.selected=[a.id,b.id];self.w.refresh()
        self.s.direction.setCurrentIndex(self.s.direction.findData('two'));self.s.depth.setValue(8);self.s.second.setValue(3);self.wait()
        self.s.apply_extrude();self.wait();solids=[b for b in self.w.document.bodies if b.kind=='solid']
        self.assertEqual(len(solids),2)
        for body in solids:self.assertAlmostEqual(k.bounds(body.shape).zmin,-3,places=5);self.assertAlmostEqual(k.bounds(body.shape).zmax,8,places=5)
    def test_separate_line_chain_becomes_extrudable(self):
        self.s.begin_sketch();self.s.select_plane('XY')
        for a,b in [((0,0),(10,0)),((10,0),(10,10)),((10,10),(0,10)),((0,10),(0,0))]:self.draw('line',[a,b])
        self.s.begin_extrude();self.wait();self.assertTrue(self.s.selected_profiles())
        self.s.depth.setValue(5);self.s.apply_extrude();self.wait()
        solids=[b for b in self.w.document.bodies if b.kind=='solid'];self.assertEqual(len(solids),1);self.assertAlmostEqual(solids[0].shape.Volume(),500,places=4)
    def test_scissors_and_undo_native_edge_intersection(self):
        self.s.begin_sketch();self.s.select_plane('XY');self.draw('line',[(-10,0),(10,0)]);base=self.w.document.bodies[-1]
        self.draw('line',[(-3,-5),(-3,5)]);self.draw('line',[(3,-5),(3,5)])
        self.s.choose_shape('trim');revision=self.w.document._revision
        xy=self.w.view.project_points(np.array([[0,0,0]]))[0][0];self.s.schedule_trim(*xy);self.wait()
        self.assertTrue(self.w.view.preview_items);self.assertEqual(self.w.document._revision,revision)
        self.click_world((0,0,0));self.wait()
        self.assertAlmostEqual(sum(e.Length() for e in self.w.document.get(base.id).shape.Edges()),14,places=4)
        self.w.undo();self.assertAlmostEqual(self.w.document.get(base.id).shape.Length(),20,places=4)

    def test_tangent_circle_mouse_contract(self):
        self.s.begin_sketch();self.s.select_plane('XY');self.draw('line',[(-10,0),(10,0)]);self.draw('line',[(0,-10),(0,10)])
        self.s.choose_shape('circleTangent2');self.click_world((-7,0,0));self.click_world((0,7,0));self.click_world((4,3,0));self.wait()
        body=self.w.document.bodies[-1];self.assertEqual(body.sketch_data['type'],'circle')
        self.assertAlmostEqual(g.extrusion(body,2).Volume(),2*np.pi*3.5**2,places=4)

    def test_snapping_to_segment_crossing(self):
        self.s.begin_sketch();self.s.select_plane('XY');self.draw('line',[(0,4),(10,4)]);self.draw('line',[(3,0),(3,10)])
        self.s.choose_shape('rectangle');point=g.world_point(self.s.frame,(3.2,4.1));xy=self.w.view.project_points(np.array([point]))[0][0]
        snapped=self.s.uv(*xy);self.assertTrue(np.allclose(snapped,(3,4)));self.assertIsNotNone(self.s.snap_target)

    def test_select_intersection_region_and_atomic_undo(self):
        self.s.begin_sketch();self.s.select_plane('XY');self.draw('circle',[(0,0),(5,0)]);self.draw('circle',[(5,0),(10,0)])
        original=self.w.document.bodies;self.s.begin_extrude();self.wait()
        self.assertEqual(len(self.s.live_regions),3);self.assertEqual(self.w.document.bodies,original)
        self.click_world((2.5,0,0));self.assertEqual(len(self.s.selected_profiles()),1)
        area=self.s.selected_profile().shape.Area();self.s.depth.setValue(3);self.s.apply_extrude();self.wait()
        solids=[b for b in self.w.document.bodies if b.kind=='solid'];self.assertEqual(len(solids),1);self.assertAlmostEqual(solids[0].shape.Volume(),area*3,places=5)
        self.w.undo();self.assertEqual(self.w.document.bodies,original)

    def test_mirror_click_object_then_face_and_join(self):
        from rccad.document import Body
        body=Body('Kostka',k.box(10,10,10)).prepared();self.w.document.commit([body]);self.w.selected=[body.id];self.w.refresh(True)
        self.s.begin_mirror();self.assertEqual(self.s.mirror_source,body.id)
        self.click_world((5,5,10));self.wait();self.assertIsNotNone(self.s.mirror_frame)
        QTest.keyClick(self.w,Qt.Key_Return);self.wait();self.assertEqual(len(self.w.document.bodies),2)
        self.w.undo();self.s.mirror_join.setChecked(True);self.s.apply_mirror();self.wait()
        self.assertEqual(len(self.w.document.bodies),1);self.assertAlmostEqual(self.w.document.bodies[0].shape.Volume(),2000,places=5)

# unittest sees all inherited methods; suppress duplicate legacy contracts in this class.
for name in list(dir(ClassicUiTests)):
    if name.startswith('test_') and name in base.StudioTests.__dict__:setattr(ClassicUiTests,name,None)
