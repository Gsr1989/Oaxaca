from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session, send_file
)
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo          # para hora local MX
from supabase import create_client, Client
import fitz                            # PyMuPDF
import os

app = Flask(__name__)
app.secret_key = 'clave_muy_segura_123456'

# Supabase
SUPABASE_URL = "https://xsagwqepoljfsogusubw.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhzYWd3cWVwb2xqZnNvZ3VzdWJ3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDM5NjM3NTUs"
    "ImV4cCI6MjA1OTUzOTc1NX0.NUixULn0m2o49At8j6X58UqbXre2O2_JStqzls_8Gws"
)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ENTIDAD FIJA
ENTIDAD = "oaxaca"

# Carpeta para PDFs
os.makedirs("documentos", exist_ok=True)

def generar_pdf(folio: str, numero_serie: str) -> str:
    plantilla = "oaxacaverga.pdf"
    if not os.path.isfile(plantilla):
        raise FileNotFoundError(f"No existe la plantilla PDF: {plantilla}")

    doc = fitz.open(plantilla)
    page = doc[0]

    ahora = datetime.now(tz=ZoneInfo("America/Mexico_City"))
    page.insert_text((136, 141), ahora.strftime("%d/%m/%Y"), fontsize=10)
    page.insert_text((136, 166), numero_serie,            fontsize=10)
    page.insert_text((146, 206), ahora.strftime("%H:%M:%S"), fontsize=10)

    ruta = os.path.join("documentos", f"{folio}.pdf")
    doc.save(ruta)
    doc.close()
    return ruta

@app.route('/')
def inicio():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        # Admin
        if username == 'Gsr89roja.' and password == 'serg890105':
            session['admin'] = True
            return redirect(url_for('admin'))
        # Usuario Supabase
        res = supabase.table("verificaciondigitalcdmx") \
                      .select("*") \
                      .eq("username", username) \
                      .eq("password", password) \
                      .execute()
        if res.data:
            session['user_id']  = res.data[0]['id']
            session['username'] = username
            return redirect(url_for('registro_usuario'))
        flash("Credenciales incorrectas", "error")
    return render_template("login.html")

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
        u    = request.form['username']
        p    = request.form['password']
        fols = int(request.form['folios'])
        exists = supabase.table("verificaciondigitalcdmx") \
                         .select("id") \
                         .eq("username", u) \
                         .execute()
        if exists.data:
            flash("El usuario ya existe.", "error")
        else:
            supabase.table("verificaciondigitalcdmx").insert({
                "username":       u,
                "password":       p,
                "folios_asignac": fols,
                "folios_usados":  0
            }).execute()
            flash("Usuario creado.", "success")
    return render_template("crear_usuario.html")

@app.route('/registro_usuario', methods=['GET', 'POST'])
def registro_usuario():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    uid = session['user_id']

    if request.method == 'POST':
        folio        = request.form['folio']
        marca        = request.form['marca']
        linea        = request.form['linea']
        anio         = request.form['anio']
        numero_serie = request.form['serie']
        numero_motor = request.form['motor']
        vigencia     = int(request.form['vigencia'])

        # duplicado?
        if supabase.table("folios_registrados").select("folio") \
                   .eq("folio", folio).execute().data:
            flash("Folio ya existe.", "error")
            return redirect(url_for('registro_usuario'))

        u = supabase.table("verificaciondigitalcdmx") \
                    .select("folios_asignac,folios_usados") \
                    .eq("id", uid).execute().data[0]
        if u['folios_asignac'] - u['folios_usados'] < 1:
            flash("Sin folios disponibles.", "error")
            return redirect(url_for('registro_usuario'))

        hoy = datetime.now(tz=ZoneInfo("America/Mexico_City"))
        supabase.table("folios_registrados").insert({
            "folio":             folio,
            "marca":             marca,
            "linea":             linea,
            "anio":              anio,
            "numero_serie":      numero_serie,
            "numero_motor":      numero_motor,
            "fecha_expedicion":  hoy.isoformat(),
            "fecha_vencimiento": (hoy + timedelta(days=vigencia)).isoformat(),
            "entidad":           ENTIDAD
        }).execute()
        supabase.table("verificaciondigitalcdmx").update({
            "folios_usados": u['folios_usados'] + 1
        }).eq("id", uid).execute()

        # renderiza página de éxito
        return render_template(
            "exitoso.html",
            folio=folio,
            serie=numero_serie,
            fecha_generacion=hoy.strftime("%d/%m/%Y %H:%M:%S")
        )

    info = supabase.table("verificaciondigitalcdmx") \
                   .select("folios_asignac,folios_usados") \
                   .eq("id", uid).execute().data[0]
    return render_template("registro_usuario.html", folios_info=info)

@app.route('/registro_admin', methods=['GET', 'POST'])
def registro_admin():
    if 'admin' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        folio        = request.form['folio']
        marca        = request.form['marca']
        linea        = request.form['linea']
        anio         = request.form['anio']
        numero_serie = request.form['serie']
        numero_motor = request.form['motor']
        vigencia     = int(request.form['vigencia'])

        # duplicado?
        if supabase.table("folios_registrados").select("folio") \
                   .eq("folio", folio).execute().data:
            flash("Folio ya existe.", "error")
            return render_template("registro_admin.html")

        hoy = datetime.now(tz=ZoneInfo("America/Mexico_City"))
        supabase.table("folios_registrados").insert({
            "folio":             folio,
            "marca":             marca,
            "linea":             linea,
            "anio":              anio,
            "numero_serie":      numero_serie,
            "numero_motor":      numero_motor,
            "fecha_expedicion":  hoy.isoformat(),
            "fecha_vencimiento": (hoy + timedelta(days=vigencia)).isoformat(),
            "entidad":           ENTIDAD
        }).execute()

        return render_template(
            "exitoso.html",
            folio=folio,
            serie=numero_serie,
            fecha_generacion=hoy.strftime("%d/%m/%Y %H:%M:%S")
        )
    return render_template("registro_admin.html")

@app.route('/descargar_pdf/<folio>')
def descargar_pdf(folio):
    path = os.path.join("documentos", f"{folio}.pdf")
    return send_file(path, as_attachment=True, download_name=f"{folio}.pdf")

@app.route('/consulta_folio', methods=['GET', 'POST'])
def consulta_folio():
    resultado = None
    if request.method == 'POST':
        folio = request.form['folio']
        row   = supabase.table("folios_registrados") \
                        .select("*").eq("folio", folio).execute().data
        if not row:
            resultado = {"estado":"NO ENCONTRADO","folio":folio}
        else:
            r    = row[0]
            fexp = datetime.fromisoformat(r['fecha_expedicion'])
            fven = datetime.fromisoformat(r['fecha_vencimiento'])
            estado = "VIGENTE" if datetime.now() <= fven else "VENCIDO"
            resultado = {
                "estado": estado,
                "folio": folio,
                "fecha_expedicion":  fexp.strftime("%d/%m/%Y"),
                "fecha_vencimiento": fven.strftime("%d/%m/%Y"),
                "marca":    r['marca'],
                "linea":    r['linea'],
                "año":      r['anio'],
                "serie":    r['numero_serie'],
                "motor":    r['numero_motor'],
                "entidad":  r.get('entidad','')
            }
        return render_template("resultado_consulta.html", resultado=resultado)
    return render_template("consulta_folio.html")

@app.route('/admin_folios')
def admin_folios():
    if 'admin' not in session:
        return redirect(url_for('login'))
    folios = supabase.table("folios_registrados").select("*").execute().data or []
    hoy = datetime.now(tz=ZoneInfo("America/Mexico_City"))
    for f in folios:
        fv = datetime.fromisoformat(f['fecha_vencimiento'])
        f['estado'] = "VIGENTE" if hoy <= fv else "VENCIDO"
    return render_template("admin_folios.html", folios=folios)

@app.route('/editar_folio/<folio>', methods=['GET','POST'])
def editar_folio(folio):
    if 'admin' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        supabase.table("folios_registrados").update({
            "marca":            request.form['marca'],
            "linea":            request.form['linea'],
            "anio":             request.form['anio'],
            "numero_serie":     request.form['serie'],
            "numero_motor":     request.form['motor'],
            "fecha_expedicion": request.form['fecha_expedicion'],
            "fecha_vencimiento":request.form['fecha_vencimiento'],
            "entidad":          ENTIDAD
        }).eq("folio", folio).execute()
        flash("Folio actualizado.", "success")
        return redirect(url_for('admin_folios'))
    row = supabase.table("folios_registrados").select("*") \
                  .eq("folio", folio).execute().data
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

if __name__ == '__main__':
    app.run(debug=True)
