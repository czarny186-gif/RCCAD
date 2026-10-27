"""Native Qt/OpenGL viewport with picking against displayed CAD edge curves."""
from __future__ import annotations
import numpy as np
import pyqtgraph as pg
import pyqtgraph.opengl as gl
from pyqtgraph.opengl import shaders
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QVector3D
from .document import Body


class CadView(gl.GLViewWidget):
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
                        float diffuse = max(0.0, dot(normalize(v_normal), normalize(vec3(0.3, 0.6, 1.0))));
                        gl_FragColor = vec4(v_color.rgb * (0.58 + 0.42 * diffuse), v_color.a);
                    }
                """),
            ])
        self.setBackgroundColor('#edf1f5')
        self.setCameraPosition(distance=120, elevation=25, azimuth=-55)
        grid = gl.GLGridItem()
        grid.setSize(200, 200)
        grid.setSpacing(10, 10)
        grid.setColor(pg.mkColor('#bac9d8'))
        self.addItem(grid)
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
            mesh = body.mesh
            color = (.30, .53, .76, 1) if body.id in self.selected_bodies else (.64, .67, .72, 1)
            if len(mesh.triangles):
                item = gl.GLMeshItem(vertexes=mesh.vertices, faces=mesh.triangles, smooth=True, color=color, shader='rccad', drawEdges=False)
                item.setGLOptions('opaque')
                self.addItem(item)
                self.model_items.append(item)
            for index, points in mesh.edges.items():
                selected = index in self.selected_edges.get(body.id, set())
                line = gl.GLLinePlotItem(pos=points, color=(1, .48, .05, 1) if selected else (.12, .16, .21, 1), width=3 if selected else 1, antialias=True)
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
        values = {'iso': (25, -55), 'XY': (90, -90), 'XZ': (0, -90), 'YZ': (0, 0)}
        el, az = values[name]
        self.setCameraPosition(elevation=el, azimuth=az)

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
            if not body.visible or not body.mesh or not len(body.mesh.triangles):
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

    def mouseMoveEvent(self, event):
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
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if not self._press:
            return
        x, y, button = self._press
        self._press = None
        if self.mouse_mode != "select" or button != Qt.LeftButton or np.hypot(event.position().x()-x, event.position().y()-y)>4:
            return
        additive = self.multi_select or bool(event.modifiers() & Qt.ShiftModifier)
        if self.edge_mode:
            hit = self.nearest_edge(x,y)
            if hit:
                self.edgeClicked.emit(*hit,additive)
            elif not additive:
                self.selectionCleared.emit()
        else:
            ray=self._ray(x,y)
            hit=self._hit(*ray) if ray else None
            if hit:
                self.bodyClicked.emit(hit[1],additive)
            elif not additive:
                self.selectionCleared.emit()
