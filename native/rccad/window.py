"""Native desktop workflow. CAD work runs outside the GUI event loop."""
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
import traceback
from PySide6.QtCore import Qt, QObject, Signal, QRunnable, QThreadPool
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDockWidget,
    QTreeWidget, QTreeWidgetItem, QAbstractItemView, QToolBar, QDoubleSpinBox,
    QPushButton, QComboBox, QFormLayout, QDialog, QDialogButtonBox,
    QFileDialog, QMessageBox, QCheckBox, QProgressBar, QStyle,
)
from . import __version__, kernel
from .document import Body, Document
from .viewport import CadView


class WorkSignals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Work(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = WorkSignals()

    def run(self):
        try:
            self.signals.done.emit(self.function())
        except Exception as exc:
            self.signals.failed.emit(str(exc) if isinstance(exc, kernel.CadError) else f"Operacja nie powiodła się: {exc}")


def values_dialog(parent, title, fields, hint=""):
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    layout = QVBoxLayout(dialog)
    if hint:
        text = QLabel(hint)
        text.setWordWrap(True)
        layout.addWidget(text)
    form = QFormLayout()
    controls = {}
    for key, label, value, minimum in fields:
        control = QDoubleSpinBox()
        control.setRange(minimum, 1e6)
        control.setDecimals(3)
        control.setValue(value)
        control.setMinimumWidth(150)
        form.addRow(label, control)
        controls[key] = control
    layout.addLayout(form)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    if dialog.exec() != QDialog.Accepted:
        return None
    return {key: control.value() for key, control in controls.items()}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.document = Document()
        self.selected = []
        self.edges = {}
        self.busy = False
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self._work = None
        self.resize(1380, 900)
        self.setMinimumSize(950, 650)
        self.view = CadView()
        self.setCentralWidget(self.view)
        self.actions = []
        self._menus()
        self._sidebar()
        self.view.edgeClicked.connect(self.edge_clicked)
        self.view.bodyClicked.connect(self.body_clicked)
        self.view.selectionCleared.connect(self.clear_selection)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumWidth(180)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().showMessage("Gotowy · mm · lewy przycisk: obrót / wybór · środkowy: przesuwanie · rolka: zoom")
        self._style()
        self.refresh()

    def _action(self, name, callback, shortcut=None, icon=None):
        action = QAction(name, self)
        if icon is not None:
            action.setIcon(self.style().standardIcon(icon))
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(callback)
        self.actions.append(action)
        return action

    def _menus(self):
        file = self.menuBar().addMenu("Projekt")
        top = QToolBar("Projekt")
        top.setMovable(False)
        top.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(top)
        for name, fn, key, icon in [
            ("Nowy", self.new_project, QKeySequence.New, QStyle.SP_FileIcon),
            ("Otwórz", self.open_project, QKeySequence.Open, QStyle.SP_DirOpenIcon),
            ("Zapisz", self.save_project, QKeySequence.Save, QStyle.SP_DialogSaveButton),
            ("Importuj", self.import_model, "Ctrl+I", QStyle.SP_ArrowDown),
            ("Eksportuj", self.export_model, "Ctrl+E", QStyle.SP_ArrowUp),
        ]:
            action = self._action(name, fn, key, icon)
            file.addAction(action)
            top.addAction(action)
        file.addAction(self._action("Zapisz jako…", lambda: self.save_project(True), "Ctrl+Shift+S"))
        top.addSeparator()
        self.undo_action = self._action("Cofnij", self.undo, QKeySequence.Undo, QStyle.SP_ArrowBack)
        self.redo_action = self._action("Ponów", self.redo, QKeySequence.Redo, QStyle.SP_ArrowForward)
        top.addAction(self.undo_action)
        top.addAction(self.redo_action)
        self.addToolBarBreak()
        model = QToolBar("Modelowanie")
        model.setMovable(False)
        self.addToolBar(model)
        for name, fn in [
            ("Prostopadłościan", self.add_box), ("Walec", self.add_cylinder),
            ("Szkic", self.add_sketch), ("Wyciągnij", self.extrude_sketch),
            ("Otwór", self.make_hole), ("Połącz", lambda: self.combine('union')),
            ("Wytnij", lambda: self.combine('subtract')), ("Część wspólna", lambda: self.combine('intersect')),
            ("Zaokrąglij", lambda: self.start_blend('fillet')), ("Fazuj", lambda: self.start_blend('chamfer')),
            ("Przenieś / obróć", self.transform_body), ("Lustro", self.mirror_body),
        ]:
            model.addAction(self._action(name, fn))
        view = self.menuBar().addMenu("Widok")
        for name in ['iso', 'XY', 'XZ', 'YZ']:
            view.addAction(self._action('Izometryczny' if name == 'iso' else name, lambda checked=False, n=name: self.view.set_view(n)))
        view.addAction(self._action("Dopasuj model", self.view.fit_all, "F"))
        view.addAction(self._action("Siatka", self.toggle_grid, "G"))
        edit = self.menuBar().addMenu("Edycja")
        edit.addAction(self.undo_action)
        edit.addAction(self.redo_action)
        edit.addAction(self._action("Duplikuj", self.duplicate_body, "Ctrl+D"))
        edit.addAction(self._action("Usuń", self.delete_selected, QKeySequence.Delete))
        help_menu = self.menuBar().addMenu("Pomoc")
        help_menu.addAction(self._action("O programie", lambda: QMessageBox.information(self, "RCCAD Desktop", f"RCCAD Desktop {__version__}\nNatywna aplikacja Qt · silnik OpenCascade\nPierwsza wersja rozwojowa. Jednostki: mm.\nStarsze projekty HTML przenoś przez eksport STEP.")))

    def _sidebar(self):
        dock = QDockWidget("MODEL", self)
        dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Obiekt", "Typ"])
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.itemSelectionChanged.connect(self.tree_selection)
        self.tree.itemChanged.connect(self.visibility_changed)
        layout.addWidget(self.tree, 1)
        self.properties = QLabel("Dodaj bryłę albo utwórz szkic.")
        self.properties.setWordWrap(True)
        self.properties.setMinimumHeight(110)
        self.properties.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.properties)
        self.blend_panel = QWidget()
        blend_layout = QVBoxLayout(self.blend_panel)
        blend_layout.setContentsMargins(0, 12, 0, 8)
        self.blend_type = QComboBox()
        self.blend_type.addItem("Zaokrąglenie", "fillet")
        self.blend_type.addItem("Fazowanie", "chamfer")
        blend_layout.addWidget(self.blend_type)
        self.blend_size = QDoubleSpinBox()
        self.blend_size.setRange(.001, 100000)
        self.blend_size.setDecimals(3)
        self.blend_size.setValue(3)
        self.blend_size.setSuffix(" mm")
        blend_layout.addWidget(self.blend_size)
        self.edge_count = QLabel("Kliknij krawędź. Shift + klik dodaje kolejne.")
        self.edge_count.setWordWrap(True)
        blend_layout.addWidget(self.edge_count)
        buttons = QHBoxLayout()
        apply = QPushButton("Zastosuj")
        apply.clicked.connect(self.apply_blend)
        close = QPushButton("Zamknij")
        close.clicked.connect(self.end_blend)
        buttons.addWidget(apply)
        buttons.addWidget(close)
        blend_layout.addLayout(buttons)
        self.blend_panel.hide()
        layout.addWidget(self.blend_panel)
        tip = QLabel("W drzewie: Ctrl + klik zaznacza kilka brył.\nW widoku: Shift + klik dodaje krawędzie.\nF — dopasuj · Ctrl+Z — cofnij")
        tip.setWordWrap(True)
        tip.setObjectName('tip')
        layout.addWidget(tip)
        dock.setWidget(panel)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        dock.setMinimumWidth(285)
        dock.setMaximumWidth(380)
        self.model_dock = dock

    def _style(self):
        self.setStyleSheet("""
        QMainWindow { background: #edf1f5; }
        QMenuBar, QToolBar { background: #fff; spacing: 7px; padding: 6px; border: 0; }
        QToolButton { padding: 8px; border: 1px solid transparent; border-radius: 5px; }
        QToolButton:hover { background: #e6f0fb; border-color: #bfd2e7; }
        QDockWidget { color: #23435f; font-weight: 600; }
        QDockWidget QWidget { background: #fff; }
        QTreeWidget { border: 0; alternate-background-color: #f3f6fa; }
        QTreeWidget::item { padding: 7px 0; }
        QTreeWidget::item:selected { background: #dcecff; color: #173f68; }
        QPushButton { padding: 8px 12px; border: 1px solid #b8c9da; border-radius: 5px; background: #f3f7fb; }
        QPushButton:hover { background: #dcecff; }
        QDoubleSpinBox, QComboBox { padding: 6px; border: 1px solid #b8c9da; border-radius: 4px; }
        QLabel#tip { color: #607a91; font-size: 11px; padding: 10px 0; }
        QStatusBar { background: #fff; color: #47647d; }
        """)

    def refresh(self, fit=False):
        live = {b.id for b in self.document.bodies}
        self.selected = [i for i in self.selected if i in live]
        self.edges = {i: es for i, es in self.edges.items() if i in live}
        self.tree.blockSignals(True)
        self.tree.clear()
        labels = {'solid': 'Bryła', 'sketch': 'Szkic', 'mesh': 'Siatka'}
        for body in self.document.bodies:
            item = QTreeWidgetItem([body.name, labels[body.kind]])
            item.setData(0, Qt.UserRole, body.id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEditable)
            item.setCheckState(0, Qt.Checked if body.visible else Qt.Unchecked)
            self.tree.addTopLevelItem(item)
            item.setSelected(body.id in self.selected)
        self.tree.blockSignals(False)
        self.view.set_models(self.document.bodies, self.selected, self.edges)
        if fit:
            self.view.fit_all()
        self.undo_action.setEnabled(self.document.can_undo and not self.busy)
        self.redo_action.setEnabled(self.document.can_redo and not self.busy)
        self.setWindowTitle(f"{'● ' if self.document.dirty else ''}{self.document.path.name if self.document.path else 'Nowy projekt'} — RCCAD Desktop")
        self.edge_count.setText(f"Zaznaczone krawędzie: {sum(map(len,self.edges.values()))}\nShift + klik dodaje kolejne.")
        body = self.document.get(self.selected[0]) if self.selected else None
        if body:
            bounds = body.shape.BoundingBox()
            volume = f"\nObjętość: {body.shape.Volume():,.3f} mm³" if body.kind == 'solid' else ''
            self.properties.setText(f"{body.name}\nWymiary: {bounds.xlen:.3f} × {bounds.ylen:.3f} × {bounds.zlen:.3f} mm{volume}\nKrawędzie: {len(body.shape.Edges())}")
        else:
            self.properties.setText("Dodaj bryłę lub szkic.\nWybierz obiekt w drzewie albo w widoku 3D.")

    def run_operation(self, label, function, apply, fit=False):
        if self.busy:
            return
        self.busy = True
        self.progress.show()
        self.statusBar().showMessage(label + "…")
        for action in self.actions:
            action.setEnabled(False)
        self.tree.setEnabled(False)
        self.blend_panel.setEnabled(False)
        work = Work(function)
        self._work = work
        def done(value):
            try:
                apply(value)
                self.edges.clear()
                self.statusBar().showMessage(label + " — gotowe", 6000)
            except Exception as exc:
                QMessageBox.warning(self, "RCCAD", str(exc))
            finally:
                finish()
                self.refresh(fit)
        def failed(message):
            finish()
            QMessageBox.warning(self, "Nie można wykonać operacji", message + "\n\nDotychczasowy model pozostał bez zmian.")
            self.refresh()
        def finish():
            self.busy = False
            self.progress.hide()
            self.tree.setEnabled(True)
            self.blend_panel.setEnabled(True)
            for action in self.actions:
                action.setEnabled(True)
            self._work = None
        work.signals.done.connect(done)
        work.signals.failed.connect(failed)
        self.pool.start(work)

    def add_prepared(self, body):
        self.document.commit((*self.document.bodies, body))
        self.selected = [body.id]

    def selected_body(self, kind='solid'):
        body = self.document.get(self.selected[0]) if len(self.selected) == 1 else None
        if not body or (kind and body.kind != kind):
            QMessageBox.information(self, "Wybierz obiekt", "Zaznacz jedną bryłę." if kind == 'solid' else "Zaznacz jeden szkic.")
            return None
        return body

    def replace_body(self, body, result):
        self.document.commit(result if isinstance(result, (list, tuple)) else [result if b.id == body.id else b for b in self.document.bodies])
        self.selected = [body.id]

    def add_box(self):
        v = values_dialog(self, "Prostopadłościan", [('x','Szerokość X (mm)',30,.001),('y','Głębokość Y (mm)',30,.001),('z','Wysokość Z (mm)',30,.001)])
        if v:
            self.run_operation("Tworzenie prostopadłościanu", lambda: Body('Prostopadłościan',kernel.box(**v)).prepared(), self.add_prepared, True)

    def add_cylinder(self):
        v = values_dialog(self,"Walec",[('radius','Promień (mm)',10,.001),('height','Wysokość (mm)',30,.001)])
        if v:
            self.run_operation("Tworzenie walca",lambda: Body('Walec',kernel.cylinder(**v)).prepared(),self.add_prepared,True)

    def add_sketch(self):
        dialog=QDialog(self);dialog.setWindowTitle("Nowy szkic")
        form=QFormLayout(dialog);kind=QComboBox();kind.addItem('Prostokąt','rectangle');kind.addItem('Okrąg','circle');kind.addItem('Wielokąt','polygon')
        plane=QComboBox();plane.addItems(['XY','XZ','YZ']);form.addRow('Figura',kind);form.addRow('Płaszczyzna',plane)
        controls={}
        for key,label,value,minimum in [('width','Szerokość / średnica (mm)',30,.001),('height','Wysokość prostokąta (mm)',20,.001),('x','Środek U (mm)',0,-1e6),('y','Środek V (mm)',0,-1e6),('sides','Boki wielokąta',6,3)]:
            spin=QDoubleSpinBox();spin.setRange(minimum,128 if key=='sides' else 1e6);spin.setDecimals(0 if key=='sides' else 3);spin.setValue(value);form.addRow(label,spin);controls[key]=spin
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()!=QDialog.Accepted:return
        values={k:w.value() for k,w in controls.items()};p=plane.currentText();k=kind.currentData()
        self.run_operation("Tworzenie szkicu",lambda: Body('Szkic '+p,kernel.sketch(k,p,**values),'sketch',p).prepared(),self.add_prepared,True)

    def extrude_sketch(self):
        body=self.selected_body('sketch')
        if not body:return
        v=values_dialog(self,'Wyciągnięcie',[('distance','Odległość (mm)',20,-1e6)])
        if v:self.run_operation('Wyciąganie szkicu',lambda: Body('Wyciągnięcie',kernel.extrude(body.shape,body.plane,**v)).prepared(),self.add_prepared,True)

    def make_hole(self):
        body=self.selected_body()
        if not body:return
        c=body.shape.Center();v=values_dialog(self,'Otwór w osi Z',[('radius','Promień (mm)',4,.001),('x','Środek X (mm)',c.x,-1e6),('y','Środek Y (mm)',c.y,-1e6),('depth','Głębokość; 0 = przelot (mm)',0,0)])
        if v:self.run_operation('Wykonywanie otworu',lambda: body.changed(kernel.hole(body.shape,**v)),lambda r:self.replace_body(body,r))

    def combine(self, operation):
        bodies=[b for i in self.selected if (b:=self.document.get(i)) and b.kind=='solid']
        if len(bodies)<2:
            QMessageBox.information(self,'Wybierz bryły','W drzewie zaznacz co najmniej dwie bryły z Ctrl. Pierwsza jest bazą, kolejne narzędziami.');return
        base,tools=bodies[0],bodies[1:];ids={b.id for b in bodies}
        def build():
            result=base.changed(kernel.boolean(operation,base.shape,[b.shape for b in tools]))
            return [result if b.id==base.id else b for b in self.document.bodies if b.id==base.id or b.id not in ids]
        self.run_operation('Operacja na bryłach',build,lambda r:self.replace_body(base,r))

    def start_blend(self, kind):
        self.view.edge_mode=True;self.blend_panel.show();self.blend_type.setCurrentIndex(0 if kind=='fillet' else 1)
        self.statusBar().showMessage('Kliknij krawędź bryły. Shift + klik dodaje kolejne. Następnie Zastosuj.')

    def end_blend(self):
        self.view.edge_mode=False;self.edges.clear();self.blend_panel.hide();self.refresh()

    def apply_blend(self):
        if self.busy:return
        if len(self.edges)!=1 or not next(iter(self.edges.values()),None):
            QMessageBox.information(self,'Wybierz krawędź','Zaznacz krawędzie jednej bryły w widoku 3D.');return
        identifier,ids=next(iter(self.edges.items()));body=self.document.get(identifier)
        if not body or body.kind!='solid':return
        size=self.blend_size.value();kind=self.blend_type.currentData()
        self.run_operation('Zaokrąglanie' if kind=='fillet' else 'Fazowanie',lambda:body.changed(kernel.blend(body.shape,ids,size,kind)),lambda r:self.replace_body(body,r))

    def transform_body(self):
        body=self.selected_body()
        if not body:return
        fields=[(k,label,0,-1e6) for k,label in [('x','Przesunięcie X (mm)'),('y','Przesunięcie Y (mm)'),('z','Przesunięcie Z (mm)'),('rx','Obrót X (°)'),('ry','Obrót Y (°)'),('rz','Obrót Z (°)')]]
        v=values_dialog(self,'Przenieś / obróć',fields)
        if v:self.run_operation('Transformacja',lambda:body.changed(kernel.transform(body.shape,(v['x'],v['y'],v['z']),(v['rx'],v['ry'],v['rz']))),lambda r:self.replace_body(body,r),True)

    def mirror_body(self):
        body=self.selected_body()
        if not body:return
        dialog=QDialog(self);dialog.setWindowTitle('Odbicie lustrzane');form=QFormLayout(dialog);plane=QComboBox();plane.addItems(['XY','XZ','YZ']);form.addRow('Płaszczyzna przez początek układu',plane)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()==QDialog.Accepted:
            p=plane.currentText();self.run_operation('Odbicie lustrzane',lambda:Body(body.name+' — odbicie',kernel.mirror(body.shape,p)).prepared(),self.add_prepared,True)

    def duplicate_body(self):
        body=self.selected_body()
        if body:self.run_operation('Duplikowanie',lambda:Body(body.name+' — kopia',kernel.transform(body.shape,(10,10,0))).prepared(),self.add_prepared,True)

    def delete_selected(self):
        if not self.busy and self.selected:
            self.document.commit([b for b in self.document.bodies if b.id not in self.selected]);self.clear_selection()

    def toggle_grid(self):
        self.view.grid_item.setVisible(not self.view.grid_item.visible())

    def clear_selection(self):
        if self.busy:return
        self.selected=[];self.edges={};self.refresh()

    def body_clicked(self, identifier, additive):
        if self.busy:return
        if additive:self.selected=self.selected+[identifier] if identifier not in self.selected else [i for i in self.selected if i!=identifier]
        else:self.selected=[identifier]
        self.edges={};self.refresh()

    def edge_clicked(self, identifier, index, additive):
        if self.busy:return
        body=self.document.get(identifier)
        if not body or body.kind!='solid':return
        if not additive or identifier not in self.edges:self.edges={identifier:{index}}
        elif index in self.edges[identifier]:self.edges[identifier].remove(index)
        else:self.edges[identifier].add(index)
        self.selected=[identifier];self.refresh()

    def tree_selection(self):
        if self.busy:return
        ids=[item.data(0,Qt.UserRole) for item in self.tree.selectedItems()]
        self.selected=[i for i in self.selected if i in ids]+[i for i in ids if i not in self.selected]
        self.edges={};self.refresh()

    def visibility_changed(self, item, column):
        if self.busy:return
        identifier=item.data(0,Qt.UserRole)
        body=self.document.get(identifier)
        if body:
            self.document.commit([replace(b,visible=item.checkState(0)==Qt.Checked,name=item.text(0)) if b.id==identifier else b for b in self.document.bodies]);self.refresh()

    def undo(self):
        if not self.busy:self.document.undo();self.edges={};self.refresh()

    def redo(self):
        if not self.busy:self.document.redo();self.edges={};self.refresh()

    def confirm_discard(self):
        if self.busy:
            QMessageBox.information(self,'Trwa operacja','Poczekaj na zakończenie bieżącej operacji.');return False
        if not self.document.dirty:return True
        reply=QMessageBox.question(self,'Niezapisane zmiany','Odrzucić niezapisane zmiany?',QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Cancel)
        return reply==QMessageBox.Discard

    def new_project(self):
        if self.confirm_discard():self.document=Document();self.selected=[];self.edges={};self.refresh(True)

    def open_project(self):
        if not self.confirm_discard():return
        path,_=QFileDialog.getOpenFileName(self,'Otwórz projekt','','RCCAD Desktop (*.rccadx)')
        if path:self.run_operation('Otwieranie projektu',lambda:Document.load(path),self._loaded,True)

    def _loaded(self, document):
        self.document=document;self.selected=[];self.edges={}

    def save_project(self, save_as=False):
        path=self.document.path
        if save_as or path is None:
            value,_=QFileDialog.getSaveFileName(self,'Zapisz projekt',str(path or 'Projekt.rccadx'),'RCCAD Desktop (*.rccadx)')
            if not value:return
            path=Path(value)
            if path.suffix.lower()!='.rccadx':path=path.with_suffix('.rccadx')
        self.run_operation('Zapisywanie projektu',lambda:self.document.save(path),lambda _:None)

    def import_model(self):
        path,_=QFileDialog.getOpenFileName(self,'Importuj model','','Modele CAD (*.step *.stp *.brep *.brp *.stl *.dxf)')
        if not path:return
        def build():
            return [Body(Path(path).stem if i==0 else f'{Path(path).stem} {i+1}',s,kind).prepared() for i,(s,kind) in enumerate(kernel.import_shapes(path))]
        def add(bodies):
            if not bodies:raise kernel.CadError('Plik nie zawiera obsługiwanej geometrii.')
            self.document.commit((*self.document.bodies,*bodies));self.selected=[b.id for b in bodies]
            if any(b.kind=='mesh' for b in bodies):QMessageBox.information(self,'Import STL','STL jest siatką do podglądu i eksportu. Do dokładnego modelowania i zaokrągleń użyj STEP lub BREP.')
        self.run_operation('Importowanie modelu',build,add,True)

    def export_model(self):
        bodies=[b for b in self.document.bodies if b.id in self.selected] if self.selected else [b for b in self.document.bodies if b.visible]
        if not bodies:QMessageBox.information(self,'Eksport','Brak geometrii do eksportu.');return
        path,_=QFileDialog.getSaveFileName(self,'Eksportuj zaznaczone lub widoczne obiekty','Model.step','STEP (*.step);;STL (*.stl);;BREP (*.brep);;DXF — szkice (*.dxf)')
        if path:self.run_operation('Eksportowanie',lambda:kernel.export_shapes([b.shape for b in bodies],path),lambda _:None)

    def closeEvent(self,event):
        if self.confirm_discard():event.accept()
        else:event.ignore()
