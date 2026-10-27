"""HTML-inspired native workspace: floating cards, direct sketching and CAD previews."""
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
from math import atan2, degrees, asin
import numpy as np
import cadquery as cq
from PySide6.QtCore import Qt, QSize, QTimer, QPoint
from PySide6.QtGui import QIcon, QVector3D, QColor
from PySide6.QtWidgets import (QWidget,QFrame,QVBoxLayout,QHBoxLayout,QGridLayout,
    QLabel,QPushButton,QToolButton,QComboBox,QDoubleSpinBox,QCheckBox,QStackedWidget,
    QToolBar,QMenu,QButtonGroup,QGraphicsDropShadowEffect,QScrollArea,QLayout,QSizePolicy,QStyle)
from . import interaction as gesture, kernel
from .document import Body


class Studio(QWidget):
    def __init__(self, window):
        super().__init__()
        self.w = window; self.view = window.view
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.addWidget(self.view)
        self.mode=None; self.frame=None; self.support=None; self.points=[]; self.hover=None
        self.await_face=False;self.preview_running=False;self.preview_work=None;self.generation=0;self.last_profile_id=None;self.blend_preview_stamp=None
        self.preview_timer=QTimer(self);self.preview_timer.setSingleShot(True);self.preview_timer.setInterval(180)
        self.preview_timer.timeout.connect(self.refresh_preview)
        self.setObjectName('studio')
        self.top=self.card();row=QHBoxLayout(self.top);row.setContentsMargins(9,9,9,9);row.setSpacing(8)
        self.buttons={}
        for key,label,icon,fn in [
            ('file','Projekt',None,self.file_menu),('sketch','Szkic','newSketch',self.begin_sketch),
            ('extrude','Wyciągnij','extrudeTool',self.begin_extrude),('boolean','Operacje brył','boolTool',self.begin_boolean),
            ('blend','Edytuj krawędzie','modTool',self.begin_blend),('mirror','Lustro','mirrorTool',self.begin_mirror)]:
            button=QToolButton();button.setToolTip(label);button.setText(label)
            if icon:button.setIcon(QIcon(str(Path(__file__).parent/'assets'/(icon+'.png'))))
            else:
                from .window import tool_icon
                button.setIcon(window.style().standardIcon(QStyle.SP_DialogSaveButton))
            button.setIconSize(QSize(38,38));button.setFixedSize(58,58);button.clicked.connect(fn)
            button.setCheckable(key!='file');row.addWidget(button);self.buttons[key]=button
        self.history=self.card();row=QHBoxLayout(self.history);row.setContentsMargins(7,7,7,7)
        for action in [window.undo_action,window.redo_action]:
            b=QToolButton();b.setDefaultAction(action);b.setFixedSize(40,40);row.addWidget(b)
        self.button(row,'Model',lambda:window.model_dock.setVisible(not window.model_dock.isVisible()))
        self.navigation=self.card();grid=QGridLayout(self.navigation);grid.setContentsMargins(9,9,9,9)
        for label,position,view,color in [('Z',(0,1),'XY','#4285e9'),('-X',(1,0),'-YZ','#e45b60'),('3D',(1,1),'iso','#6983a3'),('X',(1,2),'YZ','#e45b60'),('-Y',(2,0),'XZ','#32a56f'),('-Z',(2,1),'-XY','#4285e9'),('Y',(2,2),'-XZ','#32a56f')]:
            b=QPushButton(label);b.setFixedSize(42,42);b.setStyleSheet(f'background:{color};color:white;border-radius:21px;font-weight:700;');b.clicked.connect(lambda checked=False,n=view:self.change_view(n));grid.addWidget(b,*position)
        self.panel=self.card();self.panel.setFixedWidth(298);self.panel_layout=QVBoxLayout(self.panel);self.panel_layout.setContentsMargins(16,16,16,16);self.panel_layout.setSpacing(10)
        self.title=QLabel();self.title.setObjectName('panelTitle');self.panel_layout.addWidget(self.title)
        self.pages=QStackedWidget();self.pages.layout().setSizeConstraint(QLayout.SetNoConstraint);self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);self.pages.setFixedWidth(244);self.scroll.setFrameShape(QFrame.NoFrame);self.scroll.setWidget(self.pages);self.panel_layout.addWidget(self.scroll)
        self.sketch_page=self.build_sketch();self.extrude_page=self.build_extrude();self.boolean_page=self.build_boolean();self.blend_page=self.build_blend();self.mirror_page=self.build_mirror();self.transform_page=self.build_transform()
        for p in [self.sketch_page,self.extrude_page,self.boolean_page,self.blend_page,self.mirror_page,self.transform_page]:self.pages.addWidget(p)
        self.finish_button=QPushButton('Zakończ szkic');self.finish_button.clicked.connect(self.close_tool);self.panel_layout.addWidget(self.finish_button);self.finish_button.hide()
        self.panel.hide()
        self.bottom=self.card();row=QHBoxLayout(self.bottom);row.setContentsMargins(8,7,8,7)
        self.navigation_modes=QButtonGroup(self)
        for name,mode in [('Wybór','select'),('Obrót','orbit'),('Przesuń widok','pan')]:
            b=self.button(row,name,lambda checked=False,m=mode:self.set_mouse_mode(m));b.setCheckable(True);b.setChecked(mode=='select');self.navigation_modes.addButton(b)
        self.multiple=QCheckBox('Wiele');self.multiple.toggled.connect(window.multi_select.setChecked);window.multi_select.toggled.connect(self.multiple.setChecked);row.addWidget(self.multiple)
        self.button(row,'Dopasuj',self.view.fit_all);self.button(row,'Przenieś / obróć bryłę',self.begin_transform)
        self.hint=QLabel('Szkic → płaszczyzna lub ściana → rysowanie myszą → Wyciągnij');self.hint.setObjectName('workspaceHint');self.hint.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hint.setParent(self)
        self.view.setMouseTracking(True)
        self.view.sketchClicked.connect(self.sketch_click);self.view.sketchMoved.connect(self.sketch_move);self.view.faceClicked.connect(self.face_clicked)
        self.view.handleDragged.connect(self.drag_extrusion)
        self.view.profileClicked.connect(self.profile_clicked)
        self.view.editCancelled.connect(self.cancel_points)
        self.view.profileClosed.connect(self.finish_polyline)
        self.view.setBackgroundColor('#edf2f8')
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.context_menu)
        window.documentChanged.connect(self.document_changed)
        self.document_changed()

    def card(self):
        frame=QFrame(self);frame.setObjectName('floatingCard')
        shadow=QGraphicsDropShadowEffect(frame);shadow.setBlurRadius(22);shadow.setOffset(0,5);shadow.setColor(QColor(37,63,90,37));frame.setGraphicsEffect(shadow)
        return frame

    def button(self, layout, text, fn):
        b=QPushButton(text);b.clicked.connect(fn);layout.addWidget(b);return b

    def label(self,layout,text):
        q=QLabel(text);q.setWordWrap(True);layout.addWidget(q);return q

    def combo(self,layout,label,items):
        self.label(layout,label);c=QComboBox()
        for text,data in items:c.addItem(text,data)
        layout.addWidget(c);return c

    def spin(self,layout,label,value=0,minimum=-1e6):
        self.label(layout,label);s=QDoubleSpinBox();s.setRange(minimum,1e6);s.setDecimals(3);s.setValue(value);s.setSuffix(' mm');layout.addWidget(s);return s

    def row_buttons(self,layout,apply,close=True):
        row=QHBoxLayout();self.button(row,'Zastosuj',apply)
        if close:self.button(row,'Zamknij',self.close_tool)
        layout.addLayout(row)

    def build_sketch(self):
        page=QWidget();v=QVBoxLayout(page);v.setContentsMargins(0,0,0,0)
        self.plane=self.combo(v,'Płaszczyzna',[('XY — z góry','XY'),('XZ — z przodu','XZ'),('YZ — z boku','YZ')])
        self.offset=self.spin(v,'Odsunięcie płaszczyzny',0)
        self.plane.currentIndexChanged.connect(self.reset_plane);self.offset.valueChanged.connect(self.reset_plane)
        self.face_button=self.button(v,'Wybierz płaską ścianę bryły',self.choose_face)
        self.plane_status=self.label(v,'')
        self.shape=self.combo(v,'Narzędzie',[('Prostokąt — dwa narożniki','rectangle'),('Prostokąt ze środka','center_rectangle'),('Okrąg — środek i promień','circle'),('Elipsa — środek i promienie','ellipse'),('Wielokąt foremny','polygon'),('Fasolka — 3 punkty','slot'),('Profil łamany — zamknięty','polyline'),('Odcinek','line'),('Łuk przez 3 punkty','arc')])
        self.shape.hide()
        grid=QGridLayout();self.sketch_tools=QButtonGroup(self)
        for i,(label,kind,icon) in enumerate([('Prostokąt','rectangle','box'),('Ze środka','center_rectangle','box'),('Okrąg','circle','circle'),('Elipsa','ellipse','circle'),('Wielokąt','polygon','sketch'),('Fasolka','slot','round'),('Łamana','polyline','sketch'),('Odcinek','line','move'),('Łuk','arc','round')]):
            from .window import tool_icon
            b=QToolButton();b.setText(label);b.setIcon(tool_icon(icon,'#426381'));b.setIconSize(QSize(24,24));b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon);b.setCheckable(True);b.setChecked(i==0);b.setMinimumSize(70,58)
            b.clicked.connect(lambda checked=False,k=kind:self.shape.setCurrentIndex(self.shape.findData(k)));self.sketch_tools.addButton(b);grid.addWidget(b,i//3,i%3)
        v.addLayout(grid)
        self.shape.currentIndexChanged.connect(self.cancel_points)
        self.sides=self.spin(v,'Liczba boków wielokąta',6,3);self.sides.setSuffix('');self.sides.setDecimals(0);self.sides.setMaximum(128)
        self.snap=QCheckBox('Przyciągaj do siatki');self.snap.setChecked(True);v.addWidget(self.snap)
        self.step=self.spin(v,'Krok siatki',1,.01)
        self.dimensions=self.label(v,'Kliknij pierwszy punkt w widoku.')
        self.exact_u=self.spin(v,'Dokładny wymiar U / promień',20,.001)
        self.exact_v=self.spin(v,'Dokładny wymiar V / promień',10,.001)
        self.button(v,'Utwórz z wymiarów od pierwszego punktu',self.dimensioned_profile)
        self.button(v,'Zamknij profil łamany',self.finish_polyline)
        self.button(v,'Cofnij punkt',self.undo_point)
        self.button(v,'Zakończ szkic',self.close_tool)
        self.label(v,'Figury: kliknij punkty w widoku. Profil łamany: kliknij kolejne wierzchołki i pierwszy punkt lub „Zamknij profil”. Esc anuluje bieżącą figurę. Rolka przybliża.')
        return page

    def build_extrude(self):
        page=QWidget();v=QVBoxLayout(page);v.setContentsMargins(0,0,0,0)
        self.profile_label=self.label(v,'Kliknij profil szkicu w widoku 3D.')
        self.operation=self.combo(v,'Operacja',[('Nowa bryła','new'),('Połącz z bryłą','union'),('Wytnij w bryle','subtract'),('Część wspólna','intersect')])
        self.target=self.combo(v,'Bryła docelowa',[])
        self.depth=self.spin(v,'Odległość wyciągnięcia',20)
        self.symmetric=QCheckBox('Symetrycznie względem szkicu');v.addWidget(self.symmetric)
        self.include_holes=QCheckBox('Profile wewnętrzne jako otwory');self.include_holes.setChecked(True);v.addWidget(self.include_holes);self.include_holes.toggled.connect(self.request_preview)
        self.label(v,'Przeciągnij pomarańczową strzałkę w widoku albo wpisz odległość. Dodatnia głębokość wycinania jest skierowana w głąb ściany.')
        self.row_buttons(v,self.apply_extrude)
        self.preview_status=self.label(v,'Zielony podgląd: dodawanie. Pomarańczowy: wycinanie.')
        for control in [self.operation,self.target]:control.currentIndexChanged.connect(self.request_preview)
        self.depth.valueChanged.connect(self.request_preview);self.symmetric.toggled.connect(self.request_preview)
        return page

    def build_boolean(self):
        page=QWidget();v=QVBoxLayout(page);v.setContentsMargins(0,0,0,0)
        self.bool_mode=self.combo(v,'Operacja',[('Połącz','union'),('Wytnij','subtract'),('Część wspólna','intersect')])
        self.bool_status=self.label(v,'')
        self.label(v,'Kliknij bryłę bazową, a potem bryły narzędziowe. „Wiele” jest włączone automatycznie. Pierwsza zaznaczona bryła jest bazą.')
        self.row_buttons(v,lambda:self.w.combine(self.bool_mode.currentData()))
        self.button(v,'Odznacz wszystko',self.w.clear_selection)
        return page

    def build_blend(self):
        page=QWidget();v=QVBoxLayout(page);v.setContentsMargins(0,0,0,0)
        # Reuse the existing native edge controls and exact CAD callbacks.
        self.w.blend_panel.setParent(page);self.w.blend_panel.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Maximum);v.addWidget(self.w.blend_panel);self.w.blend_panel.show()
        self.blend_preview_button=self.button(v,'Podgląd zaokrąglenia / fazy',self.preview_blend)
        self.blend_status=self.label(v,'Podgląd jest liczony przez silnik CAD, bez zmieniania modelu.')
        self.w.blend_type.currentIndexChanged.connect(self.update_edge_handle)
        self.w.blend_size.valueChanged.connect(self.update_edge_handle)
        self.label(v,'Kliknij jedną krawędź. Włącz „Wiele”, aby dodać następne. Pomarańczową strzałką ustaw promień lub fazę.')
        return page

    def build_mirror(self):
        page=QWidget();v=QVBoxLayout(page);v.setContentsMargins(0,0,0,0)
        self.mirror_plane=self.combo(v,'Płaszczyzna odbicia',[('XY','XY'),('XZ','XZ'),('YZ','YZ')]);self.label(v,'Zaznacz bryłę w widoku. Odbicie utworzy nowy obiekt.')
        self.row_buttons(v,self.apply_mirror);return page

    def resizeEvent(self,event):
        super().resizeEvent(event);self.arrange()

    def arrange(self):
        self.top.adjustSize();self.top.move(18,18)
        self.navigation.adjustSize();self.navigation.move(self.width()-self.navigation.width()-18,18)
        self.history.adjustSize();self.history.move(max(self.top.geometry().right()+12,self.navigation.x()-self.history.width()-12),20)
        page=self.pages.currentWidget();page_height=page.layout().totalHeightForWidth(244) if page.hasHeightForWidth() else page.sizeHint().height();self.pages.setFixedHeight(page_height);self.scroll.setFixedHeight(min(max(200,self.height()-260),page_height+10));self.panel.adjustSize();self.panel.move(18,105)
        self.panel.setMaximumHeight(max(200,self.height()-200))
        self.bottom.adjustSize();self.bottom.move(max(18,(self.width()-self.bottom.width())//2),self.height()-self.bottom.height()-20)
        self.hint.adjustSize();self.hint.move(max(330,(self.width()-self.hint.width())//2),self.height()-85)
        for q in [self.top,self.navigation,self.history,self.panel,self.bottom,self.hint]:q.raise_()

    def open_tool(self,mode,page,title):
        if self.w.busy:return False
        self.close_tool();self.mode=mode;self.finish_button.setVisible(mode=='sketch');self.pages.setCurrentWidget(page);self.title.setText(title);self.panel.show()
        
        if mode in self.buttons:self.buttons[mode].setChecked(True)
        self.set_mouse_mode('select');self.arrange();return True

    def close_tool(self):
        if self.w.busy:return
        self.generation+=1;self.preview_timer.stop();self.view.clear_preview();self.view.set_handle(None)
        self.view.sketch_mode=False;self.view.face_mode=False;self.view.profile_mode=False;self.view.edge_mode=False;self.view.set_sketch_plane(None)
        self.points=[];self.hover=None;self.await_face=False;self.mode=None;self.panel.hide()
        self.w.edges.clear();self.w.refresh()
        for b in self.buttons.values():b.setChecked(False)
        self.hint.setText('Szkic → płaszczyzna lub ściana → rysowanie myszą → Wyciągnij');self.arrange()

    def set_mouse_mode(self,mode):
        self.w.set_mouse_mode(mode)
        for b,m in zip(self.navigation_modes.buttons(),['select','orbit','pan']):b.setChecked(m==mode)

    def file_menu(self):
        menu=QMenu(self)
        for action in self.w.menuBar().actions()[0].menu().actions():menu.addAction(action)
        menu.addSeparator()
        menu.addAction('Dodaj prostopadłościan',self.w.add_box);menu.addAction('Dodaj walec',self.w.add_cylinder)
        menu.addAction('Szkic z wymiarów',self.w.add_sketch)
        menu.exec(self.top.mapToGlobal(QPoint(0,self.top.height())))

    def context_menu(self,position):
        if self.w.busy:return
        menu=QMenu(self)
        for label,fn in [('Szkic',self.begin_sketch),('Wyciągnij profil',self.begin_extrude),('Edytuj krawędzie',self.begin_blend),('Przenieś / obróć',self.begin_transform),('Duplikuj',self.w.duplicate_body),('Usuń',self.w.delete_selected),('Dopasuj widok',self.view.fit_all)]:menu.addAction(label,fn)
        menu.exec(self.view.mapToGlobal(position))

    def change_view(self,name):
        self.view.set_view(name)

    def begin_sketch(self):
        if self.open_tool('sketch',self.sketch_page,'UTWÓRZ SZKIC'):
            self.reset_plane()

    def reset_plane(self,*args):
        if self.mode!='sketch':return
        self.frame=gesture.frame_for(self.plane.currentData(),self.offset.value());self.support=None
        self.plane_status.setText('Płaszczyzna '+self.plane.currentData());self.activate_plane()

    def activate_plane(self):
        self.points=[];self.hover=None;self.view.clear_preview();self.await_face=False;self.view.face_mode=False;self.view.sketch_mode=True
        self.set_mouse_mode('select')
        normal=np.array(self.frame[2]);self.view.setCameraPosition(elevation=degrees(asin(float(normal[2]))),azimuth=degrees(atan2(float(normal[1]),float(normal[0]))))
        self.view.opts['center']=QVector3D(*self.frame[0]);self.view.set_sketch_plane(self.frame);self.view.update()
        self.dimensions.setText('Kliknij pierwszy punkt w widoku.');self.hint.setText('Rysuj w widoku: klikaj punkty figury. Esc anuluje figurę.');self.arrange()

    def choose_face(self):
        self.points=[];self.view.clear_preview();self.view.sketch_mode=False;self.view.face_mode=True;self.await_face=True;self.view.set_view('iso');self.view.fit_all()
        self.plane_status.setText('Kliknij płaską ścianę bryły w widoku 3D.')

    def face_clicked(self,identifier,point):
        if self.mode!='sketch' or not self.await_face or self.w.busy:return
        body=self.w.document.get(identifier)
        try:self.frame=gesture.face_frame(body,point)
        except kernel.CadError as exc:self.plane_status.setText(str(exc));return
        self.support=identifier;self.plane_status.setText('Ściana: '+body.name);self.activate_plane()

    def uv(self,x,y):
        ray=self.view._ray(x,y)
        q=gesture.plane_point(self.frame,*ray) if ray else None
        if q and self.snap.isChecked():q=tuple(round(v/self.step.value())*self.step.value() for v in q)
        return q

    def sketch_move(self,x,y):
        if self.mode!='sketch' or not self.view.sketch_mode or self.w.busy:return
        q=self.uv(x,y)
        if q is None:return
        self.hover=q
        if self.points:
            a=self.points[0];self.dimensions.setText(f'U: {q[0]:.2f}   V: {q[1]:.2f} mm\nΔU: {q[0]-a[0]:.2f}   ΔV: {q[1]-a[1]:.2f} mm')
            self.draw_sketch_preview()
        else:self.dimensions.setText(f'U: {q[0]:.2f}   V: {q[1]:.2f} mm\nKliknij pierwszy punkt.')

    def sketch_click(self,x,y):
        if self.w.busy or self.mode!='sketch':return
        q=self.uv(x,y)
        if q is None:return
        kind=self.shape.currentData()
        if kind=='polyline' and len(self.points)>=3:
            first=self.view.project_points(np.array([gesture.world_point(self.frame,self.points[0])]))[0][0]
            if np.linalg.norm(first-[x,y])<10:self.finish_polyline();return
        self.points.append(q)
        needed=3 if kind in ('arc','slot') else 2
        if kind!='polyline' and len(self.points)>=needed:self.commit_profile(kind,self.points)
        else:self.dimensions.setText(f'Punkty: {len(self.points)}. Kliknij kolejny punkt.');self.draw_sketch_preview()

    def draw_sketch_preview(self):
        pts=self.points+([self.hover] if self.hover and self.hover!=self.points[-1] else [])
        if len(pts)<2:return
        kind=self.shape.currentData()
        try:
            if kind=='polyline' or (kind in ('slot','arc') and len(pts)<3):
                self.view.show_lines(np.array([gesture.world_point(self.frame,q) for q in pts]),'#1787de')
            else:
                wire=gesture.profile(kind,self.frame,pts,self.sides.value());self.view.show_wire(wire,'#1787de')
        except Exception:pass  # Incomplete zero-size draft curves are expected while moving the mouse.

    def commit_profile(self,kind,points):
        frame=self.frame;support=self.support;sides=self.sides.value();plane=self.plane.currentData();points=tuple(points)
        name='Szkic — '+self.shape.itemText(self.shape.findData(kind)).split(' — ')[0]
        def build():return Body(name,gesture.profile(kind,frame,points,sides),'sketch',plane,frame=frame,support_id=support).prepared()
        def apply(body):
            self.w.add_prepared(body);self.points=[];self.hover=None;self.view.clear_preview();self.dimensions.setText('Profil zapisany. Rysuj kolejną figurę lub zakończ szkic.')
        self.w.run_operation('Rysowanie szkicu',build,apply)

    def dimensioned_profile(self):
        if not self.points:self.dimensions.setText('Najpierw kliknij punkt początkowy w widoku.');return
        kind=self.shape.currentData()
        if kind in ('polyline','arc','slot'):
            self.dimensions.setText('To narzędzie wymaga wskazania kolejnych punktów w widoku.');return
        a=self.points[0];u=self.exact_u.value();v=self.exact_v.value()
        self.commit_profile(kind,[a,(a[0]+u,a[1]+(0 if kind in ('circle','polygon','line') else v))])

    def finish_polyline(self):
        if self.mode=='sketch' and self.shape.currentData()=='polyline':
            if len(self.points)<3:self.dimensions.setText('Wskaż co najmniej 3 wierzchołki.');return
            self.commit_profile('polyline',self.points)

    def undo_point(self):
        if self.points:self.points.pop()
        self.view.clear_preview()
        if self.points:self.draw_sketch_preview()

    def cancel_points(self,*args):
        if self.mode=='sketch':
            self.points=[];self.hover=None;self.view.clear_preview();self.dimensions.setText('Kliknij pierwszy punkt w widoku.')
        elif self.mode:self.close_tool()

    def begin_extrude(self):
        if self.open_tool('extrude',self.extrude_page,'WYCIĄGNIĘCIE'):
            self.view.profile_mode=True;self.view.set_view('iso');self.request_preview()

    def selected_profile(self):
        return next((self.w.document.get(i) for i in self.w.selected if self.w.document.get(i) and self.w.document.get(i).kind=='sketch'),None)

    def profile_clicked(self,identifier):
        if self.mode=='extrude':self.w.body_clicked(identifier,False)

    def request_preview(self,*args):
        self.generation+=1
        if self.mode in ('extrude','transform'):self.preview_timer.start()

    def refresh_preview(self):
        if self.mode=='transform':self.preview_transform()
        else:self.preview_extrusion()

    def preview_extrusion(self):
        if self.mode!='extrude' or self.w.busy:return
        if self.preview_running:self.preview_timer.start();return
        body=self.selected_profile()
        if not body:self.view.clear_preview();self.view.set_handle(None);return
        gen=self.generation;revision=self.w.document._revision;bodies=self.w.document.bodies;include_holes=self.include_holes.isChecked();distance=self.depth.value();symmetric=self.symmetric.isChecked();cut=self.operation.currentData()=='subtract'
        from .window import Work
        work=Work(lambda:kernel.display_mesh(gesture.extrusion(body,-distance if cut else distance,symmetric,gesture.inner_profiles(body,bodies) if include_holes else [])))
        self.preview_running=True;self.preview_work=work
        def done(mesh):
            self.preview_running=False;self.preview_work=None
            if self.mode!='extrude' or gen!=self.generation or revision!=self.w.document._revision:return
            self.view.show_preview_mesh(mesh,'#ef9a26' if cut else '#3cae80');self.preview_status.setText('Podgląd narzędzia wycinającego' if cut else 'Podgląd wyciągnięcia')
            normal=np.array(body.frame[2] if body.frame else kernel.NORMALS[body.plane]);center=np.array(body.shape.Center().toTuple());d=-distance if cut else distance
            self.view.set_handle(center+normal*d,normal,'extrude')
        def failed(message):
            self.preview_running=False;self.preview_work=None
            if gen==self.generation and self.mode=='extrude':self.view.clear_preview();self.preview_status.setText(message)
        work.signals.done.connect(done);work.signals.failed.connect(failed);self.w.pool.start(work)

    def drag_extrusion(self,kind,delta):
        if self.w.busy:return
        if kind=='extrude' and self.mode=='extrude':
            sign=-1 if self.operation.currentData()=='subtract' else 1
            self.depth.setValue(self.depth.value()+delta*sign)
        elif kind=='transform' and self.mode=='transform':
            control=self.move_fields[self.move_axis.currentIndex()];control.setValue(control.value()+delta)
        elif kind=='blend' and self.mode=='blend':self.w.blend_size.setValue(max(.001,self.w.blend_size.value()+delta))

    def apply_extrude(self):
        body=self.selected_profile()
        if not body:self.preview_status.setText('Najpierw kliknij profil szkicu.');return
        mode=self.operation.currentData();target=self.w.document.get(self.target.currentData());distance=self.depth.value();symmetric=self.symmetric.isChecked()
        bodies=self.w.document.bodies;include_holes=self.include_holes.isChecked()
        def build():
            holes=gesture.inner_profiles(body,bodies) if include_holes else []
            consumed={body.id,*[b.id for b in holes]}
            shape=gesture.apply_profile(body,distance,mode,target,symmetric,holes)
            result=Body('Wyciągnięcie',shape).prepared() if mode=='new' else target.changed(shape)
            changed=[replace(b,visible=False) if b.id in consumed else result if mode!='new' and b.id==target.id else b for b in bodies]
            if mode=='new':changed.append(result)
            return changed,result.id
        def apply(value):
            changed,identifier=value;self.w.document.commit(changed);self.w.selected=[identifier]
            self.view.clear_preview();self.view.set_handle(None)
        self.generation+=1
        self.w.run_operation('Wyciąganie / wycinanie',build,apply,True)

    def build_transform(self):
        page=QWidget();v=QVBoxLayout(page);v.setContentsMargins(0,0,0,0)
        self.move_axis=self.combo(v,'Oś uchwytu',[('X','X'),('Y','Y'),('Z','Z')])
        self.move_axis.currentIndexChanged.connect(self.request_preview)
        self.move_fields=[self.spin(v,'Przesunięcie '+name,0) for name in ['X','Y','Z']]
        self.rotate_fields=[self.spin(v,'Obrót '+name,0) for name in ['X','Y','Z']]
        for control in self.rotate_fields:control.setSuffix(' °')
        for control in self.move_fields+self.rotate_fields:control.valueChanged.connect(self.request_preview)
        self.label(v,'Wybierz bryłę i oś. Przeciągaj pomarańczowy uchwyt lub ustaw wartości. Podgląd nie zmienia modelu do „Zastosuj”.')
        self.row_buttons(v,self.apply_transform)
        return page

    def begin_transform(self):
        if self.open_tool('transform',self.transform_page,'PRZENIEŚ / OBRÓĆ BRYŁĘ'):
            for c in self.move_fields+self.rotate_fields:c.setValue(0)
            self.request_preview()

    def transform_target(self):
        return next((self.w.document.get(i) for i in self.w.selected if self.w.document.get(i) and self.w.document.get(i).kind=='solid'),None)

    def preview_transform(self):
        if self.mode!='transform' or self.w.busy:return
        if self.preview_running:self.preview_timer.start();return
        body=self.transform_target()
        if not body:self.view.clear_preview();self.view.set_handle(None);return
        move=tuple(c.value() for c in self.move_fields);rotate=tuple(c.value() for c in self.rotate_fields)
        gen=self.generation;revision=self.w.document._revision;axis=np.eye(3)[self.move_axis.currentIndex()]
        from .window import Work
        work=Work(lambda:kernel.display_mesh(kernel.transform(body.shape,move,rotate)))
        self.preview_running=True;self.preview_work=work
        def done(mesh):
            self.preview_running=False;self.preview_work=None
            if self.mode!='transform' or gen!=self.generation or revision!=self.w.document._revision:return
            self.view.show_preview_mesh(mesh,'#36a78c');point=np.array(mesh.center)+axis*max(5,mesh.size*.6)
            self.view.set_handle(point,axis,'transform')
        def failed(message):
            self.preview_running=False;self.preview_work=None
            if gen==self.generation:self.view.clear_preview();self.w.statusBar().showMessage(message)
        work.signals.done.connect(done);work.signals.failed.connect(failed);self.w.pool.start(work)

    def apply_transform(self):
        body=self.transform_target()
        if not body:self.w.statusBar().showMessage('Kliknij bryłę w widoku 3D.');return
        move=tuple(c.value() for c in self.move_fields);rotate=tuple(c.value() for c in self.rotate_fields)
        self.generation+=1
        def apply(result):
            self.w.replace_body(body,result)
            for c in self.move_fields+self.rotate_fields:c.setValue(0)
        self.w.run_operation('Przenoszenie / obracanie',lambda:body.changed(kernel.transform(body.shape,move,rotate)),apply,True)

    def begin_boolean(self):
        if self.open_tool('boolean',self.boolean_page,'OPERACJE NA BRYŁACH'):self.multiple.setChecked(True);self.document_changed()

    def begin_blend(self):
        if self.open_tool('blend',self.blend_page,'EDYTUJ BRYŁĘ'):
            self.w.blend_panel.show();self.view.edge_mode=True;self.update_edge_handle()

    def update_edge_handle(self,*args):
        if self.mode!='blend':return
        stamp=self.blend_stamp()
        if self.blend_preview_stamp is not None and stamp!=self.blend_preview_stamp:
            self.generation+=1;self.view.clear_preview();self.blend_preview_stamp=None
        for identifier,ids in self.w.edges.items():
            body=self.w.document.get(identifier)
            if body and ids:
                edge=body.shape.Edges()[next(iter(ids))];center=np.array(edge.Center().toTuple())
                self.view.set_handle(center+np.array([0,0,self.w.blend_size.value()]),np.array([0,0,1]),'blend');return
        self.view.set_handle(None)

    def blend_stamp(self):
        return (self.w.document._revision,tuple((i,tuple(sorted(ids))) for i,ids in self.w.edges.items()),self.w.blend_size.value(),self.w.blend_type.currentData())

    def preview_blend(self):
        if self.w.busy or self.preview_running:return
        if len(self.w.edges)!=1 or not next(iter(self.w.edges.values()),None):
            self.blend_status.setText('Kliknij krawędzie jednej bryły.');return
        identifier,ids=next(iter(self.w.edges.items()));body=self.w.document.get(identifier)
        if not body or body.kind!='solid':return
        from .window import Work
        size=self.w.blend_size.value();kind=self.w.blend_type.currentData();ids=tuple(ids)
        self.generation+=1;gen=self.generation;self.blend_preview_stamp=self.blend_stamp()
        self.preview_running=True;self.blend_status.setText('Obliczanie podglądu…')
        work=Work(lambda:kernel.display_mesh(kernel.blend(body.shape,ids,size,kind)));self.preview_work=work
        def done(mesh):
            self.preview_running=False;self.preview_work=None
            if self.mode=='blend' and gen==self.generation:
                self.view.show_blend_preview(identifier,mesh);self.blend_status.setText('Podgląd gotowy. Zastosuj, aby zapisać wynik.')
        def failed(message):
            self.preview_running=False;self.preview_work=None
            if gen==self.generation:self.view.clear_preview();self.blend_status.setText(message)
        work.signals.done.connect(done);work.signals.failed.connect(failed);self.w.pool.start(work)

    def begin_mirror(self):self.open_tool('mirror',self.mirror_page,'ODBICIE LUSTRZANE')

    def apply_mirror(self):
        body=self.w.selected_body()
        if body:
            plane=self.mirror_plane.currentData();self.w.run_operation('Odbicie lustrzane',lambda:Body(body.name+' — odbicie',kernel.mirror(body.shape,plane)).prepared(),self.w.add_prepared,True)

    def document_changed(self):
        if not hasattr(self,'target'):return
        selected=self.target.currentData();self.target.blockSignals(True);self.target.clear()
        for b in self.w.document.bodies:
            if b.kind=='solid':self.target.addItem(b.name,b.id)
        profile=self.selected_profile()
        if profile and profile.id!=self.last_profile_id and profile.support_id:selected=profile.support_id
        self.last_profile_id=profile.id if profile else None
        i=self.target.findData(selected)
        if i>=0:self.target.setCurrentIndex(i)
        self.target.blockSignals(False)
        self.profile_label.setText('Profil: '+profile.name if profile else 'Kliknij profil szkicu w widoku 3D.')
        names=[self.w.document.get(i).name for i in self.w.selected if self.w.document.get(i) and self.w.document.get(i).kind=='solid']
        self.bool_status.setText(('Baza: '+names[0]+'\nNarzędzia: '+', '.join(names[1:])) if names else 'Kliknij bryłę bazową.')
        self.top.setEnabled(not self.w.busy);self.panel.setEnabled(not self.w.busy)
        if self.mode in ('extrude','transform'):self.request_preview()
        if self.mode=='blend':self.update_edge_handle()
