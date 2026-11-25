import concurrent.futures
import io
import json
import sys
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
import trimesh
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import make_server, GEOMETRY_SLOT
from generador import audit, generate, prepare

class GeometryTests(unittest.TestCase):
    def test_reopened_stl(self):
        for name in ('Elisa', 'Adrián', 'ADRIÁN', 'Toñi', 'Iñaki', 'María', 'Maximiliano'):
            with self.subTest(name=name):
                mesh, report = generate(name)
                exported = mesh.export(file_type='stl')
                checked = audit(trimesh.load_mesh(io.BytesIO(exported), file_type='stl'))
                self.assertEqual(checked['piezas'], 2)
                self.assertTrue(checked['cerrada'])
                self.assertEqual(checked['bordes_abiertos'], 0)
                self.assertEqual(checked['aristas_non_manifold'], 0)
                for mark in report['apoyos_de_marcas']:
                    self.assertGreater(mark['solape_marca_mm2'], .02)
                    self.assertGreater(mark['solape_letra_mm2'], .02)

    def test_invalid_inputs(self):
        for name, size, shift in (('',19.5,0), ('A'*19,19.5,0), ('<script>',19.5,0), ('Elisa',float('nan'),0), ('Elisa',19.5,4)):
            with self.subTest(name=name, size=size, shift=shift):
                with self.assertRaises(ValueError): prepare(name,size,shift)

class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=make_server('127.0.0.1',0)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()
    def test_health_and_no_history(self):
        self.assertEqual(json.load(urllib.request.urlopen(self.base+'/healthz'))['version'],'0.1.0')
        with urllib.request.urlopen(self.base+'/export?'+urllib.parse.urlencode({'nombre':'Adrián'})) as response:
            self.assertIn('adorno-adrian.stl',response.headers['Content-Disposition'])
            mesh=trimesh.load_mesh(io.BytesIO(response.read()),file_type='stl')
            self.assertTrue(audit(mesh)['cerrada'])
        self.assertFalse((Path(__file__).resolve().parents[1]/'salidas').exists())
    def test_busy_returns_429_but_health_available(self):
        GEOMETRY_SLOT.acquire()
        try:
            self.assertEqual(urllib.request.urlopen(self.base+'/healthz').status,200)
            with self.assertRaises(urllib.error.HTTPError) as ctx: urllib.request.urlopen(self.base+'/export?nombre=Elisa')
            self.assertEqual(ctx.exception.code,429)
        finally: GEOMETRY_SLOT.release()
    def test_invalid_name(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx: urllib.request.urlopen(self.base+'/export?nombre=%3Cscript%3E')
        self.assertEqual(ctx.exception.code,400)

if __name__=='__main__': unittest.main()
