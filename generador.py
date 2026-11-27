"""Personalizador local. Geometría base extraída de Fusion, unidades mm."""
from pathlib import Path
from functools import lru_cache
import json, math, unicodedata
import numpy as np
import shapely
from shapely.geometry import Polygon, LineString, box, Point
from shapely.ops import unary_union, polygonize, nearest_points
from shapely.affinity import scale, translate
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
import uharfbuzz as hb
import trimesh
import manifold3d as manifold

ROOT=Path(__file__).resolve().parent
FONT=ROOT/'assets/Lobster-Regular.ttf'

class Contours(BasePen):
    def __init__(self, gs):
        super().__init__(gs); self.rings=[]; self.cur=[]
    def _moveTo(self,p): self.cur=[p]
    def _lineTo(self,p): self.cur.append(p)
    def _curveToOne(self,a,b,c):
        p=self.cur[-1]
        for t in np.linspace(0,1,25)[1:]:
            self.cur.append(tuple((1-t)**3*p[j]+3*(1-t)**2*t*a[j]+3*(1-t)*t*t*b[j]+t**3*c[j] for j in range(2)))
    def _qCurveToOne(self,a,b):
        p=self.cur[-1]
        for t in np.linspace(0,1,20)[1:]:
            self.cur.append(tuple((1-t)**2*p[j]+2*(1-t)*t*a[j]+t*t*b[j] for j in range(2)))
    def _closePath(self):
        if len(self.cur)>=3: self.rings.append(self.cur+[self.cur[0]])
        self.cur=[]
    def _endPath(self): self._closePath()

def winding(pt, ring):
    x,y=pt; n=0
    for a,b in zip(ring,ring[1:]):
        cross=(b[0]-a[0])*(y-a[1])-(x-a[0])*(b[1]-a[1])
        if a[1]<=y<b[1] and cross>0: n+=1
        elif b[1]<=y<a[1] and cross<0: n-=1
    return n

def text_shape(name, with_glyphs=False):
    data=FONT.read_bytes(); face=hb.Face(data); font=hb.Font(face)
    font.scale=(face.upem,face.upem); hb.ot_font_set_funcs(font)
    buf=hb.Buffer(); buf.add_str(name); buf.guess_segment_properties(); hb.shape(font,buf,{'kern':True,'liga':True})
    tt=TTFont(FONT); gs=tt.getGlyphSet(); order=tt.getGlyphOrder(); x=y=0; polys=[]; glyphs=[]
    for info,pos in zip(buf.glyph_infos,buf.glyph_positions):
        if info.codepoint==0: raise ValueError('La fuente no tiene alguno de estos caracteres.')
        pen=Contours(gs); gs[order[info.codepoint]].draw(pen)
        rings=[[(a+x+pos.x_offset,b+y+pos.y_offset) for a,b in r] for r in pen.rings]
        cells=list(polygonize(unary_union([LineString(r) for r in rings])))
        glyph_polys=[]
        for cell in cells:
            p=cell.representative_point()
            if sum(winding((p.x,p.y),r) for r in rings)!=0: glyph_polys.append(cell)
        if glyph_polys:
            glyphs.append(unary_union(glyph_polys))
            polys.extend(glyph_polys)
        x+=pos.x_advance; y+=pos.y_advance
    shape=unary_union(polys)
    return (shape,glyphs) if with_glyphs else shape

def load_base():
    p=ROOT/'assets/referencia-fusion.json'
    if not p.exists(): raise ValueError('La referencia de Fusion aún no se ha extraído.')
    raw=json.loads(p.read_text()); meshes={}
    for name,obj in raw.items():
        m=trimesh.Trimesh(vertices=np.array(obj['vertices'])-[470,0,0],faces=obj['faces'],process=True)
        m.merge_vertices(digits_vertex=5); m.remove_unreferenced_vertices(); m.fix_normals()
        if not m.is_watertight: raise ValueError('La base de Fusion tiene bordes abiertos: '+name)
        meshes['copo' if 'copo' in name else 'aro']=m
    return meshes

def components(g): return list(g.geoms) if g.geom_type=='MultiPolygon' else [g]
def extrude(g,h):
    return trimesh.util.concatenate([trimesh.creation.extrude_polygon(p,h,engine='earcut') for p in components(g) if p.area>1e-8])

def centered_accent_link(mark, body):
    # Aim through the material at the centre of the mark, rather than its tip.
    safe_mark=mark.buffer(-.2)
    if safe_mark.is_empty: safe_mark=mark
    point=safe_mark.centroid
    if not safe_mark.covers(point): point=safe_mark.representative_point()
    safe_body=body.buffer(-.25)
    if safe_body.is_empty: safe_body=body
    vertical=LineString([(point.x,body.bounds[1]-1),(point.x,point.y)])
    section=safe_body.intersection(vertical)
    _,nearest_anchor=nearest_points(point,safe_body)
    if not section.is_empty:
        def points(geom):
            if hasattr(geom,'geoms'):
                return [p for part in geom.geoms for p in points(part)]
            return list(geom.coords)
        anchor=max(points(section),key=lambda p:p[1])
        anchor=Point(anchor)
        if anchor.distance(point)>1.6*nearest_anchor.distance(point):
            anchor=nearest_anchor
    else:
        anchor=nearest_anchor
    link=LineString([anchor,point]).buffer(.5,cap_style='round',quad_segs=12)
    mark_overlap=link.intersection(mark).area
    body_overlap=link.intersection(body).area
    if min(mark_overlap,body_overlap)<.02:
        raise ValueError('No se ha conseguido un apoyo suficiente para una tilde o punto.')
    return link,{'centro_marca_mm':[round(point.x,3),round(point.y,3)],
                 'anclaje_letra_mm':[round(anchor.x,3),round(anchor.y,3)],
                 'solape_marca_mm2':round(mark_overlap,4),'solape_letra_mm2':round(body_overlap,4)}

TEXT_RADIUS=24.4  # The reference ring's inner radius is approximately 25 mm.
MAX_FILL=106  # Overlap the inner edge without reaching the ring's outer edge.

@lru_cache(maxsize=1)
def ring_outline():
    mesh=load_base()['aro']
    return unary_union([Polygon(triangle[:,:2]) for triangle in mesh.triangles
                        if Polygon(triangle[:,:2]).area>1e-9])

def attachment_report(text):
    ring=ring_outline()
    anchor=ring.buffer(-.4).representative_point()
    joined=unary_union([ring,text])
    loose=sum(not part.covers(anchor) for part in components(joined))
    overlap=text.intersection(ring).area
    # Remove 0.4 mm from both sides to find necks below 0.8 mm. Test
    # substantial letter cores, ignoring tiny fragments of curved outlines.
    eroded=joined.buffer(-.4)
    attached=unary_union([part for part in components(eroded) if part.covers(anchor)])
    weak=any(part.area>.05 and part.difference(attached).area>.05
             for part in components(text.buffer(-.4)))
    if loose:
        state='suelto'
        detail='queda una parte' if loose==1 else f'quedan {loose} partes'
        message=f'Sin la base {detail} del nombre sin unir al aro. Aumenta el tamaño o activa el helper de base para descargar.'
    elif overlap<1 or weak:
        state='debil'
        message='El nombre toca el aro, pero alguna unión es demasiado pequeña. Aumenta el tamaño o activa el helper de base para descargar.'
    else:
        state='unido'
        message='Sin base: el nombre y sus puntos o acentos quedan unidos al aro. Resistencia pendiente de prueba física.'
    return {'estado':state,'partes_sueltas':loose,'solape_aro_mm2':round(overlap,4),
            'solape_minimo_mm2':1,'cuello_minimo_mm':.8,'aviso':message}

def fit_text(raw, glyphs, size, shift, fill):
    a,b,c,d=raw.bounds
    cx=(a+c)/2
    points=shapely.get_coordinates(raw)
    # Find the vertical centre that admits the largest proportional text.
    # The maximum squared radius is convex in the centre's Y coordinate.
    lo,hi=b,d
    def radius_squared(y):
        return np.max((points[:,0]-cx)**2+(points[:,1]-y)**2)
    for _ in range(64):
        left,right=(2*lo+hi)/3,(lo+2*hi)/3
        if radius_squared(left)<radius_squared(right): hi=right
        else: lo=left
    cy=(lo+hi)/2
    centered=points-[cx,cy]
    squared=np.sum(centered**2,axis=1)
    valid=squared>0
    # Solve |factor * vertex + (0, shift)| <= TEXT_RADIUS for every
    # contour vertex, including accents. A segment stays inside the disc
    # whenever its endpoints do, so this also bounds the full outline.
    cross=centered[valid,1]*shift
    limits=(-cross+np.sqrt(cross**2+squared[valid]*(TEXT_RADIUS**2-shift**2)))/squared[valid]
    factor=float(limits.min())*(1-1e-8)
    if size is not None: factor=min(factor,size/(d-b))
    factor*=fill/100
    def transform(shape):
        shape=translate(shape,xoff=-cx,yoff=-cy)
        shape=scale(shape,xfact=factor,yfact=factor,origin=(0,0))
        return translate(shape,xoff=1.64,yoff=1.03+shift)
    return transform(raw),[transform(glyph) for glyph in glyphs]

def prepare(name='Elisa',size=None,shift=0,*,fill=100,base_helper_enabled=True):
    name=unicodedata.normalize('NFC',name.strip())
    if not name or len(name)>18: raise ValueError('Escribe un nombre de entre 1 y 18 caracteres.')
    if any(not(c.isalpha() or c in ' -') for c in name): raise ValueError('Usa letras, espacios o guiones.')
    size=float(size) if size is not None else None
    shift=float(shift); fill=float(fill)
    if (size is not None and not 8<=size<=48) or not -3<=shift<=3 or not 40<=fill<=MAX_FILL:
        raise ValueError('El tamaño o la posición están fuera del rango permitido.')
    raw,glyphs=text_shape(name,with_glyphs=True)
    text,glyphs=fit_text(raw,glyphs,size,shift,fill)
    a,b,c,d=text.bounds
    report={'nombre':name,'ancho_texto_mm':round(c-a,3),'alto_texto_mm':round(d-b,3),
            'escala_porcentaje':fill,
            'radio_limite_texto_mm':round(TEXT_RADIUS*fill/100+abs(shift)*abs(1-fill/100),3),
            'letras_z_mm':3,'helpers_z_mm':1.2,'helpers_ancho_mm':1,'version_helpers':2,
            'helper_base':base_helper_enabled,'apoyos_de_marcas':[], 'enlaces_automaticos':0,
            'puede_exportar':True,
            'aviso':('Nombre reducido: revisa que los trazos sean adecuados para tu impresora.' if d-b<10 else 'Prototipo: pendiente de prueba física de impresión.')}
    accent_links=[]; anchors=[]
    for glyph in glyphs:
        parts=components(glyph)
        if len(parts)<2: continue
        body=max(parts,key=lambda p:p.area)
        for mark in parts:
            if mark is body or mark.bounds[1]<body.bounds[3]-.05: continue
            link,info=centered_accent_link(mark,body)
            accent_links.append(link); anchors.append(info)
    report.update(apoyos_de_marcas=anchors,enlaces_automaticos=len(accent_links))
    if not base_helper_enabled:
        helpers=unary_union(accent_links)
        support=attachment_report(unary_union([text,helpers]))
        report.update(sujecion=support,puede_exportar=support['estado']=='unido')
        return name,text,helpers,report
    bar_y=b+1.65
    half=math.sqrt(26.5**2-(bar_y-1.03)**2)
    helpers=box(1.64-half,bar_y-.5,1.64+half,bar_y+.5)
    # Join each accent to its own glyph first. Only then connect whole regions
    # to the bar, so a detached support cannot be mistaken for the main body.
    pending=components(unary_union([text,*accent_links])); connected=helpers
    links=list(accent_links)
    helpers=unary_union([helpers,*accent_links])
    while pending:
        i=min(range(len(pending)),key=lambda j:pending[j].distance(connected))
        region=pending.pop(i)
        if region.distance(connected)>0:
            p,q=nearest_points(region,connected)
            link=LineString([p,q]).buffer(.5,cap_style='round',quad_segs=8)
            links.append(link); helpers=unary_union([helpers,link])
            connected=unary_union([connected,link])
        connected=unary_union([connected,region])
    report.update(apoyos_de_marcas=anchors,enlaces_automaticos=len(links))
    return name,text,helpers,report

def solid_union(meshes):
    combined=None
    for mesh in meshes:
        solid=manifold.Manifold(manifold.Mesh64(np.array(mesh.vertices,dtype=np.float64,order="C",copy=True),np.array(mesh.faces,dtype=np.uint64,order="C",copy=True)))
        if solid.status()!=manifold.Error.NoError: raise ValueError('Una pieza no tiene un volumen válido para unir.')
        combined=solid if combined is None else combined+solid
    data=combined.simplify().to_mesh64()
    return trimesh.Trimesh(vertices=data.vert_properties[:,:3],faces=data.tri_verts,process=False)

def generate(name='Elisa',size=None,shift=0,*,fill=100,base_helper_enabled=True):
    name,text,helpers,report=prepare(name,size,shift,fill=fill,base_helper_enabled=base_helper_enabled)
    if not report['puede_exportar']: raise ValueError(report['sujecion']['aviso'])
    base=load_base()
    lower=extrude(unary_union([text,helpers]),1.2)
    upper=extrude(text,1.81)
    upper.apply_translation([0,0,1.19])
    inner=solid_union([base['aro'],lower,upper])
    if len(inner.split())!=1: raise ValueError('El nombre o algún helper no ha quedado unido al aro.')
    result=trimesh.util.concatenate([inner,base['copo']])
    report.update(audit(result))
    if report['piezas']!=2 or report['bordes_abiertos'] or report['aristas_non_manifold']:
        raise ValueError('La malla generada no supera la comprobación: '+json.dumps(report))
    return result,report

def audit(mesh):
    _,counts=np.unique(np.sort(mesh.edges,axis=1),axis=0,return_counts=True)
    return {'piezas':len(mesh.split(only_watertight=False)),'bordes_abiertos':int(sum(counts==1)),'aristas_non_manifold':int(sum(counts>2)),'cerrada':bool(mesh.is_watertight),'dimensiones_mm':np.round(mesh.extents,3).tolist(),'triangulos':len(mesh.faces)}

def preview(name='Elisa',size=None,shift=0,*,fill=100,base_helper_enabled=True):
    name,text,helpers,report=prepare(name,size,shift,fill=fill,base_helper_enabled=base_helper_enabled)
    def path(g,color):
        if g.is_empty: return ''
        return f'<path fill="{color}" fill-rule="evenodd" d="'+''.join('M'+' L'.join(f'{x:.4f},{-y:.4f}' for x,y in ring.coords)+'Z' for p in components(g) for ring in [p.exterior,*p.interiors])+'"/>'
    base=load_base(); basepaths=[]
    for key,color in [('copo','#d8e7de'),('aro','#c5a46b')]:
        m=base[key]; v=m.vertices; fs=m.faces
        top=v[fs][:,:,2].min(axis=1)>2.9
        polygons=unary_union([Polygon(v[f,:2]) for f in fs[top] if Polygon(v[f,:2]).area>1e-9])
        basepaths.append(path(polygons,color))
    svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="-44 -44 90 90">'+''.join(basepaths)+path(helpers,'#e8a273')+path(text,'#314e51')+'</svg>'
    return svg,report

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('nombre',nargs='?',default='Elisa'); parser.add_argument('--salida',type=Path); args=parser.parse_args()
    m,r=generate(args.nombre); dest=args.salida or Path.cwd()/f'adorno-{args.nombre.lower()}.stl'; dest.parent.mkdir(parents=True,exist_ok=True); m.export(dest)
    # Reopen the exported file, not just the in-memory object.
    checked=trimesh.load_mesh(dest,process=True); r['stl_reabierto']=audit(checked)
    dest.with_suffix('.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)); print(dest); print(json.dumps(r,ensure_ascii=False,indent=2))
