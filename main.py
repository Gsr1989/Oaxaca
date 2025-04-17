from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from datetime import datetime, timedelta
from supabase import create_client, Client
import fitz
import os
import io
import qrcode

app = Flask(__name__)
app.secret_key = 'clave_muy_segura_123456'

SUPABASE_URL = "https://xsagwqepoljfsogusubw.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhzYWd3cWVwb2xqZnNvZ3VzdWJ3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDM5NjM3NTUsImV4cCI6MjA1OTUzOTc1NX0.NUixULn0m2o49At8j6X58UqbXre2O2_JStqzls_8Gws"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ------------------------------------------------------------------
#  NUEVA FUNCIÓN: genera el PDF con plantilla 'oaxacaverga.pdf'
# ------------------------------------------------------------------
def generar_pdf(folio, numero_serie, fecha_expedicion):
    """
    Crea documentos/<folio>.pdf usando la plantilla oaxacaverga.pdf
    e inserta serie, fecha y hora en las coordenadas indicadas.
    """
    plantilla = "oaxacaverga.pdf"           # Nombre exacto de la plantilla
    doc = fitz.open(plantilla)
    page = doc[0]

    # Coordenadas validadas
    x_fecha, y_fecha = 136, 141
    x_serie, y_serie = 136, 166
    x_hora,  y_hora  = 146, 206

    # Inserciones
    page.insert_text((x_serie, y_serie), numero_serie,
                     fontsize=10, fontname="helv")
    page.insert_text((x_fecha, y_fecha), fecha_expedicion.strftime("%d/%m/%Y"),
                     fontsize=10, fontname="helv")
    page.insert_text((x_hora, y_hora),  fecha_expedicion.strftime("%H:%M:%S"),
                     fontsize=10, fontname="helv")

    os.makedirs("documentos", exist_ok=True)
    salida = f"documentos/{folio}.pdf"
    doc.save(salida)
    doc.close()
    return salida
# ------------------------------------------------------------------


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
        response = supabase.table("verificaciondigitalcdmx").select("*") \
                           .eq("username", username).eq("password", password).execute()
        usuarios = response.data
        if usuarios:
            session['user_id'] = usuarios[0]['id']
            session['username'] = usuarios[0]['username']
            return redirect(url_for('registro_usuario'))
        else:
            flash('Credenciales incorrectas', 'error')
    return render_template('login.html')

@app.route('/admin')
def admin():
    if 'admin' not in session:
        return redirect(url_for('login'))
    return render_template('panel.html')

@app.route('/crear_usuario', methods=['GET', 'POST'])
def crear_usuario():
    if 'admin' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        folios   = int(request.form['folios'])
        existe = supabase.table("verificaciondigitalcdmx") \
                         .select("id").eq("username", username).execute()
        if existe.data:
            flash('Error: el nombre de usuario ya existe.', 'error')
            return render_template('crear_usuario.html')
        supabase.table("verificaciondigitalcdmx").insert({
            "username": username,
            "password": password,
            "folios_asignac": folios,
            "folios_usados": 0
        }).execute()
        flash('Usuario creado exitosamente.', 'success')
    return render_template('crear_usuario.html')

@app.route('/registro_usuario', methods=['GET', 'POST'])
def registro_usuario():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']

    if request.method == 'POST':
        folio        = request.form['folio']
        marca        = request.form['marca']
        linea        = request.form['linea']
        anio         = request.form['anio']
        numero_serie = request.form['serie']
        numero_motor = request.form['motor']
        vigencia     = int(request.form['vigencia'])

        # — Validaciones —
        if supabase.table("folios_registrados").select("*").eq("folio", folio).execute().data:
            flash('Error: el folio ya existe.', 'error')
            return redirect(url_for('registro_usuario'))

        usuario_data = supabase.table("verificaciondigitalcdmx") \
                               .select("folios_asignac, folios_usados") \
                               .eq("id", user_id).execute()
        if not usuario_data.data:
            flash("No se pudo obtener la información del usuario.", "error")
            return redirect(url_for('registro_usuario'))

        info = usuario_data.data[0]
        if info['folios_asignac'] - info['folios_usados'] <= 0:
            flash("No tienes folios disponibles para registrar.", "error")
            return redirect(url_for('registro_usuario'))

        # — Guardado —
        fecha_exp  = datetime.now()
        fecha_ven  = fecha_exp + timedelta(days=vigencia)
        supabase.table("folios_registrados").insert({
            "folio": folio,
            "marca": marca,
            "linea": linea,
            "anio": anio,
            "numero_serie": numero_serie,
            "numero_motor": numero_motor,
            "fecha_expedicion": fecha_exp.isoformat(),
            "fecha_vencimiento": fecha_ven.isoformat()
        }).execute()
        supabase.table("verificaciondigitalcdmx").update({
            "folios_usados": info["folios_usados"] + 1
        }).eq("id", user_id).execute()

        # — Generar PDF —
        generar_pdf(folio, numero_serie, fecha_exp)

        flash("Folio registrado correctamente y PDF generado.", "success")
        return render_template("exitoso.html",
                               folio=folio,
                               serie=numero_serie,
                               fecha_generacion=fecha_exp.strftime('%d/%m/%Y'))

    resp = supabase.table("verificaciondigitalcdmx") \
                   .select("folios_asignac, folios_usados") \
                   .eq("id", session['user_id']).execute()
    return render_template("registro_usuario.html",
                           folios_info=resp.data[0] if resp.data else {})

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

        if supabase.table("folios_registrados").select("*").eq("folio", folio).execute().data:
            flash('Error: el folio ya existe.', 'error')
            return render_template('registro_admin.html')

        fecha_exp = datetime.now()
        fecha_ven = fecha_exp + timedelta(days=vigencia)
        supabase.table("folios_registrados").insert({
            "folio": folio,
            "marca": marca,
            "linea": linea,
            "anio": anio,
            "numero_serie": numero_serie,
            "numero_motor": numero_motor,
            "fecha_expedicion": fecha_exp.isoformat(),
            "fecha_vencimiento": fecha_ven.isoformat()
        }).execute()

        generar_pdf(folio, numero_serie, fecha_exp)

        return render_template("exitoso.html",
                               folio=folio,
                               serie=numero_serie,
                               fecha_generacion=fecha_exp.strftime('%d/%m/%Y'))
    return render_template('registro_admin.html')

# ------------------------------------------------------------------
#  (El resto del archivo NO se tocó)
# ------------------------------------------------------------------
@app.route('/consulta_folio', methods=['GET', 'POST'])
def consulta_folio():
    resultado = None
    if request.method == 'POST':
        folio = request.form['folio']
        registros = supabase.table("folios_registrados") \
                            .select("*").eq("folio", folio).execute().data
        if not registros:
            resultado = {"estado": "NO SE ENCUENTRA REGISTRADO",
                         "color": "rojo", "folio": folio}
        else:
            r = registros[0]
            f_exp = datetime.fromisoformat(r['fecha_expedicion'])
            f_ven = datetime.fromisoformat(r['fecha_vencimiento'])
            estado = "VIGENTE" if datetime.now() <= f_ven else "VENCIDO"
            resultado = {
                "estado": estado,
                "color": "verde" if estado == "VIGENTE" else "cafe",
                "folio": folio,
                "fecha_expedicion": f_exp.strftime('%d/%m/%Y'),
                "fecha_vencimiento": f_ven.strftime('%d/%m/%Y'),
                "marca": r['marca'],
                "linea": r['linea'],
                "año": r['anio'],
                "numero_serie": r['numero_serie'],
                "numero_motor": r['numero_motor']
            }
        return render_template("resultado_consulta.html", resultado=resultado)
    return render_template("consulta_folio.html")

@app.route('/descargar_pdf/<folio>')
def descargar_pdf(folio):
    return send_file(f"documentos/{folio}.pdf", as_attachment=True)

# … resto de rutas admin_folios / editar_folio / eliminar_folio / logout
# (SIN CAMBIOS)

if __name__ == '__main__':
    app.run(debug=True)
