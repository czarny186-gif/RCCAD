"""Native widget actions and background computation; no browser automation."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen' if not os.environ.get('DISPLAY') and os.name!='nt' else '')
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QThread
from PySide6.QtWidgets import QApplication,QMessageBox
from rccad import kernel as k
from rccad.document import Body
from rccad.window import MainWindow


class NativeUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.window=MainWindow()
        self.window.resize(1200,850)
        self.window.layout().activate()
        self.warning=patch.object(QMessageBox,'warning',return_value=QMessageBox.Ok)
        self.warning_mock=self.warning.start()
        self.info=patch.object(QMessageBox,'information',return_value=QMessageBox.Ok)
        self.info.start()

    def tearDown(self):
        self.wait()
        self.window.pool.waitForDone(5000)
        self.window.document._saved_revision=self.window.document._revision
        self.window.close()
        self.app.processEvents()
        self.warning.stop();self.info.stop()

    def wait(self):
        end=time.monotonic()+15
        while self.window.busy and time.monotonic()<end:
            self.app.processEvents();time.sleep(.005)
        self.app.processEvents()
        self.assertFalse(self.window.busy,'Background CAD operation did not finish')

    def add_box(self):
        with patch('rccad.window.values_dialog',return_value={'x':30,'y':30,'z':30}):
            self.window.add_box()
        self.wait()
        self.assertEqual(len(self.window.document.bodies),1)

    def test_creation_updates_native_tree_properties_and_undo(self):
        self.add_box()
        self.assertEqual(self.window.tree.topLevelItemCount(),1)
        self.assertIn('Objętość',self.window.properties.text())
        self.window.undo();self.assertEqual(len(self.window.document.bodies),0)
        self.window.redo();self.assertEqual(len(self.window.document.bodies),1)

    def test_worker_applies_result_on_gui_thread(self):
        threads=[]
        self.window.run_operation('Test',lambda:Body('A',k.box(10,10,10)).prepared(),lambda body:(threads.append(QThread.currentThread()),self.window.add_prepared(body)))
        self.wait()
        self.assertEqual(threads,[self.app.thread()])

    def test_failed_operation_keeps_model(self):
        self.add_box();body=self.window.document.bodies[0]
        self.window.run_operation('Błąd',lambda:body.changed(k.blend(body.shape,[0],1000)),lambda r:self.window.replace_body(body,r))
        self.wait()
        self.assertEqual(self.window.document.bodies[0],body)
        self.assertEqual(self.warning_mock.call_count,1)
        self.assertTrue(self.window.tree.isEnabled())

    def test_edge_selection_and_fillet_apply(self):
        self.add_box();body=self.window.document.bodies[0]
        self.window.start_blend('fillet')
        self.window.edge_clicked(body.id,0,False)
        self.window.edge_clicked(body.id,1,False)
        self.assertEqual(self.window.edges,{body.id:{1}})
        self.window.edge_clicked(body.id,2,True)
        self.assertEqual(self.window.edges,{body.id:{1,2}})
        self.window.blend_size.setValue(2)
        self.window.apply_blend();self.wait()
        self.assertLess(self.window.document.bodies[0].shape.Volume(),27000)
        self.assertFalse(self.window.edges)
        self.assertEqual(self.warning_mock.call_count,0)

    def test_save_and_open_through_native_actions(self):
        self.add_box()
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/'ui.rccadx')
            with patch('rccad.window.QFileDialog.getSaveFileName',return_value=(path,'')):
                self.window.save_project()
            self.wait();self.assertFalse(self.window.document.dirty)
            self.window.new_project();self.assertFalse(self.window.document.bodies)
            with patch('rccad.window.QFileDialog.getOpenFileName',return_value=(path,'')):
                self.window.open_project()
            self.wait();self.assertEqual(len(self.window.document.bodies),1)
            self.assertAlmostEqual(self.window.document.bodies[0].shape.Volume(),27000)

    def test_export_and_import_through_native_actions(self):
        self.add_box()
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/'ui.step')
            with patch('rccad.window.QFileDialog.getSaveFileName',return_value=(path,'')):
                self.window.export_model()
            self.wait();self.assertTrue(Path(path).exists())
            with patch('rccad.window.QFileDialog.getOpenFileName',return_value=(path,'')):
                self.window.import_model()
            self.wait();self.assertEqual(len(self.window.document.bodies),2)
            self.assertEqual(self.warning_mock.call_count,0)

    def test_visibility_is_reversible(self):
        self.add_box()
        item=self.window.tree.topLevelItem(0)
        item.setCheckState(0,Qt.Unchecked)
        self.assertFalse(self.window.document.bodies[0].visible)
        self.window.undo();self.assertTrue(self.window.document.bodies[0].visible)


if __name__=='__main__':unittest.main()
