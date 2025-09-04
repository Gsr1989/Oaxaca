from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from supabase import create_client, Client
import fitz
import os

app = Flask(__name__)
app.secret_key = 'clave_muy_segura_123456'

SUPABASE_URL = "https://xsagwqepoljfsogusubw.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhzYWd3cWVwb2xqZnNvZ3VzdWJ3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDM5NjM3NTUs"
    "ImV4cCI6MjA1OTUzOTc1NX0.NUixULn0m2o49At8j6X58UqbXre2O2_JStqzls_8Gws"
)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

ENTIDAD = "oaxaca"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, "documentos")
os.makedirs(DOCS_DIR, exist_ok=True)

def generar_pdf(folio: str, numero_serie: str, fecha_expedicion: datetime) -> str:
    plantilla = os.path.join(BASE_DIR, "oaxacaverga.pdf")
    if not os.path.isfile(plantilla):
        raise FileNotFoundError(f"No existe la plantilla PDF: {plantilla}")
    doc = fitz.open(plantilla)
    page = doc[0]
    page.insert_text((136, 141), fecha_expedicion.strftime("%d/%m/%Y"), fontsize=10)
    page.insert_text((136, 166), numero_serie, fontsize=10)
    page.insert_text((146, 206), fecha_expedicion.strftime("%H:%M:%S"), fontsize=10)
    salida = os.path.join(DOCS_DIR, f"{folio}.pdf")
    doc.save(salida)
    doc.close()
    return salida

@app.route('/')
def inicio():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'Serg890105tm3' and password == 'Serg890105tm3':
            session['admin'] = True
            return redirect(url_for('admin'))
        res = supabase.table("verificaciondigitalcdmx").select("*") \
                      .eq("username", username).eq("password", password).execute()
        if res.data:
            session['user_id'] = res.data[0]['id']
            session['username'] = username
            return redirect(url_for('registro_usuario'))
        
        return render_template('bloqueado.html')
    return render_template('login.html')

@app.route('/admin')
def admin():
    if 'admin' not in session:
        return redirect(url_for('login'))
    return render_template("panel.html")

@app.route('/crear_usuario', methods=['GET', 'POST'])
def crear_usuario():
    if 'admin' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        u = request.form['username']
        p = request.form['password']
        f = int(request.form['folios'])
        exists = supabase.table("verificaciondigitalcdmx").select("id") \
                         .eq("username", u).execute()
        if exists.data:
            flash("El usuario ya existe.", "error")
        else:
            supabase.table("verificaciondigitalcdmx").insert({
                "username": u,
                "password": p,
                "folios_asignac": f,
                "folios_usados": 0
            }).execute()
            flash("Usuario creado exitosamente.", "success")
    return render_template("crear_usuario.html")

@app.route('/registro_usuario', methods=['GET', 'POST'])
def registro_usuario():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    uid = session['user_id']
    if request.method == 'POST':
        folio = request.form['folio']
        marca = request.form['marca']
        linea = request.form['linea']
        anio = request.form['anio']
        serie = request.form['serie']
        motor = request.form['motor']
        vigencia = int(request.form['vigencia'])
        if supabase.table("folios_registrados").select("folio").eq("folio", folio).execute().data:
            flash("Folio ya existe.", "error")
            return redirect(url_for('registro_usuario'))
        udat = supabase.table("verificaciondigitalcdmx") \
                       .select("folios_asignac,folios_usados") \
                       .eq("id", uid).execute().data[0]
        if udat['folios_asignac'] - udat['folios_usados'] < 1:
            flash("Sin folios disponibles.", "error")
            return redirect(url_for('registro_usuario'))
        ahora = datetime.now(tz=ZoneInfo("America/Mexico_City"))
        supabase.table("folios_registrados").insert({
            "folio": folio,
            "marca": marca,
            "linea": linea,
            "anio": anio,
            "numero_serie": serie,
            "numero_motor": motor,
            "fecha_expedicion": ahora.isoformat(),
            "fecha_vencimiento": (ahora + timedelta(days=vigencia)).isoformat(),
            "entidad": ENTIDAD
        }).execute()
        supabase.table("verificaciondigitalcdmx").update({
            "folios_usados": udat['folios_usados'] + 1
        }).eq("id", uid).execute()
        pdf_path = generar_pdf(folio, serie, ahora)
        return render_template("exitoso.html", folio=folio, serie=serie,
                               fecha_generacion=ahora.strftime("%d/%m/%Y %H:%M:%S"))
    info = supabase.table("verificaciondigitalcdmx").select("folios_asignac,folios_usados") \
                   .eq("id", uid).execute().data[0]
    return render_template("registro_usuario.html", folios_info=info)

@app.route('/registro_admin', methods=['GET', 'POST'])
def registro_admin():
    if 'admin' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        folio = request.form['folio']
        marca = request.form['marca']
        linea = request.form['linea']
        anio = request.form['anio']
        serie = request.form['serie']
        motor = request.form['motor']
        vigencia = int(request.form['vigencia'])
        if supabase.table("folios_registrados").select("folio").eq("folio", folio).execute().data:
            flash("Folio ya existe.", "error")
            return redirect(url_for('registro_admin'))
        ahora = datetime.now(tz=ZoneInfo("America/Mexico_City"))
        supabase.table("folios_registrados").insert({
            "folio": folio,
            "marca": marca,
            "linea": linea,
            "anio": anio,
            "numero_serie": serie,
            "numero_motor": motor,
            "fecha_expedicion": ahora.isoformat(),
            "fecha_vencimiento": (ahora + timedelta(days=vigencia)).isoformat(),
            "entidad": ENTIDAD
        }).execute()
        pdf_path = generar_pdf(folio, serie, ahora)
        return render_template("exitoso.html", folio=folio, serie=serie,
                               fecha_generacion=ahora.strftime("%d/%m/%Y %H:%M:%S"))
    return render_template("registro_admin.html")

@app.route('/descargar_pdf/<folio>')
def descargar_pdf(folio):
    path = os.path.join(DOCS_DIR, f"{folio}.pdf")
    if not os.path.isfile(path):
        flash("PDF no encontrado.", "error")
        return redirect(url_for('admin'))
    return send_file(path, as_attachment=True)

@app.route('/consulta_folio', methods=['GET', 'POST'])
def consulta_folio():
    resultado = None
    if request.method == 'POST':
        folio = request.form['folio'].strip().upper()
        row = supabase.table("folios_registrados").select("*").eq("folio", folio).execute().data
        if not row:
            resultado = {
                "estado": "NO SE ENCUENTRA REGISTRADO",
                "folio": folio
            }
        else:
            r = row[0]
            fe = datetime.fromisoformat(r['fecha_expedicion'])
            fv = datetime.fromisoformat(r['fecha_vencimiento'])
            estado = "VIGENTE" if datetime.now() <= fv else "VENCIDO"
            resultado = {
                "estado": estado,
                "folio": folio,
                "fecha_expedicion": fe.strftime("%d/%m/%Y"),
                "fecha_vencimiento": fv.strftime("%d/%m/%Y"),
                "marca": r['marca'],
                "linea": r['linea'],
                "año": r['anio'],
                "numero_serie": r['numero_serie'],
                "numero_motor": r['numero_motor'],
                "entidad": r.get('entidad', '')
            }
        return render_template("resultado_consulta.html", resultado=resultado)
    return render_template("consulta_folio.html")

@app.route('/admin_folios')
def admin_folios():
    if 'admin' not in session:
        return redirect(url_for('login'))
    folios = supabase.table("folios_registrados").select("*").execute().data or []
    hoy = datetime.now()
    for f in folios:
        fv = datetime.fromisoformat(f['fecha_vencimiento'])
        f['estado'] = "VIGENTE" if hoy <= fv else "VENCIDO"
    return render_template("admin_folios.html", folios=folios)

@app.route('/editar_folio/<folio>', methods=['GET', 'POST'])
def editar_folio(folio):
    if 'admin' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        supabase.table("folios_registrados").update({
            "marca": request.form['marca'],
            "linea": request.form['linea'],
            "anio": request.form['anio'],
            "numero_serie": request.form['serie'],
            "numero_motor": request.form['motor'],
            "fecha_expedicion": request.form['fecha_expedicion'],
            "fecha_vencimiento": request.form['fecha_vencimiento'],
            "entidad": ENTIDAD
        }).eq("folio", folio).execute()
        flash("Folio actualizado.", "success")
        return redirect(url_for('admin_folios'))
    row = supabase.table("folios_registrados").select("*").eq("folio", folio).execute().data
    if not row:
        flash("Folio no encontrado.", "error")
        return redirect(url_for('admin_folios'))
    return render_template("editar_folio.html", folio=row[0])

@app.route('/eliminar_folio', methods=['POST'])
def eliminar_folio():
    if 'admin' not in session:
        return redirect(url_for('login'))
    folio = request.form['folio']
    supabase.table("folios_registrados").delete().eq("folio", folio).execute()
    flash("Folio eliminado.", "success")
    return redirect(url_for('admin_folios'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/consulta/<folio>')
def consulta_folio_directo(folio):
    """Ruta para QR dinámicos - muestra directamente el folio"""
    
    row = supabase.table("folios_registrados").select("*").eq("folio", folio).eq("entidad", ENTIDAD).execute().data
    
    if not row:
        return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Folio No Encontrado</title></head>
<body style="font-family:Arial;text-align:center;padding:50px;background:#f5f5f5">
<h1>Folio {folio} no encontrado</h1>
<p>El folio no está registrado en el sistema de Oaxaca.</p>
<a href="/consulta_folio" style="color:#007bff">Consultar otro folio</a>
</body></html>"""
    
    r = row[0]
    fe = datetime.fromisoformat(r['fecha_expedicion'])
    fv = datetime.fromisoformat(r['fecha_vencimiento'])
    estado = "VIGENTE" if datetime.now() <= fv else "VENCIDO"
    color = "#28a745" if estado == "VIGENTE" else "#dc3545"
    
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Folio {folio}</title>
<style>
body{{font-family:Arial,sans-serif;background:#f5f5f5;margin:0;padding:20px}}
.header{{text-align:center;background:white;padding:20px;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,0.1);margin-bottom:20px}}
.estado{{background:{color};color:white;padding:15px;text-align:center;font-size:1.2em;font-weight:bold;border-radius:10px;margin:20px 0}}
.info-box{{background:white;padding:20px;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,0.1)}}
.info{{margin:15px 0;padding:10px 0;border-bottom:1px solid #eee}}
.label{{font-weight:bold;color:#333;font-size:0.9em}}
.value{{color:#666;margin-top:5px}}
.footer{{text-align:center;margin-top:20px;color:#666;font-size:0.85em}}
</style></head><body>
<div class="header">
<h1>Secretaría de Movilidad</h1>
<h2>Gobierno del Estado de Oaxaca</h2>
</div>
<div class="estado">FOLIO {folio} : {estado}</div>
<div class="info-box">
<div class="info"><div class="label">FECHA DE EXPEDICIÓN</div><div class="value">{fe.strftime('%d/%m/%Y')}</div></div>
<div class="info"><div class="label">FECHA DE VENCIMIENTO</div><div class="value">{fv.strftime('%d/%m/%Y')}</div></div>
<div class="info"><div class="label">MARCA</div><div class="value">{r['marca']}</div></div>
<div class="info"><div class="label">LÍNEA</div><div class="value">{r['linea']}</div></div>
<div class="info"><div class="label">AÑO</div><div class="value">{r['anio']}</div></div>
<div class="info"><div class="label">NÚMERO DE SERIE</div><div class="value">{r['numero_serie']}</div></div>
<div class="info"><div class="label">NÚMERO DE MOTOR</div><div class="value">{r['numero_motor']}</div></div>
</div>
<div class="footer">DOCUMENTO DIGITAL VÁLIDO EN TODO MÉXICO</div>
</body></html>"""

if __name__ == '__main__':
    app.run(debug=True)
