"""Native Qt/OpenGL viewport with picking against displayed CAD edge curves."""
from __future__ import annotations
import numpy as np
import pyqtgraph as pg
import pyqtgraph.opengl as gl
from pyqtgraph.opengl import shaders
from PySide6.QtCore import Qt, Signal, QVariantAnimation, QEasingCurve, QEvent
from PySide6.QtGui import QVector3D
from .document import Body


class CadView(gl.GLViewWidget):
    planeClicked = Signal(str)
    pointerMoved = Signal(float,float)
    sketchDoubleClicked = Signal(float,float)
    dimensionRequested = Signal()
    operationRequested = Signal()
    sketchClicked = Signal(float, float)
    sketchMoved = Signal(float, float)
    faceClicked = Signal(str, object)
    profileClicked = Signal(str)
    handleDragged = Signal(str, float)
    editCancelled = Signal()
    profileClosed = Signal()
    edgeClicked = Signal(str, int, bool)
    bodyClicked = Signal(str, bool)
    selectionCleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        if 'rccad' not in shaders.ShaderProgram.names:
            shaders.ShaderProgram('rccad', [
                shaders.VertexShader(shaders.getShaderProgram('shaded').shaders[0].code),
                shaders.FragmentShader("""
                    #ifdef GL_ES
                    precision mediump float;
                    #endif
                    varying vec4 v_color;
                    varying vec3 v_normal;
                    void main() {
                        float diffuse = max(0.0, dot(normalize(v_normal), normalize(vec3(0.35, 0.5, 1.0))));
                        gl_FragColor = vec4(v_color.rgb * (0.68 + 0.40 * floor(diffuse*24.0+0.5)/24.0), v_color.a);
                    }
                """),
            ])
        self.setBackgroundColor('#edf1f5')
        self.setCameraPosition(distance=210, elevation=31.51268, azimuth=132.971835)
        from .appearance import HtmlBackground,HtmlGrid
        self.background_item=HtmlBackground();self.addItem(self.background_item)
        grid=HtmlGrid();self.grid_half=120;self.addItem(grid)
        self.grid_item = grid
        self.bodies = ()
        self.model_items = []
        self.highlight_items = []
        self.selected_bodies = set()
        self.selected_edges = {}
        self.edge_mode = False
        self.mouse_mode = "select"
        self.multi_select = False
        self._drag_position = None
        self._press = None
        self._canvas_pan = False
        self._pan_was_dragged = False
        self.sketch_mode = False
        self.face_mode = False
        self.profile_mode = False
        self.preview_items = []
        self.preview_replacement = None
        self.handle_items = []
        self.handle = None
        self.gizmo_handles = []
        self.gizmo_center = None
        self.drag_handle = None
        self.plane_mode = False
        self.plane_items = []
        self.plane_art = {}
        self.hover_plane = None
        self.ghost_hover = []
        self.flash_color = None
        self.camera_animation = QVariantAnimation(self)
        self.camera_animation.setDuration(280);self.camera_animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.camera_animation.valueChanged.connect(self._camera_step)
        self.flash_animation = QVariantAnimation(self);self.flash_animation.setDuration(360)
        self.flash_animation.setStartValue(1.);self.flash_animation.setEndValue(0.)
        self.flash_animation.valueChanged.connect(self._flash_step)



    def set_models(self, bodies, selected_bodies=(), selected_edges=None):
        for item in self.model_items + self.highlight_items:
            self.removeItem(item)
        self.model_items, self.highlight_items = [], []
        self.bodies = tuple(bodies)
        self.selected_bodies = set(selected_bodies)
        self.selected_edges = selected_edges or {}
        for body in self.bodies:
            if not body.visible or body.mesh is None:
                continue
            replacement=self.preview_replacement is not None and self.preview_replacement[0]==body.id
            mesh = self.preview_replacement[1] if replacement else body.mesh
            color = (138/255,138/255,144/255,1)
            if replacement:color=(.28,.74,.55,1)
            elif self.flash_color and body.kind=='solid' and body.id in self.flash_ids:
                c,t=self.flash_color;color=tuple(color[j]*(1-t)+c[j]*t for j in range(3))+(1,)
            if len(mesh.triangles) and body.kind!='sketch':
                item = gl.GLMeshItem(vertexes=mesh.vertices, faces=mesh.triangles, smooth=True, color=color, shader='rccad', drawEdges=False)
                item.setGLOptions('opaque')
                from OpenGL import GL
                item.updateGLOptions({GL.GL_POLYGON_OFFSET_FILL: True, 'glPolygonOffset': (1., 1.)})
                self.addItem(item)
                self.model_items.append(item)
            for index, points in mesh.edges.items():
                if (body.sketch_data or {}).get('type')=='construction':continue
                selected = not replacement and index in self.selected_edges.get(body.id, set())
                line = gl.GLLinePlotItem(pos=points, color=(.78, .10, .12, 1) if selected else ((.12,.43,.85,1) if body.kind=='sketch' or body.id in self.selected_bodies else (0,0,0,1)), width=3 if selected else 1, antialias=True, glOptions='opaque')
                self.addItem(line)
                self.model_items.append(line)
        self.update()

    def fit_all(self):
        visible = [b for b in self.bodies if b.visible and b.mesh is not None and len(b.mesh.vertices)]
        if not visible:
            self.opts['center'] = QVector3D(0, 0, 0)
            self.setCameraPosition(distance=120)
            return
        low = np.min([b.mesh.vertices.min(axis=0) for b in visible], axis=0)
        high = np.max([b.mesh.vertices.max(axis=0) for b in visible], axis=0)
        center = (low + high) / 2
        self.opts['center'] = QVector3D(*map(float, center))
        self.setCameraPosition(distance=max(20, float(np.linalg.norm(high - low)) * 1.6))

    def set_view(self, name):
        values = {'iso': (31.51268,132.971835), 'XY': (90,90), '-XY': (-90,90), 'XZ': (0,90), '-XZ': (0,-90), 'YZ': (0,0), '-YZ': (0,180)}
        el, az = values[name]
        self.animate_camera(el,az)

    def animate_camera(self,elevation,azimuth,center=None):
        if not self.isVisible():
            if center is not None:self.opts['center']=QVector3D(*center)
            self.setCameraPosition(elevation=elevation,azimuth=azimuth);return
        self.camera_animation.stop()
        old=np.array([self.opts['elevation'],self.opts['azimuth'],*self.opts['center'].toTuple()],dtype=float)
        azimuth=old[1]+(azimuth-old[1]+180)%360-180
        new=np.array([elevation,azimuth,*(center if center is not None else old[2:])],dtype=float)
        self._camera_endpoints=(old,new)
        self.camera_animation.setStartValue(0.);self.camera_animation.setEndValue(1.);self.camera_animation.start()

    def _camera_step(self,t):
        old,new=self._camera_endpoints;v=old*(1-t)+new*t
        self.opts['center']=QVector3D(*map(float,v[2:]));self.setCameraPosition(elevation=float(v[0]),azimuth=float(v[1]))

    def flash(self,color,identifiers=None):
        if not self.isVisible():return
        self.flash_ids=set(identifiers if identifiers is not None else [b.id for b in self.bodies])
        self._flash_rgb=np.array(pg.mkColor(color).getRgbF()[:3]);self.flash_animation.stop();self.flash_animation.start()

    def _flash_step(self,t):
        self.flash_color=(self._flash_rgb,float(t)) if t>.001 else None
        self.set_models(self.bodies,self.selected_bodies,self.selected_edges)

    def show_planes(self,visible=True):
        for item in self.plane_items:self.removeItem(item)
        self.plane_items=[];self.plane_art={};self.hover_plane=None;self.plane_mode=visible
        if not visible:return
        from .interaction import frame_for,world_point
        for name,color in [('XY',(64/255,133/255,235/255,.16)),('XZ',(56/255,171/255,112/255,.16)),('YZ',(226/255,92/255,98/255,.16))]:
            points=np.array([world_point(frame_for(name),q) for q in [(-23,-23),(23,-23),(23,23),(-23,23)]])
            face=gl.GLMeshItem(vertexes=points,faces=np.array([[0,1,2],[0,2,3]]),color=color,smooth=False,shader='balloon')
            face.setGLOptions('translucent');self.addItem(face);self.plane_items.append(face)
            edge=gl.GLLinePlotItem(pos=np.vstack([points,points[0]]),color=(*color[:3],.8),width=2,antialias=True)
            self.addItem(edge);self.plane_items.append(edge);self.plane_art[name]=(face,edge,color)

    def hover_planes(self,x,y):
        name=self.pick_plane(x,y)
        if name==self.hover_plane:return
        self.hover_plane=name
        for key,(face,edge,color) in self.plane_art.items():
            face.setColor((*color[:3],.28 if key==name else .16));edge.setData(color=(*color[:3],.95 if key==name else .62),width=2.3 if key==name else 1.5)
        self.setCursor(Qt.PointingHandCursor if name else Qt.OpenHandCursor)

    def pick_plane(self,x,y):
        from .interaction import frame_for,plane_point,world_point
        ray=self._ray(x,y)
        if ray is None:return None
        best=None
        for name in ['XY','XZ','YZ']:
            q=plane_point(frame_for(name),*ray)
            if q is None or not all(abs(v)<=23.0001 for v in q):continue
            d=np.linalg.norm(np.array(world_point(frame_for(name),q))-ray[0])
            if best is None or d<best[0]:best=(d,name)
        return best[1] if best else None

    def hover_at(self,x,y):
        for item in self.ghost_hover:self.removeItem(item)
        self.ghost_hover=[]
        if self.sketch_mode or self.plane_mode or self.drag_handle:return
        hit=self.nearest_edge(x,y) if self.edge_mode else None
        ray=self._ray(x,y);bodyhit=self._hit(*ray) if ray else None
        identifier=hit[0] if hit else self.pick_profile(x,y) if self.profile_mode else bodyhit[1] if bodyhit else None
        body=next((b for b in self.bodies if b.id==identifier),None)
        if not body or not body.mesh:return
        for index,points in body.mesh.edges.items():
            if hit and index!=hit[1]:continue
            item=gl.GLLinePlotItem(pos=points,color=(.18,.53,.9,.8),width=2,antialias=True,glOptions='opaque')
            self.addItem(item);self.ghost_hover.append(item)

    def projectionMatrix(self,region,viewport):
        # HTML's canvas projection uses the opposite horizontal handedness.
        # Reflect only the display projection; all model coordinates remain exact CAD.
        from PySide6.QtGui import QMatrix4x4
        from math import atan,degrees
        self.opts['fov']=degrees(2*atan(max(1,self.width())/(2*max(1,min(self.width(),self.height()))*1.45)))
        projection=super().projectionMatrix(region,viewport);mirror=QMatrix4x4();mirror.scale(-1.,1.,1.)
        return mirror*projection

    def pan(self,dx,dy,dz,relative='global'):
        return super().pan(-dx if relative in ('view','view-upright') else dx,dy,dz,relative)

    def camera_matrix(self):
        viewport = (0, 0, max(1,self.width()), max(1,self.height()))
        return self.projectionMatrix(viewport,viewport) * self.viewMatrix()

    def project_points(self, points):
        # Explicit Qt matrix data avoid NumPy/Qt row-major ambiguity.
        matrix = self.camera_matrix()
        m = np.array([[r.x(), r.y(), r.z(), r.w()] for r in (matrix.row(i) for i in range(4))])
        homogeneous = np.column_stack((points, np.ones(len(points)))) @ m.T
        w = homogeneous[:, 3]
        safe = np.where(np.abs(w) > 1e-12, w, np.nan)
        ndc = homogeneous[:, :3] / safe[:, None]
        xy = np.column_stack(((ndc[:, 0] + 1) * self.width() / 2, (1 - ndc[:, 1]) * self.height() / 2))
        return xy, ndc[:, 2], w

    def nearest_edge(self, x, y):
        best, distance = None, 10.
        for body in self.bodies:
            if not body.visible or not body.mesh:
                continue
            for index, points in body.mesh.edges.items():
                xy, z, w = self.project_points(points)
                if len(xy) < 2:
                    continue
                a, b = xy[:-1], xy[1:]
                delta = b - a
                denom = (delta * delta).sum(axis=1)
                t = np.clip(((np.array([x, y]) - a) * delta).sum(axis=1) / np.maximum(denom, 1e-12), 0, 1)
                projected = a + delta * t[:, None]
                dist = np.linalg.norm(projected - [x, y], axis=1)
                dist[(w[:-1] <= 0) | (w[1:] <= 0)] = np.inf
                if not np.isfinite(dist).any():
                    continue
                j = int(np.nanargmin(dist))
                if dist[j] < distance:
                    world = points[j] + (points[j + 1] - points[j]) * t[j]
                    if self._visible_point(world):
                        distance, best = float(dist[j]), (body.id, index)
        return best

    def _ray(self, x, y):
        inverse, ok = (self.camera_matrix()).inverted()
        if not ok:
            return None
        from PySide6.QtGui import QVector4D
        pts = []
        for z in (-1, 1):
            p = inverse.map(QVector3D(float(2*x/self.width()-1), float(1-2*y/self.height()), float(z)))
            pts.append(np.array([p.x(), p.y(), p.z()]))
        direction = pts[1] - pts[0]
        return pts[0], direction / np.linalg.norm(direction)

    def _hit(self, origin, direction):
        best = None
        for body in self.bodies:
            if not body.visible or body.kind=='sketch' or not body.mesh or not len(body.mesh.triangles):
                continue
            v = body.mesh.vertices[body.mesh.triangles]
            e1, e2 = v[:, 1]-v[:, 0], v[:, 2]-v[:, 0]
            h = np.cross(np.broadcast_to(direction, e2.shape), e2)
            a = np.einsum('ij,ij->i', e1, h)
            f = np.divide(1., a, out=np.zeros_like(a), where=np.abs(a)>1e-9)
            s = origin-v[:, 0]
            u = f*np.einsum('ij,ij->i', s, h)
            q = np.cross(s, e1)
            vv = f*np.einsum('j,ij->i', direction, q)
            t = f*np.einsum('ij,ij->i', e2, q)
            mask=(np.abs(a)>1e-9)&(u>=-1e-6)&(vv>=-1e-6)&(u+vv<=1+1e-6)&(t>1e-6)
            if mask.any():
                value=float(t[mask].min())
                if best is None or value<best[0]:
                    best=(value,body.id)
        return best

    def _visible_point(self, point):
        xy, _, _ = self.project_points(np.asarray([point]))
        ray = self._ray(*xy[0])
        if ray is None:
            return False
        origin, direction = ray
        hit = self._hit(origin, direction)
        return hit is None or hit[0] >= np.linalg.norm(point-origin)-.25

    def sync_grid(self):
        if not hasattr(self,'grid_item'):return
        pixels=max(1,min(self.width(),self.height()))*1.45/max(.001,self.opts['distance'])
        candidates=[.1,.2,.5,1,2,5,10]
        step=next((v for v in candidates if v*pixels>=17 and 2*self.grid_half/v<=1200),None)
        if step is None:step=max(10,float(np.ceil(self.grid_half/600/10)*10))
        self.grid_item.rebuild(self.grid_half,step)

    def setCameraPosition(self,*args,**kwargs):
        super().setCameraPosition(*args,**kwargs);self.sync_grid()

    def wheelEvent(self,event):
        super().wheelEvent(event);self.sync_grid()

    def resizeGL(self,w,h):
        super().resizeGL(w,h);self.sync_grid()

    def set_sketch_plane(self,frame):
        from PySide6.QtGui import QMatrix4x4
        from .interaction import plane_from
        if frame is None:self.grid_item.resetTransform();return
        p=plane_from(frame);x=p.xDir.toTuple();y=p.yDir.toTuple();z=p.zDir.toTuple();o=p.origin.toTuple()
        matrix=QMatrix4x4(x[0],y[0],z[0],o[0],x[1],y[1],z[1],o[1],x[2],y[2],z[2],o[2],0,0,0,1)
        self.grid_item.setTransform(matrix)

    def show_blend_preview(self,identifier,mesh):
        self.clear_preview();self.preview_replacement=(identifier,mesh)
        self.set_models(self.bodies,self.selected_bodies,self.selected_edges)

    def clear_preview(self):
        if self.preview_replacement is not None:
            self.preview_replacement=None;self.set_models(self.bodies,self.selected_bodies,self.selected_edges)
        for item in self.preview_items:self.removeItem(item)
        self.preview_items=[]
        self.update()

    def show_lines(self, points, color):
        self.clear_preview()
        item=gl.GLLinePlotItem(pos=points,color=pg.mkColor(color),width=3,antialias=True)
        self.addItem(item);self.preview_items.append(item)

    def show_wire(self,wire,color):
        self.clear_preview()
        for edge in wire.Edges():
            points=np.asarray([p.toTuple() for p in edge.positions(np.linspace(0,1,2 if edge.geomType()=='LINE' else 72))])
            item=gl.GLLinePlotItem(pos=points,color=pg.mkColor(color),width=3,antialias=True)
            self.addItem(item);self.preview_items.append(item)

    def show_preview_mesh(self,mesh,color):
        self.clear_preview()
        col=pg.mkColor(color);col.setAlphaF(.42)
        item=gl.GLMeshItem(vertexes=mesh.vertices,faces=mesh.triangles,smooth=True,color=col,shader='rccad',drawEdges=False)
        item.setGLOptions('translucent');self.addItem(item);self.preview_items.append(item)
        for points in mesh.edges.values():
            edge=gl.GLLinePlotItem(pos=points,color=pg.mkColor(color),width=2,antialias=True)
            self.addItem(edge);self.preview_items.append(edge)

    def set_handle(self,point,normal=None,kind=None):
        for item in self.handle_items:self.removeItem(item)
        self.handle_items=[]
        self.gizmo_handles=[]
        self.handle=None if point is None else (np.array(point,dtype=float),np.array(normal,dtype=float),kind)
        if self.handle:
            point,normal,kind=self.handle
            # Fixed 3D arrow; screen picking uses its projected tip.
            length=max(3,self.opts['distance']*.045)
            points=np.array([point-normal*length,point])
            line=gl.GLLinePlotItem(pos=points,color=(1,.58,.08,1),width=5,antialias=True)
            dot=gl.GLScatterPlotItem(pos=point.reshape(1,3),color=(1,.58,.08,1),size=24,pxMode=True)
            for item in [line,dot]:
                item.setGLOptions('translucent');self.addItem(item);self.handle_items.append(item)
        self.update()

    def set_gizmo(self,center,size,rotate=False):
        self.set_handle(None);self.gizmo_center=np.array(center,dtype=float)
        length=max(6,float(size));colors=[(.88,.26,.30,1),(.17,.64,.39,1),(.22,.49,.9,1)]
        for i,axis in enumerate(np.eye(3)):
            if rotate:
                u=np.eye(3)[(i+1)%3];v=np.eye(3)[(i+2)%3];angles=np.linspace(0,2*np.pi,96)
                curve=self.gizmo_center+(np.cos(angles)[:,None]*u+np.sin(angles)[:,None]*v)*length
                point=curve[12];kind='rotate_'+str(i)
                pick=curve
            else:
                point=self.gizmo_center+axis*length;curve=np.array([self.gizmo_center,point]);kind='transform_'+str(i);pick=point.reshape(1,3)
            line=gl.GLLinePlotItem(pos=curve,color=colors[i],width=3,antialias=True)
            self.addItem(line);self.handle_items.append(line)
            if not rotate:
                dot=gl.GLScatterPlotItem(pos=point.reshape(1,3),color=colors[i],size=18,pxMode=True);self.addItem(dot);self.handle_items.append(dot)
            self.gizmo_handles.append((point,axis,kind,pick))
        self.handle=self.gizmo_handles[0][:3]
        self.update()

    def pick_profile(self,x,y):
        import cadquery as cq
        from .interaction import plane_point, frame_for
        ray=self._ray(x,y)
        if ray is None:return None
        solid=self._hit(*ray);best=None
        for body in self.bodies:
            if not body.visible or body.kind!='sketch':continue
            try:
                if (body.sketch_data or {}).get('type') in ('construction','point') or (body.sketch_data or {}).get('region_source'):continue
                frame=body.frame or frame_for(body.plane)
                q=plane_point(frame,*ray)
                if q is None:continue
                from .interaction import world_point
                point=world_point(frame,q)
                depth=np.linalg.norm(np.array(point)-ray[0])
                if solid and solid[0]<depth-.3:continue
                if body.shape.Faces() or body.shape.IsClosed():
                    face=body.shape if body.shape.Faces() else cq.Face.makeFromWires(body.shape)
                    inside=face.distance(cq.Vertex.makeVertex(*point))<.1
                else:inside=False
                if inside and (best is None or depth<best[0]-1e-4 or (abs(depth-best[0])<1e-4 and face.Area()<best[2])):best=(depth,body.id,face.Area())
            except (ValueError,RuntimeError):continue
        if best:return best[1]
        hit=self.nearest_edge(x,y)
        if hit and any(b.id==hit[0] and b.kind=='sketch' for b in self.bodies):return hit[0]
        return None

    def mouseMoveEvent(self, event):
        self.pointerMoved.emit(event.position().x(),event.position().y())
        if self._canvas_pan:
            pos=event.position();delta=pos-self._drag_position;self._drag_position=pos
            self.pan(delta.x(),delta.y(),0,relative='view-upright')
            if self._press and np.hypot(pos.x()-self._press[0],pos.y()-self._press[1])>4:self._pan_was_dragged=True
            event.accept();return
        if self.drag_handle is not None:
            point,normal,kind,last=self.drag_handle
            current=event.position()
            xy,_,_=self.project_points(np.array([point,point+normal]))
            vector=xy[1]-xy[0];denom=float(vector@vector)
            delta=np.array([current.x()-last.x(),current.y()-last.y()])
            if kind.startswith('rotate_'):
                center=self.project_points(np.array([self.gizmo_center]))[0][0]
                a=np.array([last.x(),last.y()])-center;b=np.array([current.x(),current.y()])-center
                amount=float((np.degrees(np.arctan2(b[1],b[0])-np.arctan2(a[1],a[0]))+180)%360-180)
            else:amount=float(delta@vector/denom) if denom>.04 else -float(delta[1])*self.opts['distance']/max(1,self.height())
            self.drag_handle=(point+normal*amount,normal,kind,current)
            self.handleDragged.emit(kind,amount);event.accept();return
        if self.sketch_mode and self.mouse_mode=='select':
            self.sketchMoved.emit(event.position().x(),event.position().y())
            event.accept();return
        if self._press and self._press[2] == Qt.LeftButton and self.mouse_mode in ('orbit', 'pan'):
            pos = event.position()
            previous = self._drag_position or pos
            delta = pos - previous
            self._drag_position = pos
            if self.mouse_mode == 'orbit':
                self.orbit(-delta.x(), delta.y())
            else:
                self.pan(delta.x(), delta.y(), 0, relative='view-upright')
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        self._drag_position = event.position()
        self._press = (event.position().x(), event.position().y(), event.button())
        self._pan_was_dragged=False
        self._canvas_pan=event.button()==Qt.RightButton or (self.sketch_mode and event.button()==Qt.LeftButton and bool(event.modifiers() & Qt.ShiftModifier))
        if self._canvas_pan:event.accept();return
        if self.gizmo_handles and event.button()==Qt.LeftButton:
            pos=np.array([event.position().x(),event.position().y()]);best=None
            for point,normal,kind,curve in self.gizmo_handles:
                xy,_,_=self.project_points(curve)
                distances=np.linalg.norm(xy-pos,axis=1);distance=float(distances.min())
                if distance<14 and (best is None or distance<best[0]):best=(distance,point,normal,kind)
            if best is not None:
                _,point,normal,kind=best;self.drag_handle=(point,normal,kind,event.position());event.accept();return
        if self.handle is not None and event.button()==Qt.LeftButton:
            point,normal,kind=self.handle
            xy,_,_=self.project_points(point.reshape(1,3))
            if np.linalg.norm(xy[0]-[event.position().x(),event.position().y()])<18:
                self.drag_handle=(point,normal,kind,event.position());event.accept();return
        if (self.sketch_mode or self.face_mode or self.plane_mode) and self.mouse_mode=='select':event.accept();return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._canvas_pan:
            self._canvas_pan=False;self._press=None;event.accept();return
        if self.drag_handle is not None:
            self.drag_handle=None;self._press=None;event.accept();return
        super().mouseReleaseEvent(event)
        if not self._press:return
        x,y,button=self._press;self._press=None
        if self.mouse_mode!='select' or button!=Qt.LeftButton or np.hypot(event.position().x()-x,event.position().y()-y)>4:return
        if self.plane_mode:
            ray=self._ray(x,y);hit=self._hit(*ray) if ray else None
            if hit:self.faceClicked.emit(hit[1],tuple(ray[0]+ray[1]*hit[0]));return
            profile=self.pick_profile(x,y)
            if profile:self.profileClicked.emit(profile);return
            plane=self.pick_plane(x,y)
            if plane:self.planeClicked.emit(plane)
            return
        if self.sketch_mode:self.sketchClicked.emit(x,y);return
        if self.face_mode:
            ray=self._ray(x,y);hit=self._hit(*ray) if ray else None
            if hit:self.faceClicked.emit(hit[1],tuple(ray[0]+ray[1]*hit[0]))
            return
        additive=self.multi_select or bool(event.modifiers() & Qt.ShiftModifier)
        if self.edge_mode:
            hit=self.nearest_edge(x,y)
            if hit:self.edgeClicked.emit(*hit,additive)
            elif not additive:self.selectionCleared.emit()
        else:
            profile=self.pick_profile(x,y)
            if profile:
                if self.profile_mode:self.profileClicked.emit(profile)
                else:self.bodyClicked.emit(profile,additive)
                return
            ray=self._ray(x,y);hit=self._hit(*ray) if ray else None
            if hit:self.bodyClicked.emit(hit[1],additive)
            elif not additive:self.selectionCleared.emit()

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.LeftButton:
            self.sketchDoubleClicked.emit(event.position().x(),event.position().y());event.accept();return
        super().mouseDoubleClickEvent(event)

    def event(self,event):
        if event.type()==QEvent.KeyPress and event.key()==Qt.Key_Tab and self.sketch_mode:
            self.dimensionRequested.emit();event.accept();return True
        return super().event(event)

    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Tab and self.sketch_mode:
            self.dimensionRequested.emit();event.accept();return
        if event.key() in (Qt.Key_Return,Qt.Key_Enter) and not self.sketch_mode:
            self.operationRequested.emit();event.accept();return
        if event.key()==Qt.Key_Escape:
            self.editCancelled.emit();event.accept();return
        if event.key() in (Qt.Key_Return,Qt.Key_Enter) and self.sketch_mode:
            self.profileClosed.emit();event.accept();return
        super().keyPressEvent(event)
