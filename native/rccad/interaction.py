"""Translate graphical gestures into exact OpenCascade inputs.

The existing CAD kernel remains the authority for validation and Boolean work.
No display triangles are used to construct model geometry.
"""
from __future__ import annotations
from math import atan2, degrees, hypot, isfinite
import cadquery as cq
import numpy as np
from functools import lru_cache
from . import kernel as k


@lru_cache(maxsize=3)
def font_cap_ratio(font_path):
    reference=cq.Compound.makeText('H',1,0,fontPath=font_path,halign='left',valign='bottom')
    return max(1e-9,k.bounds(reference).ylen)


def frame_for(plane='XY', offset=0):
    p = cq.Plane.named(plane)
    return (p.origin.add(p.zDir.multiply(float(offset))).toTuple(), p.xDir.toTuple(), p.zDir.toTuple())


def checked_frame(frame):
    try:
        a = np.asarray(frame, dtype=float)
        if a.shape != (3, 3) or not np.isfinite(a).all() or np.max(np.abs(a)) > 1e9:
            raise ValueError()
        if abs(np.linalg.norm(a[1])-1)>1e-6 or abs(np.linalg.norm(a[2])-1)>1e-6 or abs(a[1]@a[2])>1e-6:
            raise ValueError()
        return tuple(tuple(float(v) for v in row) for row in a)
    except (ValueError, TypeError):
        raise k.CadError('Nieprawidłowy układ płaszczyzny szkicu.') from None


def plane_from(frame):
    o, x, n = checked_frame(frame)
    return cq.Plane(o, x, n)


def world_point(frame, uv):
    return plane_from(frame).toWorldCoords(tuple(uv)).toTuple()


def plane_point(frame, origin, direction):
    p = plane_from(frame)
    n = np.array(p.zDir.toTuple()); o = np.array(p.origin.toTuple())
    denom = float(n @ direction)
    if abs(denom)<1e-9:return None
    t = float(n @ (o-origin))/denom
    if t < 0:return None
    q = p.toLocalCoords(cq.Vector(*(origin+direction*t)))
    return (q.x, q.y)


def face_frame(body, point):
    vertex = cq.Vertex.makeVertex(*point)
    faces = sorted(body.shape.Faces(), key=lambda f:f.distance(vertex))
    if not faces or faces[0].geomType() != 'PLANE' or faces[0].distance(vertex) > .3:
        raise k.CadError('Wybierz płaską ścianę bryły. Powierzchnie walcowe nie są płaszczyzną szkicu.')
    face = faces[0]; normal = face.normalAt().normalized()
    x = cq.Vector(1,0,0)
    if abs(x.dot(normal))>.9:x = cq.Vector(0,1,0)
    x = x.sub(normal.multiply(x.dot(normal))).normalized()
    # Stable origin at face centre; local coordinates remain modest on moved models.
    return checked_frame((face.Center().toTuple(), x.toTuple(), normal.toTuple()))


def profile(kind, frame, points, sides=6, text="RCCAD", text_size=10, text_angle=0, text_font="sans", text_align="left", text_axes=None):
    """Return a real CAD wire from local 2D drawing points."""
    p = plane_from(frame); wp = cq.Workplane(p)
    pts = [tuple(float(v) for v in q) for q in points]
    if any(len(q)!=2 or not all(isfinite(v) for v in q) for q in pts):raise k.CadError('Nieprawidłowe punkty szkicu.')
    if kind=='point':return cq.Vertex.makeVertex(*world_point(frame,pts[0]))
    if kind=='text':
        if not str(text).strip() or len(str(text))>256:raise k.CadError('Tekst: od 1 do 256 znaków.')
        origin=world_point(frame,pts[0]);position=cq.Plane(origin,p.xDir,p.zDir)
        from pathlib import Path
        font_name={'sans':'DejaVuSans.ttf','bold':'DejaVuSans-Bold.ttf','serif':'DejaVuSerif.ttf'}.get(text_font,'DejaVuSans.ttf')
        font_path=Path(__file__).parent/'assets'/'fonts'/font_name
        shape=cq.Compound.makeText(str(text),k.positive(text_size)/font_cap_ratio(str(font_path)),0,fontPath=str(font_path),halign=text_align if text_align in ('left','center','right') else 'left',valign='bottom',position=position)
        shape=shape.rotate(origin,cq.Vector(origin).add(p.zDir),float(text_angle))
        if text_axes is not None:
            axes=np.asarray(text_axes,dtype=float)
            if axes.shape!=(2,2) or not np.isfinite(axes).all() or not np.allclose(axes.T@axes,np.eye(2),atol=1e-7):raise k.CadError('Nieprawidłowa orientacja tekstu.')
            local=np.eye(3);local[:2,:2]=axes.T
            basis=np.array([p.xDir.toTuple(),p.yDir.toTuple(),p.zDir.toTuple()]).T;rotation=basis@local@basis.T
            matrix=np.eye(4);matrix[:3,:3]=rotation;matrix[:3,3]=np.array(origin)-rotation@np.array(origin)
            from OCP.gp import gp_Trsf
            transform=gp_Trsf();transform.SetValues(*matrix[:3,:].ravel().tolist())
            shape=shape.transformShape(cq.Matrix(transform))
        return k.valid(shape,False)
    if len(pts)<2:raise k.CadError('Wskaż co najmniej dwa punkty.')
    a,b = pts[0],pts[-1]; dx,dy = b[0]-a[0],b[1]-a[1]
    if kind=='rect3':
        a,b,c=np.asarray(pts,dtype=float);axis=b-a;length=k.positive(np.linalg.norm(axis));n=np.array([-axis[1],axis[0]])/length;height=float((c-a)@n)
        k.positive(abs(height),'Wysokość');corners=[tuple(a),tuple(b),tuple(b+n*height),tuple(a+n*height)]
        wire=wp.polyline(corners).close().val()
    elif kind in ('circle2','circle3','circleTangent2'):
        if kind=='circle2':center=((a[0]+b[0])/2,(a[1]+b[1])/2);radius=hypot(dx,dy)/2
        elif kind=='circle3':center,radius=circle_three(pts)
        else:center,radius=tangent_circle(pts)
        wire=wp.center(*center).circle(k.positive(radius,'Promień')).val()
    elif kind in ('rectangle','center_rectangle'):

        w,h = k.positive(abs(dx)),k.positive(abs(dy))
        if kind=='center_rectangle':cx,cy=a;w*=2;h*=2
        else:cx,cy=(a[0]+b[0])/2,(a[1]+b[1])/2
        wire=wp.center(cx,cy).rect(w,h).val()
    elif kind in ('circle','polygon'):
        radius=k.positive(hypot(dx,dy),'Promień')
        if kind=='circle':wire=wp.center(*a).circle(radius).val()
        else:
            if not 3<=int(sides)<=128:raise k.CadError('Wielokąt: od 3 do 128 boków.')
            wire=wp.center(*a).polygon(int(sides),radius*2).val()
            center=cq.Vector(world_point(frame,a));wire=wire.rotate(center,center.add(p.zDir),degrees(atan2(dy,dx)))
    elif kind=='ellipse':
        wire=wp.center(*a).ellipse(k.positive(abs(dx)),k.positive(abs(dy))).val()
    elif kind=='slot':
        if len(pts)!=3:raise k.CadError('Fasolka wymaga dwóch środków i punktu szerokości.')
        a,b,c=pts;dx,dy=b[0]-a[0],b[1]-a[1];length=k.positive(hypot(dx,dy));diameter=k.positive(2*abs(dx*(c[1]-a[1])-dy*(c[0]-a[0]))/length)
        wire=wp.center((a[0]+b[0])/2,(a[1]+b[1])/2).slot2D(length+diameter,diameter,degrees(atan2(dy,dx))).val()
    elif kind in ('polyline','line','construction'):

        if kind=='polyline':
            if len(pts)<3:raise k.CadError('Zamknięty profil wymaga co najmniej trzech wierzchołków.')
            wire=wp.polyline(pts).close().val()
        else:wire=cq.Wire.assembleEdges([cq.Edge.makeLine(world_point(frame,a),world_point(frame,b))])
    elif kind=='arc':
        if len(pts)!=3:raise k.CadError('Łuk wymaga trzech punktów.')
        wire=cq.Wire.assembleEdges([cq.Edge.makeThreePointArc(*(world_point(frame,pts[i]) for i in (0,2,1)))])
    else:raise k.CadError('Nieznane narzędzie szkicu.')
    return k.valid(wire, False)


def extrusion(body, distance, symmetric=False, holes=()):
    if body.frame is None and not holes and not body.shape.Faces():return k.extrude(body.shape,body.plane,distance,symmetric)
    d=float(distance)
    if not isfinite(d) or abs(d)<1e-5:raise k.CadError('Odległość musi być różna od zera.')
    faces=body.shape.Faces()
    if not faces and not body.shape.IsClosed():raise k.CadError('Wyciągnięcie wymaga zamkniętego profilu.')
    normal=cq.Vector((body.frame or frame_for(body.plane))[2]).multiply(d)
    if faces:
        solids=[]
        for face in faces:
            base=face.translate(normal.multiply(-.5)) if symmetric else face
            solids.append(cq.Solid.extrudeLinear(base.outerWire(),base.innerWires(),normal))
        return k.valid(cq.Compound.makeCompound(solids))
    wire=body.shape.translate(normal.multiply(-.5)) if symmetric else body.shape
    inners=[b.shape.translate(normal.multiply(-.5)) if symmetric else b.shape for b in holes]
    return k.valid(cq.Solid.extrudeLinear(wire,inners,normal))


def apply_profile(body, distance, mode, target=None, symmetric=False, holes=()):
    # Positive cut goes inward relative to the outward normal of its supporting face.
    tool=extrusion(body,-float(distance) if mode=='subtract' else distance,symmetric,holes)
    if mode=='new':return tool
    if target is None or target.kind!='solid':raise k.CadError('Wybierz bryłę docelową.')
    result=k.boolean(mode,target.shape,[tool])
    if mode=='subtract' and target.shape.Volume()-result.Volume()<1e-7:
        raise k.CadError('Profil nie usuwa materiału. Sprawdź położenie i głębokość.')
    return result


def inner_profiles(body, bodies):
    """Immediate nested coplanar contours, classified by exact CAD face Booleans."""
    if body.shape.Faces() or not body.shape.IsClosed():return []
    outer=cq.Face.makeFromWires(body.shape);plane=plane_from(body.frame or frame_for(body.plane));n=plane.zDir
    candidates=[]
    for other in bodies:
        if other.id==body.id or other.kind!='sketch' or not other.visible or other.shape.Faces() or (other.sketch_data or {}).get('type') in ('construction','point') or not other.shape.IsClosed():continue
        op=plane_from(other.frame or frame_for(other.plane))
        if abs(abs(n.dot(op.zDir))-1)>1e-7 or abs(n.dot(op.origin.sub(plane.origin)))>1e-6:continue
        face=cq.Face.makeFromWires(other.shape)
        if face.Area()>=outer.Area()-1e-7:continue
        if face.cut(outer).Area()<1e-7:candidates.append((other,face))
    return [other for other,face in candidates if not any(big.Area()>face.Area()+1e-7 and face.cut(big).Area()<1e-7 for _,big in candidates)]


def circle_three(points):
    a,b,c=np.asarray(points,dtype=float)
    mat=2*np.array([b-a,c-a]);rhs=np.array([b@b-a@a,c@c-a@a])
    if abs(np.linalg.det(mat))<1e-9:raise k.CadError('Trzy punkty okręgu nie mogą leżeć na jednej prostej.')
    center=np.linalg.solve(mat,rhs);return tuple(center),float(np.linalg.norm(a-center))


def tangent_circle(points):
    a,b,c,d,guess=np.asarray(points,dtype=float)
    normals=[]
    for start,end in [(a,b),(c,d)]:
        delta=end-start;length=k.positive(np.linalg.norm(delta),'Długość linii')
        n=np.array([-delta[1],delta[0]])/length;normals.append((n,float(n@start)))
    candidates=[]
    for sign in [-1,1]:
        n=normals[0][0]-sign*normals[1][0];den=float(n@n)
        if den<1e-12:continue
        center=guess-n*((n@guess-normals[0][1]+sign*normals[1][1])/den)
        radius=abs(float(normals[0][0]@center)-normals[0][1])
        if radius>1e-6:candidates.append((float(np.linalg.norm(center-guess)),tuple(center),radius))
    if not candidates:raise k.CadError('Nie można wyznaczyć okręgu stycznego do tych prostych.')
    _,center,radius=min(candidates);return center,radius


def trim_segments(edge,others,point):
    """Remove the exact analytic edge interval between neighbouring intersections."""
    start,end=edge.paramAt(0),edge.paramAt(1);cuts=[]
    for other in others:
        for candidate in other.Edges():
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
            section=BRepAlgoAPI_Section(edge.wrapped,candidate.wrapped,False);section.Build()
            for v in cq.Shape.cast(section.Shape()).Vertices():
                u=edge.paramAt(v.Center())
                if start+1e-7<u<end-1e-7 and not any(abs(u-q)<1e-7 for q in cuts):cuts.append(u)
    if not cuts:return []
    cuts=sorted(cuts);clicked=edge.paramAt(cq.Vector(*point))
    if edge.IsClosed():
        lower=max((u for u in cuts if u<=clicked),default=cuts[-1]-(end-start))
        upper=min((u for u in cuts if u>clicked),default=cuts[0]+(end-start))
        segments=[]
        for lo,hi in zip([start]+cuts,cuts+[end]):
            middle=(lo+hi)/2
            inside=lower-1e-8<middle<upper+1e-8 or lower-1e-8<middle-(end-start)<upper+1e-8 or lower-1e-8<middle+(end-start)<upper+1e-8
            if not inside and hi-lo>1e-7:segments.append(edge.trim(lo,hi))
        return segments
    intervals=list(zip([start]+cuts,cuts+[end]))
    selected=min(range(len(intervals)),key=lambda i:max(intervals[i][0]-clicked,clicked-intervals[i][1],0))
    return [edge.trim(lo,hi) for i,(lo,hi) in enumerate(intervals) if i!=selected and hi-lo>1e-7]


def drawing_regions(bodies):
    """Assemble closed chains of native line/arc wires, excluding construction geometry."""
    groups={}
    for b in bodies:
        data=b.sketch_data or {}
        if b.kind=='sketch' and b.visible and data.get('type') not in ('construction','point') and not b.shape.Faces() and not b.shape.IsClosed():
            frame=checked_frame(b.frame or frame_for(b.plane));groups.setdefault(frame,[]).append(b)
    result=[]
    for frame,items in groups.items():
        for wire in cq.Wire.combine([edge for b in items for edge in b.shape.Edges()],tol=1e-5):
            if wire.IsClosed():
                source=[b.id for b in items if all(e.distance(wire)<1e-6 for e in b.shape.Edges())]
                result.append((wire,frame,source))
    return result


def design_regions(bodies):
    """Build all bounded analytic cells of a planar drawing with OpenCascade."""
    from OCP.BOPAlgo import BOPAlgo_BuilderFace,BOPAlgo_Splitter
    from OCP.TopTools import TopTools_ListOfShape
    groups=[]
    for body in bodies:
        if body.kind!='sketch' or not body.visible or (body.sketch_data or {}).get('type') in ('point','construction'):continue
        frame=checked_frame(body.frame or frame_for(body.plane));p=plane_from(frame)
        group=next((entry for entry in groups if abs(abs(plane_from(entry[0]).zDir.dot(p.zDir))-1)<1e-7 and abs(plane_from(entry[0]).zDir.dot(p.origin.sub(plane_from(entry[0]).origin)))<1e-5),None)
        if group is None:groups.append((frame,[body]))
        else:group[1].append(body)
    result=[]
    for frame,items in groups:
        if len(items)<2 or all((b.sketch_data or {}).get('type')=='region' for b in items):continue
        edges=[e for b in items for e in b.shape.Edges()]
        if len(edges)>512:raise k.CadError('Zbyt rozbudowany szkic. Podziel go na mniejsze części.')
        arguments=TopTools_ListOfShape()
        for edge in edges:arguments.Append(edge.wrapped)
        splitter=BOPAlgo_Splitter();splitter.SetArguments(arguments);splitter.Perform()
        if splitter.HasErrors():raise k.CadError('Nie udało się rozpoznać przecięć szkicu.')
        boundary=TopTools_ListOfShape()
        for edge in cq.Shape.cast(splitter.Shape()).Edges():boundary.Append(edge.wrapped);boundary.Append(edge.wrapped.Reversed())
        builder=BOPAlgo_BuilderFace();builder.SetFace(cq.Face.makePlane(basePnt=frame[0],dir=frame[2]).wrapped);builder.SetShapes(boundary);builder.Perform()
        if builder.HasErrors():raise k.CadError('Nie udało się zamknąć obszarów szkicu.')
        sources=[b.id for b in items];containers=[]
        for b in items:
            if b.shape.Faces():containers.append((b,b.shape))
            elif b.shape.IsClosed():containers.append((b,cq.Face.makeFromWires(b.shape)))
        for wrapped in builder.Areas():
            face=cq.Shape.cast(wrapped)
            # The exterior area has negative measure; only bounded valid cells are profiles.
            if face.Area()<=1e-7 or not face.isValid():continue
            owners=[(container.Area(),b.id) for b,container in containers if abs(face.intersect(container).Area()-face.Area())<max(1e-7,face.Area()*1e-8)]
            owner=min(owners)[1] if owners else None
            result.append((face,frame,sources,items[0].support_id,owner))
            if len(result)>256:raise k.CadError('Zbyt wiele zamkniętych obszarów. Podziel szkic.')
    return result
