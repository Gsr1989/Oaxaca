from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session, send_file
)
from datetime import datetime, timedelta
from supabase import create_client, Client
import fitz  # PyMuPDF
import os
import io
import qrcode

app = Flask(__name__)
app.secret_key = 'clave_muy_segura_123456'

SUPABASE_URL = "https://xsagwqepoljfsogusubw.supabase.co"
SUPABASE_KEY = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhzYWd3cWVwb2xqZnNvZ3VzdWJ3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDM5NjM3NTUs"
                "ImV4cCI6MjA1OTUzOTc1NX0.NUixULn0m2o49At8j6X58UqbXre2O2_JStqzls_8Gws")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ----------------------------------------------------------------------
# PDF – usa la plantilla oaxacaverga.pdf y coordenadas solicitadas
# ----------------------------------------------------------------------
os.makedirs("documentos", exist_ok=True)


def generar_pdf(folio: str, numero_serie: str) -> str:
    plantilla = "oaxacaverga.pdf"          # NUEVA PLANTILLA
    doc = fitz.open(plantilla)
    page = doc[0]

    ahora = datetime.now()
    fecha_txt = ahora.strftime("%d/%m/%Y")
    hora_txt = ahora.strftime("%H:%M:%S")

    # Coordenadas proporcionadas
    page.insert_text((136, 141), fecha_txt,        fontsize=10)
    page.insert_text((136, 166), numero_serie,     fontsize=10)
    page.insert_text((146, 206), hora_txt,         fontsize=10)

    ruta = f"documentos/{folio}.pdf"
    doc.save(ruta)
    doc.close()
    return ruta


# ----------------------------------------------------------------------
#                               RUTAS
# ----------------------------------------------------------------------
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

        resp = supabase.table("verificaciondigitalcdmx").select("*") \
                       .eq("username", username).eq("password", password).execute()
        if resp.data:
            session['user_id'] = resp.data[0]['id']
            session['username'] = username
            return redirect(url_for('registro_usuario'))

        flash("Credenciales incorrectas", "error")
    return render_template("login.html")


@app.route('/admin')
def admin():
    if 'admin' not in session:
        return redirect(url_for('login'))
    return render_template("panel.html")


# ------------------------- CREAR USUARIO (ADMIN) ------------------------
@app.route('/crear_usuario', methods=['GET', 'POST'])
def crear_usuario():
    if 'admin' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        user = request.form['username']
        pwd = request.form['password']
        folios = int(request.form['folios'])

        if supabase.table("verificaciondigitalcdmx").select("id").eq("username", user).execute().data:
            flash("El usuario ya existe.", "error")
        else:
            supabase.table("verificaciondigitalcdmx").insert({
                "username": user,
                "password": pwd,
                "folios_asignac": folios,
                "folios_usados": 0
            }).execute()
            flash("Usuario creado.", "success")

    return render_template("crear_usuario.html")


# ------------------------- REGISTRO – USUARIO ---------------------------
@app.route('/registro_usuario', methods=['GET', 'POST'])
def registro_usuario():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    uid = session['user_id']

    if request.method == 'POST':
        folio = request.form['folio']
        numero_serie = request.form['serie']
        vigencia = int(request.form['vigencia'])

        # Folio duplicado
        if supabase.table("folios_registrados").select("id").eq("folio", folio).execute().data:
            flash("Folio ya existe.", "error")
            return redirect(url_for('registro_usuario'))

        # Folios disponibles
        u = supabase.table("verificaciondigitalcdmx").select("folios_asignac, folios_usados") \
                    .eq("id", uid).execute().data[0]
        if u['folios_asignac'] - u['folios_usados'] < 1:
            flash("Sin folios disponibles.", "error")
            return redirect(url_for('registro_usuario'))

        hoy = datetime.now()
        supabase.table("folios_registrados").insert({
            "folio": folio,
            "marca": request.form['marca'],
            "linea": request.form['linea'],
            "anio": request.form['anio'],
            "numero_serie": numero_serie,
            "numero_motor": request.form['motor'],
            "fecha_expedicion": hoy.isoformat(),
            "fecha_vencimiento": (hoy + timedelta(days=vigencia)).isoformat()
        }).execute()
        supabase.table("verificaciondigitalcdmx").update({
            "folios_usados": u['folios_usados'] + 1
        }).eq("id", uid).execute()

        pdf_path = generar_pdf(folio, numero_serie)
        return send_file(pdf_path, as_attachment=True)

    info = supabase.table("verificaciondigitalcdmx").select("folios_asignac, folios_usados") \
                   .eq("id", uid).execute().data[0]
    return render_template("registro_usuario.html", folios_info=info)


# ------------------------- REGISTRO – ADMIN -----------------------------
@app.route('/registro_admin', methods=['GET', 'POST'])
def registro_admin():
    if 'admin' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        folio = request.form['folio']
        numero_serie = request.form['serie']
        vigencia = int(request.form['vigencia'])

        if supabase.table("folios_registrados").select("id").eq("folio", folio).execute().data:
            flash("Folio ya existe.", "error")
            return render_template("registro_admin.html")

        hoy = datetime.now()
        supabase.table("folios_registrados").insert({
            "folio": folio,
            "marca": request.form['marca'],
            "linea": request.form['linea'],
            "anio": request.form['anio'],
            "numero_serie": numero_serie,
            "numero_motor": request.form['motor'],
            "fecha_expedicion": hoy.isoformat(),
            "fecha_vencimiento": (hoy + timedelta(days=vigencia)).isoformat()
        }).execute()

        pdf_path = generar_pdf(folio, numero_serie)
        return send_file(pdf_path, as_attachment=True)

    return render_template("registro_admin.html")


# ------------------------- DESCARGAR PDF -------------------------------
@app.route('/descargar_pdf/<folio>')
def descargar_pdf(folio):
    return send_file(f"documentos/{folio}.pdf", as_attachment=True)


# ------------------------- CONSULTA FOLIO ------------------------------
@app.route('/consulta_folio', methods=['GET', 'POST'])
def consulta_folio():
    resultado = None
    if request.method == 'POST':
        folio = request.form['folio']
        resp = supabase.table("folios_registrados").select("*").eq("folio", folio).execute()
        rows = resp.data
        if not rows:
            resultado = {"estado": "NO SE ENCUENTRA REGISTRADO",
                         "color": "rojo",
                         "folio": folio}
        else:
            r = rows[0]
            f_exp = datetime.fromisoformat(r['fecha_expedicion'])
            f_ven = datetime.fromisoformat(r['fecha_vencimiento'])
            estado = "VIGENTE" if datetime.now() <= f_ven else "VENCIDO"
            resultado = {
                "estado": estado,
                "color": "verde" if estado == "VIGENTE" else "cafe",
                "folio": folio,
                "fecha_expedicion": f_exp.strftime("%d/%m/%Y"),
                "fecha_vencimiento": f_ven.strftime("%d/%m/%Y"),
                "marca": r['marca'],
                "linea": r['linea'],
                "año": r['anio'],
                "numero_serie": r['numero_serie'],
                "numero_motor": r['numero_motor']
            }
        return render_template("resultado_consulta.html", resultado=resultado)
    return render_template("consulta_folio.html")


# ------------------------- (RESTO DE RUTAS SIN CAMBIOS) ----------------
# admin_folios, editar_folio, eliminar_folio…  (todo idéntico a tu versión)


if __name__ == '__main__':
    app.run(debug=True)
