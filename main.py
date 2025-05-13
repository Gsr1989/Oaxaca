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

# ENTIDAD FIJA PARA OAXACA
ENTIDAD = "oaxaca"

os.makedirs("documentos", exist_ok=True)

def generar_pdf(folio: str, numero_serie: str) -> str:
    plantilla = "oaxacaverga.pdf"
    doc = fitz.open(plantilla)
    page = doc[0]

    ahora = datetime.now(tz=ZoneInfo("America/Mexico_City"))
    page.insert_text((136, 141), ahora.strftime("%d/%m/%Y"), fontsize=10)
    page.insert_text((136, 166), numero_serie, fontsize=10)
    page.insert_text((146, 206), ahora.strftime("%H:%M:%S"), fontsize=10)

    ruta = f"documentos/{folio}.pdf"
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

        if username == 'Gsr89roja.' and password == 'serg890105':
            session['admin'] = True
            return redirect(url_for('admin'))

        res = supabase.table("verificaciondigitalcdmx") \
                      .select("*") \
                      .eq("username", username) \
                      .eq("password", password).execute()
        if res.data:
            session['user_id'] = res.data[0]['id']
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
        user   = request.form['username']
        pwd    = request.form['password']
        folios = int(request.form['folios'])

        existe = supabase.table("verificaciondigitalcdmx") \
                         .select("id").eq("username", user).execute().data
        if existe:
            flash("El usuario ya existe.", "error")
        else:
            supabase.table("verificaciondigitalcdmx").insert({
                "username":       user,
                "password":       pwd,
                "folios_asignac": folios,
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
        numero_serie = request.form['serie']
        vigencia     = int(request.form['vigencia'])

        if supabase.table("folios_registrados").select("folio") \
                   .eq("folio", folio).execute().data:
            flash("Folio ya existe.", "error")
            return redirect(url_for('registro_usuario'))

        u = supabase.table("verificaciondigitalcdmx") \
                    .select("folios_asignac, folios_usados") \
                    .eq("id", uid).execute().data[0]
        if u['folios_asignac'] - u['folios_usados'] < 1:
            flash("Sin folios disponibles.", "error")
            return redirect(url_for('registro_usuario'))

        hoy = datetime.now(tz=ZoneInfo("America/Mexico_City"))
        supabase.table("folios_registrados").insert({
            "folio":             folio,
            "marca":             request.form['marca'],
            "linea":             request.form['linea'],
            "anio":              request.form['anio'],
            "numero_serie":      numero_serie,
            "numero_motor":      request.form['motor'],
            "fecha_expedicion":  hoy.isoformat(),
            "fecha_vencimiento": (hoy + timedelta(days=vigencia)).isoformat(),
            "entidad":           ENTIDAD
        }).execute()

        supabase.table("verificaciondigitalcdmx").update({
            "folios_usados": u['folios_usados'] + 1
        }).eq("id", uid).execute()

        return send_file(generar_pdf(folio, numero_serie), as_attachment=True)

    info = supabase.table("verificaciondigitalcdmx") \
                   .select("folios_asignac, folios_usados") \
                   .eq("id", uid).execute().data[0]
    return render_template("registro_usuario.html", folios_info=info)

@app.route('/registro_admin', methods=['GET', 'POST'])
def registro_admin():
    if 'admin' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        folio        = request.form['folio']
        numero_serie = request.form['serie']
        vigencia     = int(request.form['vigencia'])

        if supabase.table("folios_registrados").select("folio") \
                   .eq("folio", folio).execute().data:
            flash("Folio ya existe.", "error")
            return render_template("registro_admin.html")

        hoy = datetime.now(tz=ZoneInfo("America/Mexico_City"))
        supabase.table("folios_registrados").insert({
            "folio":             folio,
            "marca":             request.form['marca'],
            "linea":             request.form['linea'],
            "anio":              request.form['anio'],
            "numero_serie":      numero_serie,
            "numero_motor":      request.form['motor'],
            "fecha_expedicion":  hoy.isoformat(),
            "fecha_vencimiento": (hoy + timedelta(days=vigencia)).isoformat(),
            "entidad":           ENTIDAD
        }).execute()

        return send_file(generar_pdf(folio, numero_serie), as_attachment=True)

    return render_template("registro_admin.html")

@app.route('/descargar_pdf/<folio>')
def descargar_pdf(folio):
    return send_file(f"documentos/{folio}.pdf", as_attachment=True)

@app.route('/consulta_folio', methods=['GET', 'POST'])
def consulta_folio():
    resultado = None
    if request.method == 'POST':
        folio = request.form['folio']
        row   = supabase.table("folios_registrados") \
                        .select("*").eq("folio", folio).execute().data
        if not row:
            resultado = {"estado": "NO SE ENCUENTRA REGISTRADO",
                         "color": "rojo", "folio": folio}
        else:
            r     = row[0]
            f_exp = datetime.fromisoformat(r['fecha_expedicion'])
            f_ven = datetime.fromisoformat(r['fecha_vencimiento']).replace(tzinfo=ZoneInfo("America/Mexico_City"))
            ahora = datetime.now(tz=ZoneInfo("America/Mexico_City"))
            estado = "VIGENTE" if ahora <= f_ven else "VENCIDO"
            resultado = {
                "estado": estado,
                "color":  "verde" if estado == "VIGENTE" else "cafe",
                "folio":  folio,
                "fecha_expedicion":  f_exp.strftime("%d/%m/%Y"),
                "fecha_vencimiento": f_ven.strftime("%d/%m/%Y"),
                "marca":    r['marca'],
                "linea":    r['linea'],
                "año":      r['anio'],
                "numero_serie": r['numero_serie'],
                "numero_motor": r['numero_motor'],
                "entidad":      r.get('entidad', '')
            }
        return render_template("resultado_consulta.html", resultado=resultado)
    return render_template("consulta_folio.html")

@app.route('/admin_folios')
def admin_folios():
    if 'admin' not in session:
        return redirect(url_for('login'))

    filtro        = request.args.get('filtro', '').strip()
    criterio      = request.args.get('criterio', 'folio')
    estado_filtro = request.args.get('estado', 'todos')
    ordenar       = request.args.get('ordenar', 'desc')
    fecha_inicio  = request.args.get('fecha_inicio', '')
    fecha_fin     = request.args.get('fecha_fin', '')

    q = supabase.table("folios_registrados").select("*")
    if filtro:
        campo = "folio" if criterio == "folio" else "numero_serie"
        q = q.ilike(campo, f"%{filtro}%")

    folios = q.execute().data or []
    hoy = datetime.now(tz=ZoneInfo("America/Mexico_City"))
    filtrados = []
    for f in folios:
        f_exp = datetime.fromisoformat(f['fecha_expedicion'])
        f_ven = datetime.fromisoformat(f['fecha_vencimiento'])
        f['estado'] = "VIGENTE" if hoy <= f_ven else "VENCIDO"

        if estado_filtro != "todos" and f['estado'].lower() != estado_filtro:
            continue
        filtrados.append(f)

    filtrados.sort(key=lambda x: x['fecha_expedicion'],
                   reverse=(ordenar == "desc"))

    return render_template("admin_folios.html",
                           folios=filtrados,
                           filtro=filtro,
                           criterio=criterio,
                           estado=estado_filtro,
                           ordenar=ordenar,
                           fecha_inicio=fecha_inicio,
                           fecha_fin=fecha_fin)

@app.route('/editar_folio/<folio>', methods=['GET', 'POST'])
def editar_folio(folio):
    if 'admin' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        supabase.table("folios_registrados").update({
            "marca":            request.form['marca'],
            "linea":            request.form['linea'],
            "anio":             request.form['anio'],
            "numero_serie":     request.form['numero_serie'],
            "numero_motor":     request.form['numero_motor'],
            "fecha_expedicion": request.form['fecha_expedicion'],
            "fecha_vencimiento":request.form['fecha_vencimiento'],
            "entidad":          ENTIDAD
        }).eq("folio", folio).execute()
        flash("Folio actualizado.", "success")
        return redirect(url_for('admin_folios'))

    row = supabase.table("folios_registrados").select("*") \
                  .eq("folio", folio).execute().data
    if row:
        return render_template("editar_folio.html", folio=row[0])

    flash("Folio no encontrado.", "error")
    return redirect(url_for('admin_folios'))

@app.route('/eliminar_folio', methods=['POST'])
def eliminar_folio():
    if 'admin' not in session:
        return redirect(url_for('login'))

    folio = request.form['folio']
    supabase.table("folios_registrados").delete().eq("folio", folio).execute()
    flash("Folio eliminado.", "success")
    return redirect(url_for('admin_folios'))

@app.route('/descargar_pdf/<folio>')
def descargar_pdf(folio):
    return send_file(f"documentos/{folio}.pdf", as_attachment=True)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
