"""Graphical input must preserve exact CAD and native project semantics."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
from rccad import kernel as k
from rccad import interaction as g
from rccad.document import Body,Document

class GestureTests(unittest.TestCase):
    def test_profiles_are_exact_wires_and_extrude(self):
        frame=g.frame_for('XY',10)
        examples=[('rectangle',[(0,0),(10,5)]),('center_rectangle',[(0,0),(5,3)]),('circle',[(0,0),(5,0)]),('ellipse',[(0,0),(5,3)]),('polygon',[(0,0),(5,0)]),('slot',[(0,0),(10,0),(5,2)]),('polyline',[(0,0),(10,0),(10,5),(5,2),(0,5)])]
        for kind,points in examples:
            with self.subTest(kind=kind):
                wire=g.profile(kind,frame,points)
                self.assertTrue(wire.IsClosed())
                body=Body('Profil',wire,'sketch',frame=frame)
                shape=g.extrusion(body,8)
                self.assertTrue(shape.isValid());self.assertGreater(shape.Volume(),0)
                bounds=k.bounds(shape);self.assertAlmostEqual(bounds.zmin,10,places=6);self.assertAlmostEqual(bounds.zmax,18,places=6)

    def test_line_and_arc_open_profiles_are_not_extrudable(self):
        f=g.frame_for()
        for kind,points in [('line',[(0,0),(10,0)]),('arc',[(0,0),(5,5),(10,0)])]:
            wire=g.profile(kind,f,points)
            self.assertFalse(wire.IsClosed())
            with self.assertRaises(k.CadError):g.extrusion(Body('A',wire,'sketch',frame=f),10)

    def test_stack_join_and_holes_on_all_six_faces(self):
        base=Body('Baza',k.box(30,30,30))
        f=g.frame_for('XY',30)
        post=Body('Szkic',g.profile('rectangle',f,[(5,5),(25,25)]),'sketch',frame=f,support_id=base.id)
        joined=g.apply_profile(post,10,'union',base)
        self.assertAlmostEqual(joined.Volume(),31000,places=6)
        target=base.changed(joined)
        for point in [(15,15,40),(15,15,0),(0,15,15),(30,15,15),(15,0,15),(15,30,15)]:
            with self.subTest(point=point):
                frame=g.face_frame(target,point)
                wire=g.profile('circle',frame,[(0,0),(2,0)])
                profile=Body('Otwór',wire,'sketch',frame=frame)
                result=g.apply_profile(profile,60,'subtract',target)
                self.assertTrue(result.isValid());self.assertLess(result.Volume(),target.shape.Volume())

    def test_oblique_face_frame_and_project_roundtrip(self):
        target=Body('Pochylona',k.transform(k.box(30,30,30),rotation=(20,15,0)))
        face=target.shape.Faces()[0];f=g.face_frame(target,face.Center().toTuple())
        b=Body('Na ścianie',g.profile('circle',f,[(0,0),(3,0)]),'sketch',frame=f,support_id=target.id).prepared()
        doc=Document();doc.commit([target.prepared(),b])
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'face.rccadx';doc.save(p);loaded=Document.load(p)
            self.assertEqual(loaded.bodies[1].frame,f)
            self.assertEqual(loaded.bodies[1].support_id,target.id)
            cut=g.apply_profile(loaded.bodies[1],60,'subtract',loaded.bodies[0])
            self.assertLess(cut.Volume(),target.shape.Volume())

    def test_invalid_frame_and_nonintersecting_cut(self):
        with self.assertRaises(k.CadError):g.checked_frame(((0,0,0),(1,0,0),(1,0,0)))
        f=g.frame_for('XY',100)
        b=Body('Poza',g.profile('circle',f,[(0,0),(2,0)]),'sketch',frame=f)
        with self.assertRaises(k.CadError):g.apply_profile(b,5,'subtract',Body('B',k.box(10,10,10)))

    def test_world_plane_ray_roundtrip(self):
        for plane in ['XY','XZ','YZ']:
            f=g.frame_for(plane,8);point=np.array(g.world_point(f,(7,12)));normal=np.array(f[2])
            uv=g.plane_point(f,point+normal*20,-normal)
            self.assertTrue(np.allclose(uv,[7,12]))

    def test_nested_profiles_create_exact_hole(self):
        f=g.frame_for('XY')
        outer=Body('Zewnętrzny',g.profile('rectangle',f,[(0,0),(30,20)]),'sketch',frame=f)
        inner=Body('Wewnętrzny',g.profile('circle',f,[(15,10),(18,10)]),'sketch',frame=f)
        outside=Body('Poza',g.profile('circle',f,[(50,10),(52,10)]),'sketch',frame=f)
        holes=g.inner_profiles(outer,[outer,inner,outside])
        self.assertEqual([b.id for b in holes],[inner.id])
        result=g.apply_profile(outer,10,'new',holes=holes)
        self.assertAlmostEqual(result.Volume(),(600-9*np.pi)*10,places=5)
        self.assertTrue(result.isValid())
