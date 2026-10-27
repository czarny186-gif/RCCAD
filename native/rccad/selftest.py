"""Executed by the packaged EXE as well as Python: validates shipped DLLs and I/O."""
from __future__ import annotations
import json
from pathlib import Path
import platform
import tempfile
from . import __version__, kernel as k
from .document import Body, Document


def run(report_path=None):
    checks = []
    shape = k.box(30, 30, 30)
    rounded = k.blend(shape, range(len(shape.Edges())), 3)
    assert rounded.isValid() and 0 < rounded.Volume() < shape.Volume()
    assert len(k.display_mesh(rounded).edges) == 0
    checks.append('OpenCascade: 12 edge fillets with smooth corner patches')
    drilled = k.hole(shape, 4, 15, 15)
    assert drilled.Volume() < shape.Volume() and drilled.isValid()
    checks.append('through hole')
    cut = k.boolean('subtract', shape, [k.box(10, 10, 40)])
    assert cut.isValid() and abs(cut.Volume()-24000) < 1e-5
    checks.append('Boolean subtraction')
    wire = k.sketch('rectangle','XY',20,10)
    assert abs(k.extrude(wire,'XY',10).Volume()-2000) < 1e-5
    checks.append('native sketch extrusion')
    from . import interaction as g
    frame=g.frame_for('XY',30)
    profile=Body('Na ścianie',g.profile('rectangle',frame,[(5,5),(25,25)]),'sketch',frame=frame)
    joined=g.apply_profile(profile,10,'union',Body('Baza',shape))
    assert abs(joined.Volume()-31000)<1e-5
    top=g.frame_for('XY',40)
    cutter=Body('Otwór',g.profile('circle',top,[(15,15),(18,15)]),'sketch',frame=top)
    cut=g.apply_profile(cutter,60,'subtract',Body('Połączona',joined))
    assert cut.isValid() and cut.Volume()<joined.Volume()
    checks.append('graphical profiles, face placement, joined extrusion and profile cut')
    letter=g.profile('text',g.frame_for(),[(0,0)],text='B',text_size=10)
    assert len(letter.Faces()[0].innerWires())==2
    text_solid=g.extrusion(Body('B',letter,'sketch',frame=g.frame_for()),3)
    assert text_solid.isValid() and abs(text_solid.Volume()-letter.Area()*3)<1e-5
    checks.append('bundled DejaVu font, exact text glyph holes and text extrusion')
    import cadquery as cq
    line=cq.Edge.makeLine((-10,0,0),(10,0,0))
    others=[cq.Edge.makeLine((x,-5,0),(x,5,0)) for x in (-3,3)]
    pieces=g.trim_segments(line,others,(0,0,0));assert len(pieces)==2 and abs(sum(e.Length() for e in pieces)-14)<1e-6
    checks.append('native analytic scissors intersections')
    a=Body('A',g.profile('circle',g.frame_for(),[(0,0),(5,0)]),'sketch',frame=g.frame_for())
    b=Body('B',g.profile('circle',g.frame_for(),[(5,0),(10,0)]),'sketch',frame=g.frame_for())
    cells=g.design_regions([a,b]);assert len(cells)==3 and all(face.isValid() for face,*_ in cells)
    checks.append('OpenCascade planar cells for selectable sketch intersections')
    doc=Document();body=Body('Zaokrąglona kostka',rounded).prepared();doc.commit([body])
    doc.undo();assert not doc.bodies;doc.redo();assert len(doc.bodies)==1
    with tempfile.TemporaryDirectory(prefix='rccad-check-') as directory:
        root=Path(directory)
        doc.save(root/'test.rccadx')
        opened=Document.load(root/'test.rccadx')
        assert abs(opened.bodies[0].shape.Volume()-rounded.Volume()) < 1e-5
        k.export_shapes([rounded],root/'test.step')
        imported=k.import_shapes(root/'test.step')
        assert abs(imported[0][0].Volume()-rounded.Volume()) < .001
        k.export_shapes([rounded],root/'test.stl')
        assert (root/'test.stl').stat().st_size>100
    checks.append('project, undo/redo, STEP round trip and STL export')
    # Construct actual native widgets, even on CI without a graphics-capable desktop.
    from PySide6.QtWidgets import QApplication
    from .window import MainWindow
    app=QApplication.instance() or QApplication([])
    window=MainWindow();window.document=doc;window.selected=[body.id];window.refresh()
    assert window.tree.topLevelItemCount()==1 and 'Objętość' in window.properties.text()
    window.view.resize(800,600);window.view.fit_all()
    projected,_,_=window.view.project_points(body.mesh.vertices[:3])
    assert window.view._ray(float(projected[0][0]),float(projected[0][1])) is not None
    assert all(not window.studio.buttons[key].icon().isNull() for key in ['sketch','extrude','boolean','blend','mirror'])
    from .artwork import CATALOG,icon
    assert len(CATALOG['images'])==6 and len(CATALOG['buttons'])==24
    assert all(not icon(name).isNull() for name in CATALOG['buttons'])
    checks.append('all 24 original HTML graphics and native graphical workspace')
    checks.append('Qt coordinate projection and picking ray')
    window.document._saved_revision=window.document._revision
    window.close();app.processEvents()
    checks.append('Qt native window, object tree and properties')
    result=dict(app='RCCAD Desktop',version=__version__,platform=platform.platform(),passed=True,checks=checks)
    if report_path:
        Path(report_path).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result
