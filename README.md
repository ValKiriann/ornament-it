# ornament-it

Personalizador de adornos imprimibles con nombres en Lobster y helpers automáticos.
POC 0.1.2 para uso en red local o VPN. Conserva el copo y aro del diseño de referencia;
une el nombre y sus apoyos al aro, manteniendo el copo independiente.

## Ejecutar el contenedor

```sh
docker run --rm --name ornament-it \
  -p 127.0.0.1:8768:8768 \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --cap-drop ALL --security-opt no-new-privileges \
  ghcr.io/valkiriann/ornament-it:0.1.2
```

Abrir http://127.0.0.1:8768. Para el homelab, el Compose está en
[ValKiriann/homelab](https://github.com/ValKiriann/homelab), carpeta `ornament-it`.
La imagen publicada se construye para `linux/amd64`.

La aplicación genera y comprueba el STL en memoria. No conserva nombres, STL ni
historial; no necesita un volumen de datos ni Fusion instalado. Las descargas
conservan letras de 3 mm y helpers de 1,2 mm de altura y 1 mm de ancho. La base
original tiene una pequeña desviación de Z de unos 0,0075 mm, que se conserva.

## Tamaño del nombre

Cada nombre empieza al 100 %: la mayor escala proporcional que cabe en el disco
interior de radio 24,4 mm, dejando aproximadamente 0,6 mm hasta el aro. Se tienen
en cuenta todos los contornos, puntos y tildes. El control permite reducirlo
hasta el 40 % o aumentarlo hasta el 106 % para encajar el nombre en el aro.
Al subir o bajar el nombre se recalcula el tamaño que cabe.
No se cambia el espaciado de la fuente ni la proporción entre ancho y alto.

La API usa `escala=40..106` (100 por defecto) y `posicion=-3..3` en milímetros.
El parámetro anterior `tamano` sigue aceptando una altura máxima en milímetros
(8..48), aunque la interfaz utiliza porcentaje para evitar tramos sin efecto.

## Helper de base opcional

El checkbox **Helper de base**, activado inicialmente, quita únicamente el puente
horizontal y sus enlaces de unión al nombre. Los apoyos del punto de la i y de
los acentos siempre se conservan y siguen unidos a su propia letra.

Al quitar la base, la vista comprueba si el nombre y esos apoyos forman una sola
pieza con el aro. Avisa si quedan partes sueltas o un contacto demasiado pequeño,
y bloquea la descarga hasta aumentar el tamaño, cambiar la posición o reactivar
la base. Elsa y Elisa al 104 % se unen sin base; Elisa conserva el apoyo de la i.
La API usa `helper=0` para quitar la base y `helper=1` (por defecto) para mantenerla.

La comprobación geométrica exige al menos 1 mm² de solape con el aro y que los
núcleos de las letras sigan unidos tras una erosión de 0,4 mm por lado (cuellos de
0,8 mm). Es un filtro geométrico conservador, no una garantía de resistencia: no
modela material, orientación de capas o ajustes de impresión. El STL exportado
se comprueba además en 3D y al reabrirlo: exactamente dos piezas cerradas.

## Desarrollo

Python 3.12 y las dependencias fijadas en `requirements.txt`:

```sh
python -m venv .venv
. .venv/bin/activate
pip install --only-binary=:all: -r requirements.txt
ORNAMENT_HOST=127.0.0.1 python app.py
python -m unittest discover -s tests -v
```

`ORNAMENT_HOST` (por defecto `0.0.0.0`) y `ORNAMENT_PORT` (`8768`) controlan la escucha.
`GET /healthz` devuelve salud, versión y commit. No hay autenticación integrada:
el despliegue está previsto para LAN/VPN. Una generación de geometría a la vez;
las solicitudes adicionales reciben una respuesta de ocupado.

## Publicar una versión

1. Cambiar `VERSION` en `app.py` y documentar los cambios.
2. Enviar el código a GitHub y comprobar CI.
3. Crear y subir una etiqueta como `v0.1.2`.
4. El workflow prueba los nombres, construye la imagen, prueba el contenedor con
   un STL reabierto y publica `:0.1.2` y `:sha-<commit-completo>` en GHCR.
5. Actualizar la referencia de imagen del Compose en `homelab` y redesplegar con Komodo.

Cada etiqueta de versión corresponde a una publicación. No reutilizar una etiqueta
para otro código. El digest publicado permite fijar exactamente la imagen a desplegar.
Para volver atrás, restaurar la referencia anterior del Compose y redesplegar.
La primera publicación de GHCR debe configurarse pública para permitir descarga anónima.

## Pruebas y límites

Se reabren los STL exportados para exigir dos piezas cerradas, cero bordes abiertos
y cero aristas non-manifold. Se comprueban apoyos de puntos y tildes y entradas inválidas.
Lobster se incluye con su licencia SIL Open Font License en `assets/OFL.txt`.

El prototipo conserva una sola fuente y un máximo de 18 caracteres. Los nombres largos
se reducen para caber; revisar el grosor de sus trazos antes de imprimir. Los helpers
son geometría permanente del adorno. Falta la prueba física. La comprobación anterior
del giro fue un muestreo cada 5 grados, no una demostración continua del recorrido.
No hay adaptación ni publicación en MakerWorld.
