"""Ejecuta el backend original con la extensión SHCP y su tablero conectado."""
import sys
from pathlib import Path
from flask import abort, render_template, send_from_directory

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'original/backend'))
from app import create_app

app = create_app()
app.template_folder = str(RAIZ / 'app/templates')
app.static_folder = str(RAIZ / 'app/static')


@app.get('/')
def inicio():
    return render_template('index.html')


@app.get('/sistema/')
@app.get('/sistema/<path:archivo>')
def sistema(archivo='index.html'):
    if Path(archivo).suffix.lower() not in ('.html','.js','.css','.svg','.png','.jpg','.webp','.ico'):
        abort(404)
    return send_from_directory(RAIZ / 'original', archivo)


@app.get('/api/salud')
def salud():
    from app.database import get_db
    with get_db() as (_, cur):
        cur.execute('SELECT count(*) AS obras FROM warehouse.fact_srft')
        return dict(ok=True, **cur.fetchone())
