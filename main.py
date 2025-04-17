import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from datetime import datetime, timedelta
from supabase import create_client, Client
import fitz  # PyMuPDF

app = Flask(__name__)
app.secret_key = 'clave_muy_segura_123456'

SUPABASE_URL = "https://xsagwqepoljfsogusubw.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhzYWd3cWVwb2xqZnNvZ3VzdWJ3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDM5NjM3NTUsImV4cCI6MjA1OTUzOTc1NX0.NUixULn0m2o49At8j6X58UqbXre2O2_JStqzls_8Gws"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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
        resp = supabase.table("verificaciondigitalcdmx") \
                      .select("*") \
                      .eq("username", username) \
                      .eq("password", password) \
                      .execute()
        usuarios = resp.data
        if usuarios:
            session['user_id'] = usuarios[0]['id']
            session['username'] = usuarios[0]['username']
            return redirect(url_for('registro_usuario'))
        flash('Credenciales incorrectas', 'error')
    return render_template('login.html')

# ------------------------------------
# Función corregida para generar PDFs
# ------------------------------------
def generar_pdf(folio, marca, linea, anio, numero_serie, numero_motor, vigencia):
    # Abre plantilla
    doc = fitz.open("oaxacaverga.pdf")
    page = doc[0]

    # Coordenadas
    x_hora, y_hora   = 146, 206
    x_serie, y_serie = 136, 166
    x_fecha, y_fecha = x_serie, y_serie - 25

    hora_actual = datetime.now().strftime("%H:%M:%S")
    fecha_exped = datetime.now().strftime("%d/%m/%Y")

    # Inserta datos
    page.insert_text((x_fecha, y_fecha),    fecha_exped,   fontsize=10)
    page.insert_text((x_serie, y_serie),    numero_serie,  fontsize=10)
    page.insert_text((x_hora,  y_hora),     hora_actual,   fontsize=10)

    # Guarda en carpeta local "documentos/"
    carpeta = "documentos"
    if not os.path.isdir(carpeta):
        os.makedirs(carpeta)
    output_path = os.path.join(carpeta, f"{folio}.pdf")

    doc.save(output_path)
    doc.close()
    return output_path

# -------------------------------
# Ruta para usuarios registrados
# -------------------------------
@app.route('/registro_usuario', methods=['GET', 'POST'])
def registro_usuario():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']

    if request.method == 'POST':
        # Lee formulario
        folio        = request.form['folio']
        marca        = request.form['marca']
        linea        = request.form['linea']
        anio         = request.form['anio']
        serie        = request.form['serie']
        motor        = request.form['motor']
        vigencia     = int(request.form['vigencia'])

        # Valida duplicado
        if supabase.table("folios_registrados").select("*").eq("folio", folio).execute().data:
            flash('Error: el folio ya existe.', 'error')
            return redirect(url_for('registro_usuario'))

        # Verifica folios disponibles
        u = supabase.table("verificaciondigitalcdmx") \
                    .select("folios_asignac, folios_usados") \
                    .eq("id", user_id).execute().data[0]
        if u['folios_asignac'] - u['folios_usados'] <= 0:
            flash("No tienes folios disponibles.", 'error')
            return redirect(url_for('registro_usuario'))

        # Inserta registro y actualiza contador
        fecha_exp = datetime.now()
        fecha_ven = fecha_exp + timedelta(days=vigencia)
        supabase.table("folios_registrados").insert({
            "folio": folio,
            "marca": marca,
            "linea": linea,
            "anio": anio,
            "numero_serie": serie,
            "numero_motor": motor,
            "fecha_expedicion": fecha_exp.isoformat(),
            "fecha_vencimiento": fecha_ven.isoformat()
        }).execute()
        supabase.table("verificaciondigitalcdmx") \
                .update({"folios_usados": u["folios_usados"] + 1}) \
                .eq("id", user_id).execute()

        # Genera y envía PDF
        pdf_path = generar_pdf(folio, marca, linea, anio, serie, motor, vigencia)
        if not os.path.exists(pdf_path):
            flash("Error al generar el PDF.", "error")
            return redirect(url_for('registro_usuario'))

        return send_file(
            pdf_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{folio}.pdf"
        )

    # GET → muestra formulario
    info = supabase.table("verificaciondigitalcdmx") \
                   .select("folios_asignac, folios_usados") \
                   .eq("id", user_id).execute().data[0]
    return render_template("registro_usuario.html", folios_info=info)

# ----------------------------
# Ruta para registrar admin
# ----------------------------
@app.route('/registro_admin', methods=['GET', 'POST'])
def registro_admin():
    if 'admin' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Lee formulario
        folio    = request.form['folio']
        marca    = request.form['marca']
        linea    = request.form['linea']
        anio     = request.form['anio']
        serie    = request.form['serie']
        motor    = request.form['motor']
        vigencia = int(request.form['vigencia'])

        # Valida duplicado
        if supabase.table("folios_registrados").select("*").eq("folio", folio).execute().data:
            flash('Error: el folio ya existe.', 'error')
            return render_template('registro_admin.html')

        # Inserta registro
        fecha_exp = datetime.now()
        fecha_ven = fecha_exp + timedelta(days=vigencia)
        supabase.table("folios_registrados").insert({
            "folio": folio,
            "marca": marca,
            "linea": linea,
            "anio": anio,
            "numero_serie": serie,
            "numero_motor": motor,
            "fecha_expedicion": fecha_exp.isoformat(),
            "fecha_vencimiento": fecha_ven.isoformat()
        }).execute()

        # Genera y envía PDF
        pdf_path = generar_pdf(folio, marca, linea, anio, serie, motor, vigencia)
        if not os.path.exists(pdf_path):
            flash("Error al generar el PDF.", "error")
            return render_template('registro_admin.html')

        return send_file(
            pdf_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{folio}.pdf"
        )

    # GET → muestra formulario admin
    return render_template('registro_admin.html')

# ---------------------------
# Resto de tus rutas abajo…
# ---------------------------

# … /consulta_folio, /admin, /crear_usuario, /admin_folios, /editar_folio, /eliminar_folio, /logout …

if __name__ == '__main__':
    app.run(debug=True)
