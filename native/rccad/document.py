"""Immutable model revisions, atomic project files and undo/redo."""
from __future__ import annotations
from dataclasses import dataclass, field, replace
import json
import os
from pathlib import Path
import re
import tempfile
import uuid
from zipfile import ZipFile, ZIP_DEFLATED
import cadquery as cq
from .kernel import CadError, DisplayMesh, display_mesh, valid


@dataclass(frozen=True)
class Body:
    name: str
    shape: cq.Shape = field(compare=False, repr=False)
    kind: str = "solid"
    plane: str = "XY"
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    visible: bool = True
    mesh: DisplayMesh | None = field(default=None, compare=False, repr=False)

    frame: tuple | None = None
    support_id: str | None = None
    sketch_data: dict | None = field(default=None, compare=False)

    def prepared(self):
        return replace(self, mesh=display_mesh(self.shape))

    def changed(self, shape):
        return replace(self, shape=shape, mesh=display_mesh(shape))


class Document:
    def __init__(self):
        self.bodies: tuple[Body, ...] = ()
        self._undo = []
        self._redo = []
        self.path: Path | None = None
        self._revision = 0
        self._saved_revision = 0
        self._next_revision = 1

    @property
    def dirty(self):
        return self._revision != self._saved_revision

    @property
    def can_undo(self):
        return bool(self._undo)

    @property
    def can_redo(self):
        return bool(self._redo)

    def get(self, body_id):
        return next((b for b in self.bodies if b.id == body_id), None)

    def commit(self, bodies):
        bodies = tuple(bodies)
        if len({b.id for b in bodies}) != len(bodies):
            raise CadError("Powtórzony identyfikator obiektu.")
        self._undo.append((self.bodies, self._revision))
        self._undo = self._undo[-40:]
        self._redo.clear()
        self.bodies = bodies
        self._revision = self._next_revision
        self._next_revision += 1

    def undo(self):
        if self._undo:
            self._redo.append((self.bodies, self._revision))
            self.bodies, self._revision = self._undo.pop()

    def redo(self):
        if self._redo:
            self._undo.append((self.bodies, self._revision))
            self.bodies, self._revision = self._redo.pop()

    def save(self, path):
        path = Path(path)
        manifest = {"app": "RCCAD_DESKTOP", "version": 1, "units": "mm", "bodies": []}
        temp_path = None
        try:
            fd, temp_path = tempfile.mkstemp(prefix=".rccad-", suffix=".tmp", dir=path.parent)
            os.close(fd)
            with tempfile.TemporaryDirectory(prefix="rccad-brep-") as work, ZipFile(temp_path, "w", ZIP_DEFLATED) as archive:
                for body in self.bodies:
                    source = Path(work) / f"{body.id}.brep"
                    cq.exporters.export(body.shape, str(source), exportType="BREP")
                    member = f"bodies/{body.id}.brep"
                    archive.write(source, member)
                    manifest['bodies'].append(dict(id=body.id, name=body.name, kind=body.kind, plane=body.plane, visible=body.visible, file=member, frame=body.frame, support_id=body.support_id, sketch_data=body.sketch_data))
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
            os.replace(temp_path, path)
            self.path = path
            self._saved_revision = self._revision
        finally:
            if temp_path and Path(temp_path).exists():
                Path(temp_path).unlink()

    @classmethod
    def load(cls, path):
        result = cls()
        try:
            with ZipFile(path) as archive, tempfile.TemporaryDirectory(prefix="rccad-open-") as work:
                infos = archive.infolist()
                if len(infos) > 2001 or sum(i.file_size for i in infos) > 2_000_000_000:
                    raise CadError("Projekt jest zbyt duży.")
                if archive.getinfo("manifest.json").file_size > 2_000_000:
                    raise CadError("Nieprawidłowy manifest projektu.")
                manifest = json.loads(archive.read("manifest.json"))
                if manifest.get('app') != 'RCCAD_DESKTOP' or manifest.get('version') != 1 or not isinstance(manifest.get('bodies'), list):
                    raise CadError("To nie jest obsługiwany projekt RCCAD Desktop.")
                bodies, ids = [], set()
                for item in manifest['bodies']:
                    identifier = str(item['id'])
                    if not re.fullmatch('[0-9a-f]{32}', identifier) or identifier in ids or item['file'] != f'bodies/{identifier}.brep':
                        raise CadError("Nieprawidłowa struktura projektu.")
                    kind = item.get('kind', 'solid')
                    plane = item.get('plane', 'XY')
                    if kind not in ('solid', 'mesh', 'sketch') or plane not in ('XY', 'XZ', 'YZ'):
                        raise CadError("Nieprawidłowy typ obiektu lub płaszczyzna.")
                    ids.add(identifier)
                    source = Path(work) / (identifier + '.brep')
                    source.write_bytes(archive.read(item['file']))
                    shape = cq.importers.importBrep(str(source)).val()
                    valid(shape, kind == 'solid')
                    from .interaction import checked_frame
                    frame = checked_frame(item['frame']) if item.get('frame') is not None else None
                    support = item.get('support_id')
                    if support is not None and not re.fullmatch('[0-9a-f]{32}', str(support)):
                        raise CadError("Nieprawidłowe powiązanie szkicu.")
                    bodies.append(Body(str(item['name']), shape, kind, plane, identifier, bool(item.get('visible', True)), frame=frame, support_id=support, sketch_data=checked_sketch_data(item.get('sketch_data'))).prepared())
                result.bodies = tuple(bodies)
                result.path = Path(path)
                return result
        except CadError:
            raise
        except Exception as exc:
            raise CadError("Nie można otworzyć projektu. Plik może być uszkodzony lub mieć inny format.") from exc


def checked_sketch_data(data):
    if data is None:return None
    if not isinstance(data,dict) or len(json.dumps(data))>100000:raise CadError('Nieprawidłowy opis szkicu.')
    if not isinstance(data.get('type'),str) or len(data['type'])>32:raise CadError('Nieprawidłowe narzędzie szkicu.')
    pts=data.get('points',[])
    import math
    if not isinstance(pts,list) or len(pts)>4096 or any(not isinstance(p,(list,tuple)) or len(p)!=2 or any(not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>1e9 for v in p) for p in pts):raise CadError('Nieprawidłowe punkty szkicu.')
    return data
