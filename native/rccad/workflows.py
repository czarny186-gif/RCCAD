"""Exact CAD adapters for the HTML modelling gestures; kernel.py is unchanged."""
from dataclasses import replace
import cadquery as cq
import numpy as np
from . import kernel as k,interaction as g
from .document import Body


def ranged_tool(body,distance,direction='one',second=0,cut=False,holes=()):
    distance=float(distance);second=float(second)
    if not np.isfinite([distance,second]).all() or second<0:raise k.CadError('Nieprawidłowe odległości wyciągnięcia.')
    if direction=='symmetric':return g.extrusion(body,-distance if cut else distance,True,holes)
    if direction!='two':return g.extrusion(body,-distance if cut else distance,False,holes)
    sign=-1 if cut else 1;normal=cq.Vector((body.frame or g.frame_for(body.plane))[2])
    shift=normal.multiply(-second*sign)
    shifted=replace(body,shape=body.shape.translate(shift))
    inner=[replace(h,shape=h.shape.translate(shift)) for h in holes]
    return g.extrusion(shifted,(distance+second)*sign,False,inner)


def profile_tools(profiles,bodies,distance,direction,second,cut,include_holes=True):
    tools=[];consumed=set();processed=set()
    def add(body):
        if body.id in processed:return
        processed.add(body.id)
        children=g.inner_profiles(body,bodies) if include_holes else []
        consumed.add(body.id);consumed.update(c.id for c in children)
        tools.append(ranged_tool(body,distance,direction,second,cut,children))
        # Islands inside holes are positive regions again.
        for child in children:
            for island in g.inner_profiles(child,bodies):add(island)
    for body in profiles:add(body)
    return tools,consumed


def extrusion_transaction(profiles,bodies,distance,mode,target=None,direction='one',second=0,include_holes=True):
    if not profiles:raise k.CadError('Kliknij zamknięty profil szkicu.')
    tools,consumed=profile_tools(profiles,bodies,distance,direction,second,mode=='subtract',include_holes)
    if mode=='new':results=[Body('Wyciągnięcie',tool).prepared() for tool in tools]
    else:
        if target is None or target.kind!='solid':raise k.CadError('Wybierz bryłę docelową.')
        result=k.boolean(mode,target.shape,tools)
        if mode=='subtract' and target.shape.Volume()-result.Volume()<1e-7:raise k.CadError('Profil nie usuwa materiału. Sprawdź kierunek i głębokość.')
        results=[target.changed(result)]
    changed=[replace(b,visible=False) if b.id in consumed else results[0] if mode!='new' and b.id==target.id else b for b in bodies]
    if mode=='new':changed.extend(results)
    return changed,[b.id for b in results]


def boolean_transaction(bodies,selected,mode,keep=False):
    picked=[next((b for b in bodies if b.id==i and b.kind=='solid'),None) for i in selected]
    picked=[b for b in picked if b]
    if len(picked)<2:raise k.CadError('Kliknij bryłę bazową i co najmniej jedną bryłę-narzędzie.')
    base,*tools=picked;result=base.changed(k.boolean(mode,base.shape,[b.shape for b in tools]));removed={b.id for b in tools} if not keep else set()
    return [result if b.id==base.id else b for b in bodies if b.id not in removed],base.id


def moved_body(body,move,rotation):
    shape=k.transform(body.shape,move,rotation)
    if body.kind!='sketch':return body.changed(shape)
    from math import sin,cos,pi
    matrix=np.eye(3)
    for index,angle in enumerate(rotation):
        t=float(angle)*pi/180;c,s=cos(t),sin(t)
        r=[np.array([[1,0,0],[0,c,-s],[0,s,c]]),np.array([[c,0,s],[0,1,0],[-s,0,c]]),np.array([[c,-s,0],[s,c,0],[0,0,1]])][index]
        matrix=r@matrix
    frame=g.checked_frame(body.frame or g.frame_for(body.plane));center=np.array(body.shape.Center().toTuple());origin=center+matrix@(np.array(frame[0])-center)+np.array(move)
    return replace(body.changed(shape),frame=g.checked_frame((origin,matrix@frame[1],matrix@frame[2])))


def edit_sketch_transaction(body,data,bodies):
    """Preserve the HTML coincidence rule while editing independent sketch records."""
    def rebuilt(b,definition):
        shape=g.profile(definition['type'],b.frame or g.frame_for(b.plane),definition['points'],definition.get('sides',5),definition.get('text','Tekst'),definition.get('text_size',10),definition.get('text_angle',0),definition.get('text_font','sans'),definition.get('text_align','left'),definition.get('text_axes'))
        return replace(b.changed(shape),sketch_data=definition)
    frame=body.frame or g.frame_for(body.plane)
    old_points=body.sketch_data['points'];new_points=data['points'];moved=[]
    for old,new in zip(old_points,new_points):
        a=np.array(g.world_point(frame,old));b=np.array(g.world_point(frame,new))
        if np.linalg.norm(b-a)>1e-5:moved.append((a,b))
    result=[]
    for other in bodies:
        if other.id==body.id:result.append(rebuilt(body,data));continue
        if other.kind!='sketch' or not other.sketch_data or not other.sketch_data.get('points'):
            result.append(other);continue
        op=g.plane_from(other.frame or g.frame_for(other.plane));base_plane=g.plane_from(frame)
        if abs(abs(base_plane.zDir.dot(op.zDir))-1)>1e-6 or abs(base_plane.zDir.dot(op.origin.sub(base_plane.origin)))>1e-5:
            result.append(other);continue
        definition=dict(other.sketch_data);points=[];changed=False
        for old in definition['points']:
            point=np.array(op.toWorldCoords(tuple(old)).toTuple());matches=[b for a,b in moved if np.linalg.norm(a-point)<1e-5]
            if len(matches)==1:
                local=op.toLocalCoords(cq.Vector(*map(float,matches[0])));points.append([local.x,local.y]);changed=True
            else:points.append(list(old))
        if changed:definition['points']=points;result.append(rebuilt(other,definition))
        else:result.append(other)
    return result


def reflected_body(body,frame,join=False,keep=True):
    plane=g.plane_from(frame);normal=plane.zDir.toTuple();origin=plane.origin.toTuple()
    shape=k.valid(body.shape.mirror(normal,origin),body.kind=='solid')
    if join:
        if body.kind!='solid':raise k.CadError('Łączyć można tylko bryły.')
        return body.changed(k.boolean('union',body.shape,[shape]))
    new_frame=body.frame
    if body.kind=='sketch':
        n=np.array(normal);matrix=np.eye(3)-2*np.outer(n,n);base=np.array(origin);old=g.checked_frame(body.frame or g.frame_for(body.plane))
        new_frame=g.checked_frame((base+matrix@(np.array(old[0])-base),matrix@old[1],-matrix@old[2]))
    if keep:return Body(body.name+' — odbicie',shape,body.kind,body.plane,frame=new_frame,sketch_data=body.sketch_data).prepared()
    return replace(body.changed(shape),frame=new_frame)
