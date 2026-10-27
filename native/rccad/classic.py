"""Native reproduction of the HTML new-body design workflow."""
from __future__ import annotations
from dataclasses import replace
from math import atan2,cos,sin,pi,hypot,degrees,asin
import numpy as np
import cadquery as cq
from PySide6.QtCore import Qt,QTimer,QPoint,QRectF,QSize,QEvent,QVariantAnimation,QEasingCurve,QPropertyAnimation,QParallelAnimationGroup
from PySide6.QtGui import QPainter,QPen,QColor,QVector3D
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QPushButton,QToolButton,QMenu,QLineEdit,QDoubleSpinBox,QCheckBox,QApplication,QPlainTextEdit,QGraphicsOpacityEffect,QAbstractSpinBox
from .studio import Studio
from .artwork import HtmlButton,icon,CATALOG
from .document import Body
from . import kernel,interaction as g,workflows as flows


class TextEntry(QPlainTextEdit):
    def text(self):return self.toPlainText()
    def setText(self,value):self.setPlainText(value)
    def setMaxLength(self,length):pass


class Annotations(QWidget):
    def __init__(self,studio):
        super().__init__(studio.view);self.s=studio;self.hits=[]
        self.setAttribute(Qt.WA_TransparentForMouseEvents);self.setAttribute(Qt.WA_TranslucentBackground)
    def paintEvent(self,event):
        s=self.s;self.hits=[];p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        if s.view.plane_mode:
            for name in ['XY','XZ','YZ']:
                xy=s.view.project_points(np.array([g.world_point(g.frame_for(name),(14,0) if name=='YZ' else (0,14))]))[0][0]
                p.setPen(QColor('#355672'));p.drawText(QPoint(round(xy[0]),round(xy[1])),name)
        if s.mode=='sketch' and s.frame and not s.view.plane_mode:
            for b in s.w.document.bodies:
                if b.kind!='sketch' or not b.visible or not b.sketch_data or not s.coplanar(b):continue
                data=b.sketch_data;points=data.get('points',[])
                if not points:continue
                world=np.array([g.world_point(b.frame or g.frame_for(b.plane),q) for q in points]);xy=s.view.project_points(world)[0]
                p.setPen(QPen(QColor('#187fc8'),1));p.setBrush(QColor('white'))
                if data['type']=='construction' and len(xy)>=2:
                    p.setPen(QPen(QColor('#688aa8'),1,Qt.DashLine));p.drawLine(QPoint(*map(round,xy[0])),QPoint(*map(round,xy[-1])))
                    p.setPen(QPen(QColor('#187fc8'),1))
                for q in xy:p.drawEllipse(QPoint(round(q[0]),round(q[1])),3,3)
                text=s.dimension_text(b);q=xy.mean(axis=0)+[0,-18]
                box=QRectF(float(q[0]-p.fontMetrics().horizontalAdvance(text)/2-6),float(q[1]-12),p.fontMetrics().horizontalAdvance(text)+12,23)
                p.setPen(QPen(QColor('#b2c8dd'),1));p.setBrush(QColor(255,255,255,235));p.drawRoundedRect(box,5,5)
                p.setPen(QColor('#1269ae'));p.drawText(box,Qt.AlignCenter,text);self.hits.append((box,b.id))
            if s.hover:
                q=s.view.project_points(np.array([g.world_point(s.frame,s.hover)]))[0][0]
                p.setPen(QPen(QColor('#ed9a21') if s.snap_target else QColor('#1284db'),2));p.setBrush(Qt.NoBrush)
                p.drawRect(QRectF(float(q[0]-5),float(q[1]-5),10,10))
        if s.view.gizmo_handles:
            for i,(point,normal,kind,curve) in enumerate(s.view.gizmo_handles):
                xy=s.view.project_points(np.array([point]))[0][0];p.setPen(QColor(['#e44e55','#24a46a','#347ee6'][i]));p.drawText(QPoint(round(xy[0]+8),round(xy[1]-8)),'XYZ'[i])
        if s.view.handle is not None and not s.view.gizmo_handles:
            point,normal,kind=s.view.handle;xy=s.view.project_points(np.array([point]))[0][0]
            p.setPen(QPen(QColor('white'),2));p.setBrush(QColor('#ec9a24'));p.drawEllipse(QPoint(*map(round,xy)),12,12)
            p.drawLine(QPoint(round(xy[0]-4),round(xy[1])),QPoint(round(xy[0]+4),round(xy[1])))
            p.drawLine(QPoint(round(xy[0]),round(xy[1]-4)),QPoint(round(xy[0]),round(xy[1]+4)))
        p.end()


class ClassicStudio(Studio):
    def __init__(self,window):
        self.classic_ready=False;self.dim_active=False;self.edit_id=None;self.snap_target=None;self.snap_cache=[];self._snap_revision=-1;self.last_pointer=(500,300);self._last_revision=0;self.transform_mode="move";self._body_hashes={};self.live_regions=[];self.region_selected=[];self.region_revision=None;self.mirror_source=None;self.mirror_frame=None
        super().__init__(window)
        # All artwork is original: the SVG stroke properties come from the HTML CSS.
        row=self.top.layout();row.setContentsMargins(0,0,0,0);row.setSpacing(8)
        self.top.setGraphicsEffect(None);self.top.setStyleSheet('QFrame#floatingCard {background:transparent;border:0;}')
        mapping={'file':'fileTool','sketch':'newSketch','extrude':'extrudeTool','boolean':'boolTool','blend':'modTool','mirror':'mirrorTool'}
        callbacks={'file':self.file_menu,'sketch':self.begin_sketch,'extrude':self.begin_extrude,'boolean':self.begin_boolean,'blend':self.begin_blend,'mirror':self.begin_mirror}
        for key,name in mapping.items():
            old=self.buttons[key];index=row.indexOf(old);row.removeWidget(old);old.hide();old.deleteLater()
            b=HtmlButton(name);b.setCheckable(True);b.clicked.connect(callbacks[key]);row.insertWidget(index,b);self.buttons[key]=b
        for i,action in enumerate([window.undo_action,window.redo_action]):
            b=self.history.layout().itemAt(i).widget();b.setIcon(icon('undoBtn' if i==0 else 'redoBtn'));b.setText('');b.setIconSize(QSize(23,23));b.setStyleSheet('QToolButton {border-radius:20px;background:white;border:1px solid #bdcbd8;}')
        self.history.layout().itemAt(2).widget().hide()
        self.history.setStyleSheet('QFrame#floatingCard {background:transparent;border:0;}');self.history.setGraphicsEffect(None)
        self.cube_buttons={};mapping={'Z':'XY','-Z':'-XY','-X':'-YZ','X':'YZ','-Y':'-XZ','Y':'XZ','3D':'iso'}
        for button in self.navigation.findChildren(QPushButton):
            key=button.text();self.cube_buttons[mapping[key]]=button;button.setFixedSize(36,36)
            button.clicked.disconnect();button.clicked.connect(lambda checked=False,n=mapping[key]:self.change_view(n))
            button.setText(key.replace('-','−'));color='#4589e7' if 'Z' in key else '#dc5658' if 'X' in key else '#39a56d' if 'Y' in key else '#677e99'
            button.setProperty('cubeColor',color);button.setStyleSheet(f'background:{color};color:white;border-radius:18px;font-weight:700;')
        self.plane_toggle=HtmlButton('planesToggle',size=40);self.plane_toggle.setCheckable(True);self.plane_toggle.setStyleSheet('QToolButton {background:white;border-color:#e4b9b9;} QToolButton:checked {background:#324c68;} QToolButton:hover {background:#080808;}');self.plane_toggle.clicked.connect(self.toggle_planes);self.history.layout().addWidget(self.plane_toggle)
        self.home=QPushButton('⌂');self.home.setFixedSize(36,36);self.home.setStyleSheet('font-size:22px;color:#496780;background:white;border:1px solid #cbd9e6;border-radius:9px;');self.home.clicked.connect(self.home_view);self.history.layout().addWidget(self.home)
        for i in range(self.bottom.layout().count()):
            item=self.bottom.layout().itemAt(i)
            if item.widget():item.widget().hide()
        for label,mode,name in [('Przesuń','move','moveTool'),('Obróć','rotate','rotateTool')]:
            b=HtmlButton(name,size=42);b.clicked.connect(lambda checked=False,m=mode:self.begin_transform(m));self.bottom.layout().addWidget(b)
        self.toolbox=self.card();tools=QVBoxLayout(self.toolbox);tools.setContentsMargins(7,7,7,7);tools.setSpacing(7)
        self.classic_tools={}
        for name,kind in [('line','line'),('rect','rectangle'),('circle','circle'),('text','text'),('ellipse','ellipse'),('slot','slot'),('polygon','polygon'),('arc','arc'),('point','point'),('construction','construction'),('measure','measure'),('trim','trim')]:
            button=HtmlButton(name,size=42);button.setCheckable(True);button.clicked.connect(lambda checked=False,k=kind:self.choose_shape(k));tools.addWidget(button);self.classic_tools[kind]=button
            if name in ('rect','circle','line'):
                menu=QMenu(button)
                entries={'rect':[('2 narożniki','rectangle'),('Od środka','center_rectangle'),('3 punkty','rect3')],'circle':[('Środek + promień','circle'),('Styczny do 2 elementów','circleTangent2'),('Od 2 punktów średnicy','circle2'),('Od 3 punktów','circle3')],'line':[('Odcinek','line'),('Łamana zamknięta','polyline')]}[name]
                for title,value in entries:menu.addAction(title,lambda checked=False,k=value:self.choose_shape(k))
                button.setMenu(menu);button.setPopupMode(QToolButton.MenuButtonPopup)
                if name in ('rect','circle'):button.setFixedWidth(49)
                menu.aboutToShow.connect(lambda b=button,m=menu:QTimer.singleShot(0,lambda:m.move(b.mapToGlobal(QPoint(b.width()+8,0)))))
        for title,value in [('Prostokąt 3-punktowy','rect3'),('Okrąg od średnicy','circle2'),('Okrąg przez 3 punkty','circle3'),('Okrąg styczny','circleTangent2'),('Punkt','point'),('Linia konstrukcyjna','construction'),('Wymiar','measure'),('Nożyczki','trim'),('Tekst','text')]:
            if self.shape.findData(value)<0:self.shape.addItem(title,value)
        self.shape.currentIndexChanged.connect(self.sync_tools)
        self.toolbox.hide()
        self.inline=self.card();inline=QVBoxLayout(self.inline);inline.setContentsMargins(12,10,12,10)
        form=QFormLayout();self.inline_u=QLabel('Szerokość (mm)');self.inline_v=QLabel('Wysokość (mm)')
        self.exact_u.setParent(self.inline);self.exact_v.setParent(self.inline);self.exact_u.setRange(.001,1e6);self.exact_v.setRange(-1e6,1e6)
        self.exact_u.setSuffix('');self.exact_v.setSuffix('');self.exact_u.setFixedWidth(110);self.exact_v.setFixedWidth(110)
        form.addRow(self.inline_u,self.exact_u);form.addRow(self.inline_v,self.exact_v);inline.addLayout(form)
        self.inline_sides=QDoubleSpinBox();self.inline_sides.setRange(3,128);self.inline_sides.setDecimals(0);self.inline_sides.setValue(5);form.addRow('Boki wielokąta',self.inline_sides)
        self.text_value=TextEntry();self.text_value.setText('Tekst');self.text_value.setFixedHeight(68);form.addRow('Tekst',self.text_value);self.inline_form=form
        self.text_font=self.combo(inline,'Czcionka',[('Sans (DejaVu)','sans'),('Sans pogrubiona','bold'),('Szeryfowa','serif')])
        self.text_font_label=inline.itemAt(inline.count()-2).widget()
        self.text_align=self.combo(inline,'Wyrównanie',[('Do lewej','left'),('Do środka','center'),('Do prawej','right')])
        self.text_align_label=inline.itemAt(inline.count()-2).widget()
        self.inline_help=QLabel('Tab — następne pole · Enter — zatwierdź');inline.addWidget(self.inline_help)
        buttons=QHBoxLayout();self.button(buttons,'Zastosuj',self.accept_inline);self.button(buttons,'Anuluj',self.cancel_inline);inline.addLayout(buttons);self.inline.hide()
        for c in [self.exact_u,self.exact_v,self.inline_sides]:c.valueChanged.connect(self.inline_changed);c.installEventFilter(self)
        self.text_value.textChanged.connect(self.inline_changed);self.text_value.installEventFilter(self)
        self.text_font.currentIndexChanged.connect(self.inline_changed);self.text_align.currentIndexChanged.connect(self.inline_changed)
        self.direction=self.combo(self.extrude_page.layout(),'Kierunek',[('W jedną stronę','one'),('Symetrycznie w dwie strony','symmetric'),('Dwie strony niezależnie','two')])
        self.second=self.spin(self.extrude_page.layout(),'Druga strona',10,0);self.second.hide();self.symmetric.hide()
        self.direction.currentIndexChanged.connect(self.direction_changed);self.second.valueChanged.connect(self.request_preview)
        self.bool_keep=QCheckBox('Zachowaj bryły-narzędzia');self.boolean_page.layout().insertWidget(2,self.bool_keep)
        self.annotation=Annotations(self);self.annotation.show()
        self.annotation_timer=QTimer(self);self.annotation_timer.setInterval(33);self.annotation_timer.timeout.connect(self.annotation.update)
        self.view.planeClicked.connect(self.select_plane);self.view.pointerMoved.connect(self.pointer_moved);self.view.sketchDoubleClicked.connect(self.edit_dimension_at)
        self.view.editCancelled.disconnect(self.cancel_points);self.view.editCancelled.connect(self.escape)
        self.view.dimensionRequested.connect(self.open_dimensions);self.view.operationRequested.connect(self.accept_operation)
        self.view.camera_animation.valueChanged.connect(lambda value:self.annotation.update())
        self.auto_blend_timer=QTimer(self);self.auto_blend_timer.setSingleShot(True);self.auto_blend_timer.setInterval(180);self.auto_blend_timer.timeout.connect(self.auto_blend)
        self.trim_timer=QTimer(self);self.trim_timer.setSingleShot(True);self.trim_timer.setInterval(70);self.trim_timer.timeout.connect(self.preview_trim);self.trim_data=None;self.trim_key=None
        self._auto_blend_stamp=None;self.preview_timer.setInterval(70);self.depth.setValue(10)
        self.pages.removeWidget(self.mirror_page);self.mirror_page=QWidget();mv=QVBoxLayout(self.mirror_page);mv.setContentsMargins(0,0,0,0)
        self.mirror_status=self.label(mv,'Kliknij obiekt, a następnie płaską ścianę odbicia.')
        self.mirror_keep=QCheckBox('Zachowaj oryginał (kopia)');self.mirror_keep.setChecked(True);mv.addWidget(self.mirror_keep)
        self.mirror_join=QCheckBox('Połącz z oryginałem w jedną bryłę');mv.addWidget(self.mirror_join)
        self.label(mv,'1. Kliknij bryłę lub element szkicu. 2. Kliknij płaską ścianę, względem której ma powstać odbicie. Enter zatwierdza, Esc zamyka.')
        self.button(mv,'Zmień obiekt',self.reset_mirror);self.row_buttons(mv,self.apply_mirror);self.pages.addWidget(self.mirror_page)
        self.mirror_keep.toggled.connect(self.request_preview);self.mirror_join.toggled.connect(self.request_preview)
        self.notice=self.card();self.notice.setObjectName('sketchNotice');notice_layout=QVBoxLayout(self.notice);self.notice_text=QLabel();self.notice_text.setTextFormat(Qt.PlainText);self.notice_text.setWordWrap(True);self.notice_text.setMaximumWidth(340);notice_layout.addWidget(self.notice_text)
        self.notice.setStyleSheet('QFrame#sketchNotice {background:white;border:1px solid #d5b880;border-left:4px solid #e2a23a;border-radius:9px;} QLabel {color:#584a32;padding:4px;}')
        self.notice_opacity=QGraphicsOpacityEffect(self.notice);self.notice.setGraphicsEffect(self.notice_opacity);self.notice.hide();self.last_notice=''
        self.notice_timer=QTimer(self);self.notice_timer.setSingleShot(True);self.notice_timer.setInterval(4800);self.notice_timer.timeout.connect(self.fade_notice)
        self.notice_group=QParallelAnimationGroup(self);self.notice_fade=QPropertyAnimation(self.notice_opacity,b'opacity');self.notice_slide=QPropertyAnimation(self.notice,b'pos');self.notice_group.addAnimation(self.notice_fade);self.notice_group.addAnimation(self.notice_slide)
        # Reuse the CAD controls, but place them in the exact HTML cards.
        old_layout=self.extrude_page.layout()
        for control in [self.operation,self.target,self.direction,self.profile_label,self.preview_status,self.include_holes,self.symmetric,self.depth,self.second]:old_layout.removeWidget(control);control.setParent(self)
        from PySide6.QtWidgets import QVBoxLayout as VLayout
        options=QWidget();ov=VLayout(options);ov.setContentsMargins(0,0,0,0)
        self.label(ov,'Operacja');ov.addWidget(self.operation);self.label(ov,'Kierunek');ov.addWidget(self.direction)
        self.label(ov,'Shift + klik: wybierz kilka profili. Wytnij: dodatnia odległość prowadzi w głąb wybranej ściany. Enter zatwierdza operację.')
        ov.addWidget(self.profile_label);ov.addWidget(self.preview_status)
        self.pages.removeWidget(self.extrude_page);self.extrude_page=options;self.pages.addWidget(options)
        self.target.hide();self.include_holes.hide();self.symmetric.hide()
        self.extrude_values=self.card();ev=QHBoxLayout(self.extrude_values);ev.setContentsMargins(12,12,12,12)
        self.label(ev,'Odległość (mm)');self.depth.setFixedWidth(105);ev.addWidget(self.depth)
        self.second_label=self.label(ev,'Druga strona (mm)');self.second.setFixedWidth(105);ev.addWidget(self.second);self.second_label.hide();self.second.hide()
        self.button(ev,'Zastosuj',self.apply_extrude);self.button(ev,'Anuluj',self.close_tool);self.extrude_values.hide()
        self.transform_values=self.card();tv=QHBoxLayout(self.transform_values);tv.setContentsMargins(10,10,10,10)
        self.transform_caption=self.label(tv,'Kliknij obiekt, aby go zaznaczyć');self.transform_caption.setFixedWidth(175)
        self.transform_groups=[]
        for label,controls in [('Przesunięcie',self.move_fields),('Obrót',self.rotate_fields)]:
            group=QWidget();gr=QHBoxLayout(group);gr.setContentsMargins(0,0,0,0)
            for axis,field in zip('XYZ',controls):field.setParent(group);field.setFixedWidth(74);self.label(gr,axis);gr.addWidget(field)
            tv.addWidget(group);self.transform_groups.append(group)
        self.move_axis.hide();self.button(tv,'Zastosuj',self.apply_transform);self.button(tv,'Zamknij',self.close_tool);self.transform_values.hide()
        self.w.menuBar().hide();self.w.statusBar().hide()
        for field in [self.exact_u,self.exact_v,self.inline_sides,self.depth,self.second,self.w.blend_size,*self.move_fields,*self.rotate_fields]:
            field.setButtonSymbols(QAbstractSpinBox.NoButtons);field.installEventFilter(self)
        self.classic_ready=True;self.toolbox.hide();self.sync_tools();self.arrange()
        self.panel_animation=QVariantAnimation(self);self.panel_animation.setDuration(170);self.panel_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.panel_animation.valueChanged.connect(lambda value:self.panel.move(round(value),self.panel.y()))
        self.view.show_planes(True);self.plane_toggle.setChecked(True);self.annotation_timer.start()
        self.w.setStyleSheet(self.w.styleSheet()+"QFrame#floatingCard QLabel,QFrame#floatingCard QCheckBox,QFrame#floatingCard QComboBox {font-size:12px;color:#29475e;} QDoubleSpinBox {color:#1264b2;font-weight:700;border:1px solid #9ab5d0;border-radius:6px;} QFrame#floatingCard QPushButton {color:#29475e;} QFrame#floatingCard QPushButton:hover {background:#080808;color:white;} QComboBox QAbstractItemView {background:white;color:#254c71;selection-background-color:#080808;selection-color:white;} QPlainTextEdit {background:white;color:#254c71;border:1px solid #b1c5d7;border-radius:6px;padding:6px;} QMenu {background:white;border:1px solid #b2c7db;border-radius:9px;padding:5px;} QMenu::item {padding:8px 11px;color:#29475e;} QMenu::item:selected {background:#080808;color:white;}")

    def arrange(self):
        super().arrange()
        if not self.classic_ready:return
        self.annotation.setGeometry(self.view.rect());self.annotation.raise_()
        self.toolbox.adjustSize();self.toolbox.move(18,80)
        if self.mode in ('sketch','transform'):self.panel.hide()
        width=195 if self.mode=='extrude' else 250 if self.mode=='boolean' else 262
        self.panel.setFixedWidth(width);self.pages.setFixedWidth(width-34)
        page=self.pages.currentWidget();height=page.layout().totalHeightForWidth(width-34) if page.hasHeightForWidth() else page.sizeHint().height()
        self.pages.setFixedHeight(height);self.scroll.setFixedHeight(min(max(180,self.height()-260),height+8));self.panel.adjustSize();self.panel.move(18,170 if self.mode=='extrude' else 88)
        self.extrude_values.adjustSize();self.extrude_values.move(230,170)
        self.transform_values.adjustSize();self.transform_values.move(max(18,(self.width()-self.transform_values.width())//2),self.height()-self.transform_values.height()-100)
        self.hint.hide()
        for q in [self.top,self.history,self.navigation,self.toolbox,self.inline,self.bottom,self.panel,self.extrude_values,self.transform_values]:q.raise_()
        if hasattr(self,'notice'):self.notice.raise_()
        self.toolbox.setMaximumHeight(max(120,self.height()-165))

    def open_tool(self,mode,page,title):
        ok=super().open_tool(mode,page,title)
        if ok and self.classic_ready:
            self.inline.hide();self.toolbox.setVisible(mode=='sketch');self.annotation_timer.start();self.extrude_values.setVisible(mode=='extrude');self.transform_values.setVisible(mode=='transform')
            if mode!='sketch' and self.isVisible():
                self.panel_animation.stop();self.panel_animation.setStartValue(-self.panel.width());self.panel_animation.setEndValue(18.);self.panel_animation.start()
        return ok

    def begin_sketch(self):
        if not self.classic_ready:return super().begin_sketch()
        if self.mode=='sketch':self.close_tool();return
        if self.open_tool('sketch',self.sketch_page,'UTWÓRZ SZKIC'):
            self.frame=None;self.support=None;self.view.sketch_mode=False;self.view.face_mode=False;self.await_face=True
            self.view.show_planes(True);self.plane_toggle.setChecked(True);self.set_mouse_mode('select');self.view.set_view('iso')
            self.toolbox.show();self.panel.hide();self.annotation_timer.start();self.hint.setText('Kliknij płaszczyznę XY / XZ / YZ albo płaską ścianę bryły');self.arrange()

    def select_plane(self,name):
        if self.w.busy:return
        if self.mode!='sketch':self.begin_sketch()
        self.plane.setCurrentIndex(self.plane.findData(name));self.reset_plane()
        if name=='XY':self.view.animate_camera(89.713521,132.971835)

    def activate_plane(self):
        self.view.show_planes(False);self.plane_toggle.setChecked(False);super().activate_plane()
        if self.classic_ready:
            self.panel.hide();self.toolbox.show();self.annotation_timer.start();self.inline.hide();self.dim_active=False
            n=np.asarray(self.frame[2]);self.view.animate_camera(degrees(asin(float(n[2]))),degrees(atan2(float(n[1]),float(n[0]))),self.frame[0])
            if self.support is None:self.view.set_view(self.plane.currentData())
            self.hint.setText('Kliknij punkty figury · Tab: dokładne wymiary · dwuklik wymiaru: edycja · Esc: anuluj')

    def toggle_planes(self):
        if self.mode!='sketch':self.begin_sketch()
        elif self.view.plane_mode:
            self.view.show_planes(False)
            if self.frame:self.activate_plane()
        else:self.view.sketch_mode=False;self.await_face=True;self.view.show_planes(True);self.view.set_view('iso')

    def close_tool(self):
        if self.w.busy:return
        if self.classic_ready:
            self.live_regions=[];self.region_selected=[];self.region_revision=None;self.toolbox.hide();self.inline.hide();self.extrude_values.hide();self.transform_values.hide();self.annotation_timer.stop();self.auto_blend_timer.stop();self.trim_timer.stop();self.view.show_planes(False);self.plane_toggle.setChecked(False);self.multiple.setChecked(False);self.annotation.update();self.dim_active=False;self.edit_id=None
        super().close_tool()

    def change_view(self,name):
        if not self.classic_ready:return super().change_view(name)
        opposite={'XY':'-XY','-XY':'XY','XZ':'-XZ','-XZ':'XZ','YZ':'-YZ','-YZ':'YZ'}
        current=getattr(self,'current_cube','iso')
        if name!='iso' and name.lstrip('-')==current.lstrip('-'):name=opposite[current]
        self.current_cube=name
        if self.mode=='sketch' and name!='iso':
            self.plane.setCurrentIndex(self.plane.findData(name.lstrip('-')));self.reset_plane()
        self.view.set_view(name)
        for key,button in self.cube_buttons.items():
            color=button.property('cubeColor');active=key==name;background='white' if active and name.startswith('-') else '#080808' if active else color
            button.setStyleSheet(f"background:{background};color:{'#080808' if active and name.startswith('-') else 'white'};border-radius:18px;font-weight:700;"+("border:2px solid #aab8c8;" if active else ''))

    def home_view(self):
        if self.w.busy:return
        self.close_tool();self.view.opts['center']=QVector3D(0,0,0);self.view.setCameraPosition(distance=210);self.view.set_view('iso');self.view.show_planes(True);self.plane_toggle.setChecked(True);self.annotation_timer.start()

    def file_menu(self):
        button=self.buttons['file'];button.setChecked(True);button.setDown(True);button.setIcon(icon('fileTool',active=True))
        try:super().file_menu()
        finally:button.setChecked(False);button.setDown(False);button.setIcon(icon('fileTool'))

    def choose_shape(self,kind):
        if self.mode!='sketch':self.begin_sketch()
        self.shape.setCurrentIndex(self.shape.findData(kind));self.sync_tools()
        if kind=='text' and self.frame:
            self.exact_u.setValue(10);self.exact_v.setValue(0);self.open_dimensions(text_only=True)
        self.view.setFocus()

    def sync_tools(self,*args):
        if not self.classic_ready:return
        kind=self.shape.currentData();group={'center_rectangle':'rectangle','rect3':'rectangle','circle2':'circle','circle3':'circle','circleTangent2':'circle','polyline':'line'}.get(kind,kind)
        for value,b in self.classic_tools.items():b.setChecked(value==group)
        self.sides.setValue(self.inline_sides.value())

    def coplanar(self,body):
        if self.frame is None:return False
        other=g.plane_from(body.frame or g.frame_for(body.plane));p=g.plane_from(self.frame)
        return abs(abs(p.zDir.dot(other.zDir))-1)<1e-6 and abs(p.zDir.dot(other.origin.sub(p.origin)))<1e-5

    def context_menu(self,position):
        if self.view._pan_was_dragged:self.view._pan_was_dragged=False;return
        super().context_menu(position)

    def pointer_moved(self,x,y):
        self.last_pointer=(x,y)
        if self.view.plane_mode:self.view.hover_planes(x,y)
        if self.classic_ready and not self.w.busy:
            if self.mode!='sketch':self.view.hover_at(x,y)
            self.annotation.update()

    def rebuild_snaps(self):
        if self._snap_revision==self.w.document._revision:return
        self._snap_revision=self.w.document._revision;self.snap_cache=[];lines=[];circles=[]
        for b in self.w.document.bodies:
            if b.kind!='sketch' or not b.visible:continue
            p=g.plane_from(b.frame or g.frame_for(b.plane));data=b.sketch_data or {}
            for q in data.get('points',[]):self.snap_cache.append(np.array(p.toWorldCoords(tuple(q)).toTuple()))
            if data.get('type')=='circle':
                center=np.array(p.toWorldCoords(tuple(data['points'][0])).toTuple());radius=float(np.linalg.norm(np.array(data['points'][1])-data['points'][0]));circles.append((center,radius,np.array(p.zDir.toTuple())))
            for edge in b.shape.Edges():
                for t in ([0,.25,.5,.75,1] if edge.geomType()!='LINE' else [0,.5,1]):self.snap_cache.append(np.array(edge.positionAt(t).toTuple()))
                if edge.geomType()=='LINE':lines.append((np.array(edge.startPoint().toTuple()),np.array(edge.endPoint().toTuple())))
        # Vectorised segment crossings keep snapping independent of display tessellation.
        lines=lines[-256:];circles=circles[-128:]
        if lines:
            ends=np.asarray(lines);orig=ends[:,0];direction=ends[:,1]-orig
            i,j=np.triu_indices(len(lines),1);u=direction[i];v=direction[j];delta=orig[j]-orig[i];cross=np.cross(u,v);den=(cross*cross).sum(axis=1)
            t=np.divide((np.cross(delta,v)*cross).sum(axis=1),den,out=np.zeros_like(den),where=den>1e-14)
            ss=np.divide((np.cross(delta,u)*cross).sum(axis=1),den,out=np.zeros_like(den),where=den>1e-14)
            p1=orig[i]+u*t[:,None];p2=orig[j]+v*ss[:,None]
            mask=(den>1e-14)&(t>=0)&(t<=1)&(ss>=0)&(ss<=1)&(np.linalg.norm(p1-p2,axis=1)<1e-5)
            self.snap_cache.extend(p1[mask])
            for center,radius,normal in circles:
                offset=orig-center;aa=(direction*direction).sum(axis=1);bb=(offset*direction).sum(axis=1);disc=bb*bb-aa*((offset*offset).sum(axis=1)-radius*radius)
                coplanar=(np.abs(offset@normal)<1e-5)&(np.abs(direction@normal)<1e-5)
                for sign in (-1,1):
                    t=np.divide(-bb+sign*np.sqrt(np.maximum(disc,0)),aa,out=np.zeros_like(aa),where=aa>1e-12)
                    mask=coplanar&(disc>=0)&(aa>1e-12)&(t>=0)&(t<=1);self.snap_cache.extend(orig[mask]+direction[mask]*t[mask,None])
        for i,(a,r,n) in enumerate(circles):
            for b,s,m in circles[i+1:]:
                d=float(np.linalg.norm(b-a))
                if d<1e-8 or d>r+s+1e-8 or d<abs(r-s)-1e-8 or abs(abs(n@m)-1)>1e-6 or abs(n@(b-a))>1e-5:continue
                u=(b-a)/d;x=(r*r-s*s+d*d)/(2*d);h=np.sqrt(max(0,r*r-x*x));v=np.cross(n,u)
                self.snap_cache.extend([a+u*x+v*h,a+u*x-v*h])

    def uv(self,x,y):
        if self.frame is None:return None
        ray=self.view._ray(x,y);q=g.plane_point(self.frame,*ray) if ray else None;self.snap_target=None
        if q is None:return None
        if self.snap.isChecked():
            self.rebuild_snaps();plane=g.plane_from(self.frame)
            candidates=[w for w in self.snap_cache if abs(plane.zDir.dot(cq.Vector(*w).sub(plane.origin)))<1e-5]
            if candidates:
                xy=self.view.project_points(np.array(candidates))[0];dist=np.linalg.norm(xy-[x,y],axis=1);index=int(np.nanargmin(dist))
                if dist[index]<9:
                    point=plane.toLocalCoords(cq.Vector(*map(float,candidates[index])));self.snap_target=tuple(candidates[index]);return (point.x,point.y)
            q=tuple(round(v/self.step.value())*self.step.value() for v in q)
        return q

    def sketch_move(self,x,y):
        if self.dim_active or self.edit_id:return
        if self.shape.currentData()=='trim':self.schedule_trim(x,y);return
        super().sketch_move(x,y)
        if self.shape.currentData()=='circleTangent2' and len(self.points)==4 and self.hover:self.draw_sketch_preview()

    def sketch_click(self,x,y):
        if self.w.busy or self.frame is None or self.dim_active:return
        kind=self.shape.currentData()
        if kind=='measure':self.edit_dimension_at(x,y);return
        if kind=='trim':self.trim_at(x,y);return
        q=self.uv(x,y)
        if q is None:return
        if kind=='text':
            self.commit_profile(kind,[q]);return
        if kind=='point':self.commit_profile(kind,[q]);return
        if kind=='circleTangent2' and len(self.points)<4:
            hit=self.view.nearest_edge(x,y)
            b=self.w.document.get(hit[0]) if hit else None
            if not b or b.kind!='sketch' or not self.coplanar(b):return
            edge=b.shape.Edges()[hit[1]]
            if edge.geomType()!='LINE':self.hint.setText('Wybierz dwie proste, a potem wskaż wielkość okręgu.');return
            plane=g.plane_from(self.frame)
            for endpoint in [edge.startPoint(),edge.endPoint()]:
                p=plane.toLocalCoords(endpoint);self.points.append((p.x,p.y))
            return
        if kind in ('rect3','circle3','circle2','construction','circleTangent2'):
            self.points.append(q);needed=3 if kind in ('rect3','circle3') else 5 if kind=='circleTangent2' else 2
            if len(self.points)==needed:self.commit_profile(kind,self.points)
            return
        super().sketch_click(x,y)

    def draw_sketch_preview(self):
        if not self.points:return
        kind=self.shape.currentData();pts=self.points+([self.hover] if self.hover and self.hover!=self.points[-1] else [])
        if kind in ('rect3','circle3','circle2','construction','circleTangent2','text'):
            try:
                needed=3 if kind in ('rect3','circle3') else 5 if kind=='circleTangent2' else 1 if kind=='text' else 2
                if len(pts)<needed:self.view.show_lines(np.array([g.world_point(self.frame,q) for q in pts]),'#1583d1');return
                shape=g.profile(kind,self.frame,pts,self.inline_sides.value(),self.text_value.text(),self.exact_u.value(),self.exact_v.value(),self.text_font.currentData(),self.text_align.currentData())
                self.view.show_wire(shape,'#1787de')
            except Exception:pass
        else:super().draw_sketch_preview()

    def commit_profile(self,kind,points):
        points=[list(q) for q in points]
        if kind in ('circle2','circle3','circleTangent2'):
            if kind=='circle2':center=(np.array(points[0])+points[1])/2;radius=float(np.linalg.norm(np.array(points[1])-points[0]))/2
            elif kind=='circle3':center,radius=g.circle_three(points)
            else:center,radius=g.tangent_circle(points)
            points=[list(center),[center[0]+radius,center[1]]];kind='circle'
        frame=self.frame;support=self.support;plane=self.plane.currentData();sides=int(self.inline_sides.value())
        axes=None
        if kind=='text':
            anchor=np.array(points[0]);xy=self.view.project_points(np.array([g.world_point(frame,q) for q in [anchor,anchor+[1,0],anchor+[0,1]]]))[0];su,sv=xy[1]-xy[0],xy[2]-xy[0]
            options=[]
            for ex in [(1,0),(0,1),(-1,0),(0,-1)]:
                for sign in (-1,1):
                    ey=(-ex[1]*sign,ex[0]*sign);a=su*ex[0]+sv*ex[1];b=su*ey[0]+sv*ey[1];options.append((float(a[0]-b[1]),ex,ey))
            _,ex,ey=max(options,key=lambda item:item[0]);axes=[list(ex),list(ey)]
        data=dict(type=kind,points=points,sides=sides,text_axes=axes,text=self.text_value.text(),text_size=self.exact_u.value(),text_angle=self.exact_v.value(),text_font=self.text_font.currentData(),text_align=self.text_align.currentData())
        name='Szkic — '+self.shape.itemText(self.shape.findData(kind)).split(' — ')[0]
        def build():return Body(name,g.profile(kind,frame,points,sides,data['text'],data['text_size'],data.get('text_angle',0),data.get('text_font','sans'),data.get('text_align','left'),data.get('text_axes')),'sketch',plane,frame=frame,support_id=support,sketch_data=data).prepared()
        def apply(body):self.w.add_prepared(body);self.points=[];self.hover=None;self.view.clear_preview();self.cancel_inline();self.annotation.update()
        self.w.run_operation('Rysowanie szkicu',build,apply)

    def escape(self):
        if self.w.busy:return
        if not self.inline.isHidden():self.cancel_inline();return
        if self.mode=='sketch' and self.points:self.cancel_points();return
        self.close_tool()

    def cancel_points(self,*args):
        if self.classic_ready:self.cancel_inline()
        super().cancel_points(*args)

    def position_inline(self):
        kind=(self.w.document.get(self.edit_id).sketch_data['type'] if self.edit_id and self.w.document.get(self.edit_id) else self.shape.currentData())
        height=380 if kind=='text' else 190 if kind=='polygon' else 160 if not self.exact_v.isHidden() else 120
        self.inline.setFixedSize(380 if kind=='text' else 300,height);self.inline.layout().activate();x,y=self.last_pointer
        self.inline.move(max(88,min(self.width()-self.inline.width()-18,round(x+24))),max(90,min(self.height()-self.inline.height()-85,round(y+20))))
        self.inline.show();self.inline.raise_()

    def dimension_values(self,data):
        pts=np.array(data.get('points',[]),dtype=float);kind=data['type']
        if len(pts)<2:return (data.get('text_size',10),0)
        d=pts[-1]-pts[0];length=float(np.linalg.norm(d))
        if kind in ('rectangle','center_rectangle','ellipse'):return abs(d[0]),abs(d[1])
        if kind in ('circle','polygon'):return (2*length if kind=='circle' else 2*length*sin(pi/int(data.get('sides',5)))),degrees(atan2(d[1],d[0]))
        if kind=='circle2':return length,0
        if kind=='circle3':return 2*g.circle_three(pts)[1],0
        if kind in ('slot','rect3'):
            a,b,c=pts;axis=b-a;normal=np.array([-axis[1],axis[0]])/max(1e-9,np.linalg.norm(axis));height=abs(float((c-a)@normal));return (height*2 if kind=='slot' else float(np.linalg.norm(axis))),height
        return length,degrees(atan2(d[1],d[0]))

    def dimension_text(self,body):
        data=body.sketch_data;kind=data['type']
        if kind in ('trim','region'):return 'Profil'
        if kind=='point':return 'Punkt'
        if kind=='text':return data.get('text','Tekst')+' · '+f"{data.get('text_size',10):g} mm"
        try:a,b=self.dimension_values(data)
        except Exception:return 'Wymiar'
        if kind in ('circle','circle2','circle3'):return f'⌀ {a:.3f} mm'
        if kind=='polygon':return f"Bok {a:.3f} mm · {data.get('sides',5)} boków"
        if kind in ('rectangle','center_rectangle','rect3','ellipse'):return f'{a:.3f} × {b:.3f} mm'
        if kind=='slot':return f'Szerokość {a:.3f} mm'
        return f'{a:.3f} mm · {b:.1f}°'

    def open_dimensions(self,text_only=False):
        if self.mode!='sketch' or self.frame is None:return
        kind=self.shape.currentData()
        if not self.points and not text_only:return
        data=dict(type=kind,points=[list(q) for q in self.points]+([list(self.hover)] if self.hover else []),sides=int(self.inline_sides.value()))
        self.set_dimension_labels(kind)
        slot_first=kind=='slot' and len(self.points)==1
        if slot_first:self.inline_u.setText('Długość osi (mm)');self.inline_v.setText('Kąt (°)');self.inline_v.show();self.exact_v.show()
        if not text_only:
            try:a,b=self.dimension_values(data)
            except Exception:
                d=np.asarray(self.hover or (self.points[0][0]+20,self.points[0][1]))-self.points[0];a,b=float(np.linalg.norm(d)),degrees(atan2(d[1],d[0]))
            self.exact_u.blockSignals(True);self.exact_v.blockSignals(True);self.exact_u.setValue(max(.001,a));self.exact_v.setValue(b);self.exact_u.blockSignals(False);self.exact_v.blockSignals(False)
        self.dim_active=not text_only;self.position_inline();self.exact_u.setFocus();self.exact_u.selectAll()

    def set_dimension_labels(self,kind):
        self.inline_u.setText('Średnica (mm)' if kind in ('circle','circle2','circle3') else 'Długość boku (mm)' if kind=='polygon' else 'Wysokość tekstu (mm)' if kind=='text' else 'Szerokość fasolki (mm)' if kind=='slot' else 'Szerokość / długość (mm)')
        self.inline_v.setText('Wysokość (mm)' if kind in ('rectangle','center_rectangle','ellipse','rect3') else 'Kąt (°)')
        show_v=kind not in ('circle','circle2','circle3','slot','point')
        self.inline_v.setVisible(show_v);self.exact_v.setVisible(show_v);self.inline_sides.setVisible(kind=='polygon');self.text_value.setVisible(kind=='text');self.inline_form.labelForField(self.text_value).setVisible(kind=='text');self.inline_form.labelForField(self.inline_sides).setVisible(kind=='polygon');self.text_font.setVisible(kind=='text');self.text_align.setVisible(kind=='text');self.text_font_label.setVisible(kind=='text');self.text_align_label.setVisible(kind=='text')

    def dimension_points(self,data):
        kind=data['type'];points=np.array(data['points'],dtype=float);a=points[0];u=self.exact_u.value();v=self.exact_v.value()
        if kind=='text':return [list(a)]
        b=points[-1] if len(points)>1 else a+[1,1];d=b-a;theta=atan2(d[1],d[0]);sx=1 if d[0]>=0 else -1;sy=1 if d[1]>=0 else -1
        if self.edit_id:
            if kind in ('slot','rect3','arc'):
                length=max(1e-9,float(np.linalg.norm(points[1]-a)));return [(a+(q-a)*u/length).tolist() for q in points]
            if kind=='center_rectangle':u/=2;v/=2
            if kind=='ellipse':v=abs(d[1])
        if kind in ('rectangle','center_rectangle','ellipse'):return [list(a),list(a+[u*sx,abs(v)*sy])]
        if kind in ('circle','circle2','polygon','line','construction'):
            radius=u/2 if kind=='circle' else u/(2*sin(pi/int(self.inline_sides.value()))) if kind=='polygon' else u
            angle=theta if kind in ('circle','circle2') or self.edit_id else v*pi/180
            return [list(a),list(a+np.array([cos(angle),sin(angle)])*radius)]
        if kind=='circle3':
            center,radius=g.circle_three(points);center=np.array(center);return [(center+(q-center)*u/(2*radius)).tolist() for q in points]
        if kind in ('slot','rect3'):
            if len(points)<2:return points.tolist()
            a,b=points[:2];axis=b-a;length=max(1e-9,np.linalg.norm(axis));n=np.array([-axis[1],axis[0]])/length
            if kind=='slot':return [a.tolist(),b.tolist(),(a+n*u/2).tolist()]
            return [a.tolist(),(a+axis/length*u).tolist(),(a+n*abs(v)).tolist()]
        return points.tolist()

    def inline_changed(self,*args):
        if not self.classic_ready:return
        if not self.dim_active and not self.edit_id:return
        body=self.w.document.get(self.edit_id) if self.edit_id else None
        data=dict(body.sketch_data) if body else dict(type=self.shape.currentData(),points=[list(q) for q in self.points]+([list(self.hover)] if self.hover else []),sides=int(self.inline_sides.value()))
        if not data.get('points'):return
        try:
            data['points']=self.dimension_points(data);data['sides']=int(self.inline_sides.value())
            frame=body.frame if body else self.frame
            shape=g.profile(data['type'],frame,data['points'],data['sides'],self.text_value.text(),self.exact_u.value(),self.exact_v.value(),self.text_font.currentData(),self.text_align.currentData(),data.get('text_axes'))
            self.view.show_wire(shape,'#1787de')
        except Exception:pass

    def accept_inline(self):
        if self.w.busy:return
        if self.edit_id:
            body=self.w.document.get(self.edit_id)
            if not body:return
            data=dict(body.sketch_data);data.update(points=self.dimension_points(data),sides=int(self.inline_sides.value()),text=self.text_value.text(),text_size=self.exact_u.value(),text_angle=self.exact_v.value(),text_font=self.text_font.currentData(),text_align=self.text_align.currentData())
            bodies=self.w.document.bodies
            def build():return flows.edit_sketch_transaction(body,data,bodies)
            def apply(result):self.w.document.commit(result);self.w.selected=[body.id];self.cancel_inline();self.view.clear_preview()
            self.w.run_operation('Zmiana wymiaru szkicu',build,apply);return
        if self.shape.currentData()=='text':self.cancel_inline();return
        if not self.points:return
        kind=self.shape.currentData();data=dict(type=kind,points=[list(q) for q in self.points]+([list(self.hover)] if self.hover else []))
        points=self.dimension_points(data)
        if kind=='slot' and len(self.points)==1:
            a=np.array(self.points[0]);angle=self.exact_v.value()*pi/180;points=[a.tolist(),(a+np.array([cos(angle),sin(angle)])*self.exact_u.value()).tolist()]
        if kind in ('slot','rect3') and len(self.points)==1:
            self.points=points;self.dim_active=False;self.inline.hide();return
        self.commit_profile(kind,points)

    def dimensioned_profile(self):
        if not self.points:return
        kind=self.shape.currentData();data=dict(type=kind,points=[list(self.points[0]),list(self.hover or (self.points[0][0]+1,self.points[0][1]+1))])
        self.commit_profile(kind,self.dimension_points(data))

    def cancel_inline(self):
        if not self.classic_ready:return
        self.inline.hide();self.dim_active=False;self.edit_id=None;self.view.clear_preview();self.view.setFocus()

    def eventFilter(self,obj,event):
        if isinstance(obj,QDoubleSpinBox) and event.type() in (QEvent.Enter,QEvent.Leave):
            obj.setButtonSymbols(QAbstractSpinBox.UpDownArrows if event.type()==QEvent.Enter else QAbstractSpinBox.NoButtons)
        if event.type()==QEvent.KeyPress and obj in (self.depth,self.second,self.w.blend_size) and event.key() in (Qt.Key_Return,Qt.Key_Enter):self.accept_operation();return True
        if event.type()==QEvent.KeyPress and not self.inline.isHidden():
            if event.key() in (Qt.Key_Return,Qt.Key_Enter):
                if obj is self.text_value:return False
                self.accept_inline();return True
            if event.key()==Qt.Key_Escape:self.cancel_inline();return True
            if event.key()==Qt.Key_Tab:
                fields=[w for w in [self.exact_u,self.exact_v,self.inline_sides,self.text_value] if w.isVisible()]
                if fields:
                    index=fields.index(obj) if obj in fields else -1;next_field=fields[(index+1)%len(fields)];next_field.setFocus();next_field.selectAll()
                return True
        return super().eventFilter(obj,event)

    def edit_dimension_at(self,x,y):
        if self.w.busy:return
        if self.mode!='sketch':self.home_view();return
        identifier=next((i for rect,i in self.annotation.hits if rect.contains(x,y)),None)
        if not identifier:
            hit=self.view.nearest_edge(x,y);identifier=hit[0] if hit else self.view.pick_profile(x,y)
        body=self.w.document.get(identifier)
        if not body or not body.sketch_data or not self.coplanar(body):return
        if body.sketch_data['type'] in ('region','trim','point','circleTangent2'):return
        self.edit_id=identifier;self.points=[];data=body.sketch_data;self.set_dimension_labels(data['type'])
        a,b=self.dimension_values(data)
        if data['type']=='text':b=data.get('text_angle',0)
        if data['type']=='center_rectangle':a*=2;b*=2
        if data['type'] in ('slot','rect3','arc'):
            points=np.array(data['points']);a=float(np.linalg.norm(points[1]-points[0]));self.inline_u.setText('Długość osi (mm)' if data['type']=='slot' else 'Długość (mm)')
        if data['type'] not in ('rectangle','center_rectangle','text'):
            self.inline_v.hide();self.exact_v.hide()
        for field,value in [(self.exact_u,max(.001,a)),(self.exact_v,b),(self.inline_sides,data.get('sides',5))]:field.blockSignals(True);field.setValue(value);field.blockSignals(False)
        self.text_value.blockSignals(True);self.text_value.setText(data.get('text','RCCAD'));self.text_value.blockSignals(False)
        for field,key,default in [(self.text_font,'text_font','sans'),(self.text_align,'text_align','left')]:
            field.blockSignals(True);field.setCurrentIndex(field.findData(data.get(key,default)));field.blockSignals(False)
        self.last_pointer=(x,y);self.position_inline();self.exact_u.setFocus();self.exact_u.selectAll()

    def trim_inputs(self,x,y):
        hit=self.view.nearest_edge(x,y);body=self.w.document.get(hit[0]) if hit else None
        if not body or body.kind!='sketch' or not self.coplanar(body):return None
        ray=self.view._ray(x,y);q=g.plane_point(self.frame,*ray) if ray else None
        if q is None:return None
        others=[b.shape for b in self.w.document.bodies if b.id!=body.id and b.visible and b.kind=='sketch' and self.coplanar(b)]
        own=[e for i,e in enumerate(body.shape.Edges()) if i!=hit[1]]
        if own:others.append(cq.Compound.makeCompound(own))
        return body,hit[1],g.world_point(self.frame,q),others

    def schedule_trim(self,x,y):
        if self.w.busy:return
        data=self.trim_inputs(x,y)
        if data is None:self.trim_timer.stop();self.trim_data=None;self.generation+=1;self.view.clear_preview();return
        body,index,point,others=data;key=(self.w.document._revision,body.id,index,round(x/4),round(y/4))
        if key==self.trim_key:return
        self.trim_key=key;self.trim_data=data;self.generation+=1;self.trim_timer.start()

    def preview_trim(self):
        if self.mode!='sketch' or self.shape.currentData()!='trim' or self.w.busy or self.trim_data is None:return
        if self.preview_running:self.trim_timer.start();return
        body,index,point,others=self.trim_data;edge=body.shape.Edges()[index];gen=self.generation;revision=self.w.document._revision
        from .window import Work
        def build():
            kept=g.trim_segments(edge,others,point)
            return edge.cut(cq.Compound.makeCompound(kept)) if kept else edge
        work=Work(build);self.preview_running=True;self.preview_work=work
        def done(shape):
            self.preview_running=False;self.preview_work=None
            if self.mode=='sketch' and self.shape.currentData()=='trim' and gen==self.generation and revision==self.w.document._revision:self.view.show_wire(shape,'#cb2428')
        def failed(message):self.preview_running=False;self.preview_work=None
        work.signals.done.connect(done);work.signals.failed.connect(failed);self.w.pool.start(work)

    def trim_at(self,x,y):
        if self.w.busy:return
        data=self.trim_inputs(x,y)
        if data is None:return
        self.trim_timer.stop();self.generation+=1;body,index,point,others=data;edge=body.shape.Edges()[index]
        def build():
            remaining=[e for i,e in enumerate(body.shape.Edges()) if i!=index]+g.trim_segments(edge,others,point)
            if not remaining:return None
            shape=cq.Compound.makeCompound(remaining);return replace(body.changed(shape),sketch_data=dict(type='trim',points=[]))
        def apply(result):self.w.document.commit([result if b.id==body.id else b for b in self.w.document.bodies if b.id!=body.id or result is not None]);self.view.clear_preview();self.trim_key=None
        self.w.run_operation('Przycinanie szkicu',build,apply)

    def update_edge_handle(self,*args):
        super().update_edge_handle(*args)
        if self.classic_ready and self.mode=='blend' and not any(self.w.edges.values()):self.auto_blend_timer.stop();self._auto_blend_stamp=None
        if self.classic_ready and self.mode=='blend' and any(self.w.edges.values()):
            stamp=self.blend_stamp()
            if stamp!=self._auto_blend_stamp:self._auto_blend_stamp=stamp;self.auto_blend_timer.start()

    def auto_blend(self):
        if self.mode!='blend' or self.w.busy:return
        if self.preview_running:self.auto_blend_timer.start();return
        self.preview_blend()

    def drag_extrusion(self,kind,delta):
        if kind.startswith('transform_') or kind.startswith('rotate_'):
            fields=self.rotate_fields if kind.startswith('rotate_') else self.move_fields;control=fields[int(kind.split('_')[1])];control.setValue(control.value()+delta);return
        super().drag_extrusion(kind,delta)
        if kind=='extrude' and self.mode=='extrude':
            body=self.selected_profile()
            if body:
                n=np.array((body.frame or g.frame_for(body.plane))[2]);d=self.depth.value()*(-1 if self.operation.currentData()=='subtract' else 1)
                if self.direction.currentData()=='symmetric':d*=.5
                self.view.set_handle(np.array(body.shape.Center().toTuple())+n*d,n,'extrude')

    def direction_changed(self,*args):
        self.symmetric.setChecked(self.direction.currentData()=='symmetric');self.second.setVisible(self.direction.currentData()=='two');self.second_label.setVisible(self.direction.currentData()=='two');self.request_preview();self.arrange()

    def begin_extrude(self):
        if self.w.busy:return
        super().begin_extrude();bodies=self.w.document.bodies
        visible=[b for b in bodies if b.kind=='sketch' and b.visible and (b.sketch_data or {}).get('type') not in ('construction','point')]
        if len(visible)<2 or all((b.sketch_data or {}).get('type')=='region' for b in visible):return
        previous=tuple(self.w.selected)
        def build():
            return [Body(f'Obszar {i+1}',face,'sketch',frame=frame,support_id=support,sketch_data=dict(type='virtual_region',points=[],sources=sources,owner=owner)).prepared() for i,(face,frame,sources,support,owner) in enumerate(g.design_regions(bodies))]
        def apply(regions):
            self.live_regions=regions;self.region_revision=self.w.document._revision;self.region_selected=[]
            if len(regions)==1 and any(i in regions[0].sketch_data['sources'] for i in previous):self.region_selected=[regions[0].id]
            elif regions:
                sources={i for r in regions for i in r.sketch_data['sources']};self.w.selected=[i for i in self.w.selected if i not in sources]
        self.w.run_operation('Rozpoznawanie obszarów szkicu',build,apply)

    def selected_profile(self):
        profiles=self.selected_profiles();return profiles[0] if profiles else None

    def selected_profiles(self):
        selected=[b for i in self.w.selected if (b:=self.w.document.get(i)) and b.kind=='sketch' and (b.sketch_data or {}).get('type') not in ('construction','point')]
        if not self.live_regions:return selected
        sources={i for b in self.live_regions for i in b.sketch_data['sources']};result=[b for b in selected if b.id not in sources]
        result.extend(r for r in self.live_regions if r.id in self.region_selected or r.sketch_data.get('owner') in self.w.selected)
        return list({b.id:b for b in result}.values())

    def profile_clicked(self,identifier):
        if self.mode=='sketch' and self.view.plane_mode:
            body=self.w.document.get(identifier)
            if body and body.kind=='sketch':self.frame=body.frame or g.frame_for(body.plane);self.support=body.support_id;self.activate_plane()
        if self.mode=='extrude':
            additive=self.view.multi_select or bool(QApplication.keyboardModifiers() & Qt.ShiftModifier)
            if any(b.id==identifier for b in self.live_regions):
                if not additive:self.region_selected=[identifier];self.w.selected=[]
                elif identifier in self.region_selected:self.region_selected.remove(identifier)
                else:self.region_selected.append(identifier)
                self.w.refresh()
            else:
                if not additive:self.region_selected=[]
                self.w.body_clicked(identifier,additive)

    def preview_extrusion(self):
        if not self.classic_ready:return super().preview_extrusion()
        if self.mode!='extrude' or self.w.busy:return
        if self.preview_running:self.preview_timer.start();return
        profiles=self.selected_profiles()
        if not profiles:self.view.clear_preview();self.view.set_handle(None);return
        gen=self.generation;revision=self.w.document._revision;bodies=self.w.document.bodies;distance=self.depth.value();direction=self.direction.currentData();second=self.second.value();cut=self.operation.currentData()=='subtract';holes=self.include_holes.isChecked()
        from .window import Work
        def build():
            tools,_=flows.profile_tools(profiles,bodies,distance,direction,second,cut,holes);return kernel.display_mesh(cq.Compound.makeCompound(tools))
        work=Work(build);self.preview_running=True;self.preview_work=work
        def done(mesh):
            self.preview_running=False;self.preview_work=None
            if self.mode!='extrude' or gen!=self.generation or revision!=self.w.document._revision:return
            self.view.show_preview_mesh(mesh,'#ef9a26' if cut else '#35b77e')
            body=profiles[0];n=np.array((body.frame or g.frame_for(body.plane))[2]);d=(-distance if cut else distance)*(0.5 if direction=='symmetric' else 1)
            self.view.set_handle(np.array(body.shape.Center().toTuple())+n*d,n,'extrude');self.preview_status.setText(f'Wybrane profile: {len(profiles)}')
        def failed(message):
            self.preview_running=False;self.preview_work=None
            if gen==self.generation and self.mode=='extrude':self.view.clear_preview();self.preview_status.setText(message)
        work.signals.done.connect(done);work.signals.failed.connect(failed);self.w.pool.start(work)

    def extrusion_bodies(self):
        if not self.live_regions:return self.w.document.bodies
        sources={i for b in self.live_regions for i in b.sketch_data['sources']}
        originals=[replace(b,visible=False) if b.id in sources else b for b in self.w.document.bodies]
        return tuple(originals+[replace(b,sketch_data=dict(b.sketch_data,type='region')) for b in self.live_regions])

    def display_regions(self):
        if not self.live_regions:return
        sources={i for b in self.live_regions for i in b.sketch_data['sources']}
        originals=[replace(b,sketch_data=dict(b.sketch_data or {},region_source=True)) if b.id in sources else b for b in self.w.document.bodies]
        self.view.set_models(originals+self.live_regions,self.w.selected+self.region_selected,self.w.edges)

    def apply_extrude(self):
        profiles=self.selected_profiles();bodies=self.extrusion_bodies();distance=self.depth.value();mode=self.operation.currentData();target=self.w.document.get(self.target.currentData());direction=self.direction.currentData();second=self.second.value();holes=self.include_holes.isChecked();self.generation+=1
        def apply(value):changed,selected=value;self.live_regions=[];self.region_selected=[];self.region_revision=None;self.w.document.commit(changed);self.w.selected=selected;self.view.clear_preview();self.view.set_handle(None)
        self.w.run_operation('Wyciągnięcie / wycięcie',lambda:flows.extrusion_transaction(profiles,bodies,distance,mode,target,direction,second,holes),apply,False)

    def begin_boolean(self):
        super().begin_boolean()
        for button in self.boolean_page.findChildren(QPushButton):
            if button.text()=='Zastosuj':
                try:button.clicked.disconnect()
                except RuntimeError:pass
                button.clicked.connect(self.apply_boolean)

    def apply_boolean(self):
        bodies=self.w.document.bodies;selected=tuple(self.w.selected);mode=self.bool_mode.currentData();keep=self.bool_keep.isChecked()
        def apply(value):changed,identifier=value;self.w.document.commit(changed);self.w.selected=[identifier]
        self.w.run_operation('Operacje na bryłach',lambda:flows.boolean_transaction(bodies,selected,mode,keep),apply)

    def transform_target(self):
        return next((self.w.document.get(i) for i in self.w.selected if self.w.document.get(i) and self.w.document.get(i).kind in ('solid','sketch')),None)

    def begin_transform(self,mode='move'):
        self.transform_mode=mode if mode in ('move','rotate') else 'move';super().begin_transform()
        self.panel.hide();self.transform_groups[0].setVisible(self.transform_mode=='move');self.transform_groups[1].setVisible(self.transform_mode=='rotate');self.transform_caption.setText('Obrót (°)' if self.transform_mode=='rotate' else 'Przesunięcie (mm)');self.arrange()

    def preview_transform(self):
        if self.mode!='transform' or self.w.busy:return
        if self.preview_running:self.preview_timer.start();return
        body=self.transform_target()
        if not body:self.view.clear_preview();self.view.set_handle(None);return
        move=tuple(c.value() for c in self.move_fields);rotate=tuple(c.value() for c in self.rotate_fields);gen=self.generation;revision=self.w.document._revision
        from .window import Work
        work=Work(lambda:kernel.display_mesh(kernel.transform(body.shape,move,rotate)));self.preview_running=True;self.preview_work=work
        def done(mesh):
            self.preview_running=False;self.preview_work=None
            if self.mode!='transform' or gen!=self.generation or revision!=self.w.document._revision:return
            self.view.show_preview_mesh(mesh,'#35b783');self.view.set_gizmo(mesh.center,mesh.size*.65,self.transform_mode=='rotate')
        def failed(message):
            self.preview_running=False;self.preview_work=None
            if gen==self.generation:self.view.clear_preview();self.w.statusBar().showMessage(message)
        work.signals.done.connect(done);work.signals.failed.connect(failed);self.w.pool.start(work)

    def apply_transform(self):
        body=self.transform_target()
        if not body:return
        move=tuple(c.value() for c in self.move_fields);rotate=tuple(c.value() for c in self.rotate_fields);self.generation+=1
        def apply(result):
            self.w.replace_body(body,result)
            for c in self.move_fields+self.rotate_fields:c.setValue(0)
        self.w.run_operation('Przesunięcie / obrót',lambda:flows.moved_body(body,move,rotate),apply,False)

    def begin_mirror(self):
        self.mirror_source=None;self.mirror_frame=None
        super().begin_mirror();self.update_mirror_source()

    def reset_mirror(self):
        self.mirror_source=None;self.mirror_frame=None;self.view.face_mode=False;self.view.clear_preview();self.w.clear_selection();self.mirror_status.setText('Kliknij obiekt, a następnie płaską ścianę odbicia.')

    def update_mirror_source(self):
        if self.mode!='mirror':return
        if self.mirror_source is None:
            body=self.transform_target()
            if body:self.mirror_source=body.id
        body=self.w.document.get(self.mirror_source)
        if body:
            self.view.face_mode=True;self.mirror_join.setVisible(body.kind=='solid')
            self.mirror_status.setText('Obiekt: '+body.name+(' · wskaż ścianę odbicia' if self.mirror_frame is None else ' · płaszczyzna wskazana'))

    def face_clicked(self,identifier,point):
        if self.mode!='mirror':return super().face_clicked(identifier,point)
        if self.w.busy or self.mirror_source is None:return
        target=self.w.document.get(identifier)
        try:self.mirror_frame=g.face_frame(target,point)
        except kernel.CadError as exc:self.notify(str(exc));return
        self.update_mirror_source();self.request_preview()

    def request_preview(self,*args):
        if self.classic_ready and self.mode=='mirror':self.generation+=1;self.preview_timer.start()
        else:super().request_preview(*args)

    def refresh_preview(self):
        if self.mode=='mirror':self.preview_mirror()
        else:super().refresh_preview()

    def preview_mirror(self):
        if self.w.busy or self.mode!='mirror' or self.mirror_frame is None:return
        if self.preview_running:self.preview_timer.start();return
        body=self.w.document.get(self.mirror_source)
        if not body:return
        frame=self.mirror_frame;join=self.mirror_join.isChecked() and body.kind=='solid';keep=self.mirror_keep.isChecked();gen=self.generation
        from .window import Work
        work=Work(lambda:flows.reflected_body(body,frame,join,keep).mesh);self.preview_running=True;self.preview_work=work
        def done(mesh):
            self.preview_running=False;self.preview_work=None
            if self.mode=='mirror' and gen==self.generation:self.view.show_preview_mesh(mesh,'#35b783')
        def failed(message):
            self.preview_running=False;self.preview_work=None
            if gen==self.generation:self.notify(message)
        work.signals.done.connect(done);work.signals.failed.connect(failed);self.w.pool.start(work)

    def apply_mirror(self):
        body=self.w.document.get(self.mirror_source)
        if body is None or self.mirror_frame is None:self.notify('Kliknij obiekt, a następnie płaską ścianę odbicia.');return
        frame=self.mirror_frame;join=self.mirror_join.isChecked() and body.kind=='solid';keep=self.mirror_keep.isChecked();self.generation+=1
        def apply(result):
            if join or not keep:self.w.replace_body(body,result)
            else:self.w.add_prepared(result)
            self.view.clear_preview()
        self.w.run_operation('Odbicie lustrzane',lambda:flows.reflected_body(body,frame,join,keep),apply)

    def accept_operation(self):
        if self.w.busy:return
        if self.mode=='extrude':self.apply_extrude()
        elif self.mode=='blend':self.w.apply_blend()
        elif self.mode=='boolean':self.apply_boolean()
        elif self.mode=='transform':self.apply_transform()
        elif self.mode=='mirror':self.apply_mirror()

    def notify(self,message):
        self.last_notice=str(message);self.notice_timer.stop();self.notice_group.stop()
        self.notice_text.setText(self.last_notice);self.notice.adjustSize()
        target=QPoint(self.width()-self.notice.width()-18,self.height()-self.notice.height()-22)
        self.notice.move(target+QPoint(0,10));self.notice.show();self.notice.raise_()
        self.notice_fade.setDuration(200);self.notice_fade.setStartValue(0.);self.notice_fade.setEndValue(1.)
        self.notice_slide.setDuration(200);self.notice_slide.setStartValue(target+QPoint(0,10));self.notice_slide.setEndValue(target)
        self.notice_group.start();self.notice_timer.start()

    def fade_notice(self):
        self.notice_group.stop();self.notice_fade.setStartValue(1.);self.notice_fade.setEndValue(0.)
        self.notice_slide.setStartValue(self.notice.pos());self.notice_slide.setEndValue(self.notice.pos()+QPoint(0,10));self.notice_group.start()

    def document_changed(self):
        super().document_changed()
        if not self.classic_ready:return
        self.annotation.update()
        if self.live_regions and self.region_revision!=self.w.document._revision:self.live_regions=[];self.region_selected=[];self.region_revision=None
        if self.mode=='extrude':self.display_regions()
        if self.mode=='mirror':self.update_mirror_source()
        if self.mode=='sketch':self.panel.hide()
        if self.w.document._revision!=self._last_revision:
            self._last_revision=self.w.document._revision
            maximum=0.
            for b in self.w.document.bodies:
                if b.kind!='sketch':continue
                data=b.sketch_data or {};points=np.asarray(data.get('points',[]),dtype=float)
                if points.size:
                    maximum=max(maximum,float(np.abs(points).max()))
                    if data.get('type')=='circle' and len(points)>1:maximum=max(maximum,float(np.abs(points[0]).max()+np.linalg.norm(points[1]-points[0])))
            self.view.grid_half=120 if maximum<=100 else max(120,float(np.ceil((maximum+20)/40)*40));self.view.sync_grid()
            snapshot={b.id:b.shape.hashCode() for b in self.w.document.bodies if b.kind=='solid'}
            affected={identifier for identifier,value in snapshot.items() if self._body_hashes.get(identifier)!=value}
            self._body_hashes=snapshot
            if affected:self.view.flash('#ef9a26' if self.mode=='blend' or self.mode=='extrude' and self.operation.currentData()=='subtract' else '#6bbd9b',affected)
