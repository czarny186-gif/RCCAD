"""Translate graphical gestures into exact OpenCascade inputs.

The existing CAD kernel remains the authority for validation and Boolean work.
No display triangles are used to construct model geometry.
"""
from __future__ import annotations
from math import atan2, degrees, hypot, isfinite
import cadquery as cq
import numpy as np
from . import kernel as k


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


def profile(kind, frame, points, sides=6):
    """Return a real CAD wire from local 2D drawing points."""
    p = plane_from(frame); wp = cq.Workplane(p)
    pts = [tuple(float(v) for v in q) for q in points]
    if any(len(q)!=2 or not all(isfinite(v) for v in q) for q in pts):raise k.CadError('Nieprawidłowe punkty szkicu.')
    if len(pts)<2:raise k.CadError('Wskaż co najmniej dwa punkty.')
    a,b = pts[0],pts[-1]; dx,dy = b[0]-a[0],b[1]-a[1]
    if kind in ('rectangle','center_rectangle'):
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
    elif kind=='ellipse':
        wire=wp.center(*a).ellipse(k.positive(abs(dx)),k.positive(abs(dy))).val()
    elif kind=='slot':
        if len(pts)!=3:raise k.CadError('Fasolka wymaga dwóch środków i punktu szerokości.')
        a,b,c=pts;dx,dy=b[0]-a[0],b[1]-a[1];length=k.positive(hypot(dx,dy));diameter=k.positive(2*abs(dx*(c[1]-a[1])-dy*(c[0]-a[0]))/length)
        wire=wp.center((a[0]+b[0])/2,(a[1]+b[1])/2).slot2D(length+diameter,diameter,degrees(atan2(dy,dx))).val()
    elif kind in ('polyline','line'):
        if kind=='polyline':
            if len(pts)<3:raise k.CadError('Zamknięty profil wymaga co najmniej trzech wierzchołków.')
            wire=wp.polyline(pts).close().val()
        else:wire=cq.Wire.assembleEdges([cq.Edge.makeLine(world_point(frame,a),world_point(frame,b))])
    elif kind=='arc':
        if len(pts)!=3:raise k.CadError('Łuk wymaga trzech punktów.')
        wire=cq.Wire.assembleEdges([cq.Edge.makeThreePointArc(*(world_point(frame,q) for q in pts))])
    else:raise k.CadError('Nieznane narzędzie szkicu.')
    return k.valid(wire, False)


def extrusion(body, distance, symmetric=False, holes=()):
    if body.frame is None and not holes:return k.extrude(body.shape,body.plane,distance,symmetric)
    d=float(distance)
    if not isfinite(d) or abs(d)<1e-5:raise k.CadError('Odległość musi być różna od zera.')
    if not body.shape.IsClosed():raise k.CadError('Wyciągnięcie wymaga zamkniętego profilu.')
    normal=cq.Vector((body.frame or frame_for(body.plane))[2]).multiply(d)
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
    if not body.shape.IsClosed():return []
    outer=cq.Face.makeFromWires(body.shape);plane=plane_from(body.frame or frame_for(body.plane));n=plane.zDir
    candidates=[]
    for other in bodies:
        if other.id==body.id or other.kind!='sketch' or not other.visible or not other.shape.IsClosed():continue
        op=plane_from(other.frame or frame_for(other.plane))
        if abs(abs(n.dot(op.zDir))-1)>1e-7 or abs(n.dot(op.origin.sub(plane.origin)))>1e-6:continue
        face=cq.Face.makeFromWires(other.shape)
        if face.Area()>=outer.Area()-1e-7:continue
        if face.cut(outer).Area()<1e-7:candidates.append((other,face))
    return [other for other,face in candidates if not any(big.Area()>face.Area()+1e-7 and face.cut(big).Area()<1e-7 for _,big in candidates)]
