import unittest,tempfile
from pathlib import Path
import numpy as np
import cadquery as cq
from rccad import interaction as g,workflows as f,kernel as k
from rccad.document import Body,Document

class ClassicGeometryTests(unittest.TestCase):
    def body(self,kind,points,**extra):
        frame=g.frame_for();data=dict(type=kind,points=[list(p) for p in points],sides=5,**extra)
        shape=g.profile(kind,frame,points,5,extra.get('text','AB'),10)
        return Body(kind,shape,'sketch',frame=frame,sketch_data=data).prepared()
    def test_three_point_rectangle_is_exact(self):
        b=self.body('rect3',[(0,0),(3,4),(-1.6,1.2)])
        self.assertAlmostEqual(g.extrusion(b,3).Volume(),30,places=5)
    def test_circle_diameter_three_point_and_tangent(self):
        for kind,points,radius in [('circle2',[(-5,0),(5,0)],5),('circle3',[(5,0),(0,5),(-5,0)],5),('circleTangent2',[(0,0),(10,0),(0,0),(0,10),(4,3)],3.5)]:
            b=self.body(kind,points);self.assertAlmostEqual(g.extrusion(b,2).Volume(),np.pi*radius**2*2,places=5)
    def test_text_has_exact_glyph_holes(self):
        b=self.body('text',[(0,0)],text='B')
        self.assertEqual(len(b.shape.Faces()),1);self.assertEqual(len(b.shape.Faces()[0].innerWires()),2)
        self.assertAlmostEqual(k.bounds(b.shape).ylen,10,places=5)
        solid=g.extrusion(b,3);self.assertAlmostEqual(solid.Volume(),b.shape.Area()*3,places=5)
    def test_two_sided_and_symmetric_bounds(self):
        b=self.body('rectangle',[(0,0),(10,5)])
        for direction,second,low,high in [('one',0,0,8),('symmetric',0,-4,4),('two',3,-3,8)]:
            shape=f.ranged_tool(b,8,direction,second);bounds=k.bounds(shape)
            self.assertAlmostEqual(bounds.zmin,low,places=6);self.assertAlmostEqual(bounds.zmax,high,places=6)
    def test_multiple_profiles_one_atomic_transaction_and_undo(self):
        a=self.body('rectangle',[(0,0),(10,5)]);b=self.body('circle',[(20,0),(22,0)]);doc=Document();doc.commit([a,b])
        changed,ids=f.extrusion_transaction([a,b],doc.bodies,8,'new',direction='two',second=3);doc.commit(changed)
        self.assertEqual(len(ids),2);self.assertEqual(sum(b.kind=='solid' for b in doc.bodies),2)
        self.assertFalse(doc.get(a.id).visible);doc.undo();self.assertEqual(len(doc.bodies),2);self.assertTrue(doc.get(a.id).visible)
    def test_nested_islands_are_extruded(self):
        outer=self.body('rectangle',[(-10,-10),(10,10)]);hole=self.body('circle',[(0,0),(5,0)]);island=self.body('circle',[(0,0),(2,0)])
        tools,_=f.profile_tools([outer],[outer,hole,island],4,'one',0,False)
        self.assertEqual(len(tools),2);self.assertAlmostEqual(sum(s.Volume() for s in tools),(400-25*np.pi+4*np.pi)*4,places=5)
    def test_lines_form_closed_region_construction_excluded(self):
        lines=[self.body('line',[a,b]) for a,b in [((0,0),(10,0)),((10,0),(10,10)),((10,10),(0,10)),((0,10),(0,0))]]
        lines.append(self.body('construction',[(0,0),(10,10)]))
        regions=g.drawing_regions(lines);self.assertEqual(len(regions),1);self.assertEqual(len(regions[0][2]),4)
        self.assertAlmostEqual(cq.Face.makeFromWires(regions[0][0]).Area(),100,places=6)
    def test_trim_line_between_two_intersections(self):
        base=self.body('line',[(-10,0),(10,0)]);others=[self.body('line',[(x,-5),(x,5)]).shape for x in [-3,3]]
        edges=g.trim_segments(base.shape.Edges()[0],others,(0,0,0));self.assertEqual(len(edges),2);self.assertAlmostEqual(sum(e.Length() for e in edges),14,places=5)
    def test_trim_circle_keeps_exact_arc(self):
        b=self.body('circle',[(0,0),(5,0)]);line=self.body('line',[(0,-10),(0,10)])
        edges=g.trim_segments(b.shape.Edges()[0],[line.shape],(5,0,0))
        self.assertAlmostEqual(sum(e.Length() for e in edges),5*np.pi,places=5)
    def test_move_rotate_sketch_frame_and_project(self):
        b=self.body('rectangle',[(0,0),(10,5)]);m=f.moved_body(b,(1,2,3),(20,30,40))
        for point in m.sketch_data['points']:
            self.assertLess(m.shape.distance(cq.Vertex.makeVertex(*g.world_point(m.frame,point))),1e-6)
        doc=Document();doc.commit([m])
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'sketch.rccadx';doc.save(path);loaded=Document.load(path)
            self.assertEqual(loaded.bodies[0].sketch_data,m.sketch_data)
            self.assertTrue(np.allclose(loaded.bodies[0].frame,m.frame))
    def test_keep_boolean_tools(self):
        a=Body('Base',k.box(10,10,10));b=Body('Tool',k.box(5,5,20))
        result,identifier=f.boolean_transaction([a,b],[a.id,b.id],'subtract',True)
        self.assertEqual(len(result),2);self.assertEqual(identifier,a.id);self.assertAlmostEqual(result[0].shape.Volume(),750,places=5)

    def test_edit_dimension_moves_coincident_anchors_atomically(self):
        a=self.body('line',[(0,0),(10,0)]);b=self.body('line',[(10,0),(10,10)])
        changed=f.edit_sketch_transaction(a,dict(a.sketch_data,points=[[0,0],[20,0]]),[a,b])
        self.assertEqual(changed[1].sketch_data['points'][0],[20,0])
        self.assertEqual(a.sketch_data['points'][1],[10,0])
        self.assertLess(changed[0].shape.distance(changed[1].shape),1e-7)
    def test_arc_click_order_matches_html_start_end_on_arc(self):
        b=self.body('arc',[(0,0),(10,0),(5,5)]);edge=b.shape.Edges()[0]
        self.assertLess(np.linalg.norm(np.array(edge.endPoint().toTuple())-[10,0,0]),1e-7)
        self.assertAlmostEqual(edge.Length(),5*np.pi,places=5)
    def test_explicit_inner_region_can_be_selected_with_outer(self):
        outer=self.body('rectangle',[(-10,-10),(10,10)]);inner=self.body('circle',[(0,0),(4,0)])
        tools,_=f.profile_tools([outer,inner],[outer,inner],5,'one',0,False)
        self.assertEqual(len(tools),2);self.assertAlmostEqual(sum(t.Volume() for t in tools),2000,places=5)

    def test_screen_oriented_text_remains_extrudable_and_cuttable(self):
        frame=g.frame_for('XY',10)
        shape=g.profile('text',frame,[(0,0)],text='B',text_size=8,text_axes=[[1,0],[0,-1]])
        text=Body('B',shape,'sketch',frame=frame)
        self.assertEqual(len(shape.Faces()[0].innerWires()),2)
        self.assertTrue(g.extrusion(text,3).isValid())
        base=Body('Base',k.transform(k.box(30,30,10),(-5,-20,0)))
        self.assertLess(g.apply_profile(text,20,'subtract',base).Volume(),base.shape.Volume())

    def test_native_closed_cells_from_crossings_and_overlapping_circles(self):
        lines=[self.body('line',[(-5,y),(15,y)]) for y in (0,10)]+[self.body('line',[(x,-5),(x,15)]) for x in (0,10)]
        cells=g.design_regions(lines);self.assertEqual(len(cells),1);self.assertAlmostEqual(cells[0][0].Area(),100,places=5)
        a=self.body('circle',[(0,0),(5,0)]);b=self.body('circle',[(5,0),(10,0)])
        cells=g.design_regions([a,b]);self.assertEqual(len(cells),3)
        self.assertAlmostEqual(min(face.Area() for face,*_ in cells),2*25*np.arccos(.5)-2.5*np.sqrt(75),places=5)

    def test_mirror_over_chosen_face_copy_replace_and_join(self):
        body=Body('Kostka',k.box(10,10,10)).prepared();frame=g.face_frame(body,(5,5,10))
        copy=f.reflected_body(body,frame,False,True);self.assertNotEqual(copy.id,body.id);self.assertAlmostEqual(k.bounds(copy.shape).zmin,10,places=5)
        moved=f.reflected_body(body,frame,False,False);self.assertEqual(moved.id,body.id)
        joined=f.reflected_body(body,frame,True,True);self.assertEqual(joined.id,body.id);self.assertAlmostEqual(joined.shape.Volume(),2000,places=5)
