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
import numpy as np
import shapely
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import make_server, GEOMETRY_SLOT
from generador import audit, generate, prepare, text_shape, TEXT_RADIUS

class GeometryTests(unittest.TestCase):
    def test_reopened_stl(self):
        for name in ('Elsa', 'Elisa', 'Adrián', 'ADRIÁN', 'Toñi', 'Iñaki', 'María', 'Maximiliano', 'I'):
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

    def test_maximum_fit_keeps_proportions_and_clearance(self):
        for name in ('Elsa', 'Adrián', 'I', 'Maximiliano'):
            for shift in (-3, 0, 3):
                with self.subTest(name=name, shift=shift):
                    raw=text_shape(name)
                    _,text,_,_=prepare(name,shift=shift)
                    coords=shapely.get_coordinates(text)-[1.64,1.03]
                    self.assertLessEqual(np.linalg.norm(coords,axis=1).max(),TEXT_RADIUS)
                    # Increasing the text by 0.1 % must exceed the safe disc.
                    larger=(coords-[0,shift])*1.001+[0,shift]
                    self.assertGreater(np.linalg.norm(larger,axis=1).max(),TEXT_RADIUS)
                    a,b,c,d=raw.bounds; x,y,z,w=text.bounds
                    self.assertAlmostEqual((z-x)/(w-y),(c-a)/(d-b),places=8)
                    self.assertEqual(sum(len(p.interiors) for p in getattr(raw,'geoms',[raw])),
                                     sum(len(p.interiors) for p in getattr(text,'geoms',[text])))
        _,_,_,report=prepare('Elsa')
        self.assertGreater(report['ancho_texto_mm'],47)
        self.assertGreater(report['alto_texto_mm'],21)

    def test_scale_control_has_effect_throughout_range(self):
        for name in ('Elsa', 'Maximiliano'):
            full=prepare(name)[3]
            for percent in (40,70,99):
                report=prepare(name,fill=percent)[3]
                self.assertAlmostEqual(report['ancho_texto_mm']/full['ancho_texto_mm'],percent/100,places=4)
        for invalid in (39,101,float('nan'),float('inf')):
            with self.assertRaises(ValueError): prepare('Elsa',fill=invalid)

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
        self.assertEqual(json.load(urllib.request.urlopen(self.base+'/healthz'))['version'],'0.1.1')
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

    def test_preview_uses_automatic_fit_and_scale(self):
        full=json.load(urllib.request.urlopen(self.base+'/preview?nombre=Elsa'))['info']
        reduced=json.load(urllib.request.urlopen(self.base+'/preview?nombre=Elsa&escala=80'))['info']
        self.assertGreater(full['ancho_texto_mm'],47)
        self.assertAlmostEqual(reduced['ancho_texto_mm']/full['ancho_texto_mm'],.8,places=4)

if __name__=='__main__': unittest.main()
