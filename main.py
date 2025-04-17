from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from datetime import datetime, timedelta
from supabase import create_client, Client
import fitz  # PyMuPDF
import os
import io
import qrcode

app = Flask(__name__)
app.secret_key = 'clave_muy_segura_123456'

# Supabase credentials\SUPABASE_URL = "https://xsagwqepoljfsogusubw.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhzYWd3cWVwb2xqZnNvZ3VzdWJ3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDM5NjM3NTUsImV4cCI6MjA1OTUzOTc1NX0.NUixULn0m2o49At8j6X58UqbXre2O2_JStqzls_8Gws"
)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Ensure 'documentos' directory exists
eos.makedirs('documentos', exist_ok=True)

# ------------------------
# Helper: Generate PDF
# ------------------------
def generar_pdf(folio: str, numero_serie: str) -> str:
    """
    Opens the Oaxaca template, inserts date, series and time at fixed coordinates,
    saves to 'documentos/{folio}.pdf' and returns the path.
    """
    plantilla = "oaxacaverga.pdf"
    doc = fitz.open(plantilla)
    page = doc[0]

    # Coordinates for insertion
    x_fecha, y_fecha = 136, 141  # Date 25 pts above series
    x_serie, y_serie = 136, 166
    x_hora, y_hora   = 146, 206

    # Dynamic values
    fecha = datetime.now().strftime("%d/%m/%Y")
    hora  = datetime.now().strftime("%H:%M:%S")

    # Insert text
    page.insert_text((x_fecha, y_fecha), fecha,       fontsize=10)
    page.insert_text((x_serie, y_serie), numero_serie, fontsize=10)
    page.insert_text((x_hora, y_hora),   hora,         fontsize=10)

    # Save PDF
    output_path = os.path.join('documentos', f"{folio}.pdf")
    doc.save(output_path)
    doc.close()
    return output_path

# ------------------------
# Routes
# ------------------------

@app.route('/')
def inicio():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Hardcoded admin
        if username == 'Gsr89roja.' and password == 'serg890105':
            session['admin'] = True
            return redirect(url_for('admin'))

        # Supabase user verify
        resp = supabase.table("verificaciondigitalcdmx") \
                       .select("*") \
                       .eq("username", username) \
                       .eq("password", password) \
                       .execute()
        if resp.data:
            session['user_id']  = resp.data[0]['id']
            session['username'] = resp.data[0]['username']
            return redirect(url_for('registro_usuario'))
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
                         .select("id") \
                         .eq("username", username) \
                         .execute()
        if existe.data:
            flash('Error: el nombre de usuario ya existe.', 'error')
        else:
            supabase.table("verificaciondigitalcdmx").insert({
                "username":     username,
                "password":     password,
                "folios_asignac": folios,
                "folios_usados":  0
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

        # Check folio exists
        if supabase.table("folios_registrados").select("*").eq("folio", folio).execute().data:
            flash('Error: el folio ya existe.', 'error')
            return redirect(url_for('registro_usuario'))

        # Check available folios
        u = supabase.table("verificaciondigitalcdmx") \
                    .select("folios_asignac, folios_usados") \
                    .eq("id", user_id) \
                    .execute().data[0]
        if u['folios_asignac'] - u['folios_usados'] < 1:
            flash('No tienes folios disponibles.', 'error')
            return redirect(url_for('registro_usuario'))

        # Insert record
        hoy = datetime.now()
        supabase.table("folios_registrados").insert({
            "folio": folio,
            "marca": marca,
            "linea": linea,
            "anio":  anio,
            "numero_serie": numero_serie,
            "numero_motor": numero_motor,
            "fecha_expedicion": hoy.isoformat(),
            "fecha_vencimiento": (hoy + timedelta(days=vigencia)).isoformat()
        }).execute()
        supabase.table("verificaciondigitalcdmx").update({
            "folios_usados": u['folios_usados'] + 1
        }).eq("id", user_id).execute()

        # Generate PDF
        pdf_path = generar_pdf(folio, numero_serie)
        if not os.path.exists(pdf_path):
            flash('Error generando PDF.', 'error')
            return redirect(url_for('registro_usuario'))

        return send_file(
            pdf_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{folio}.pdf"
        )

    # GET
    info = supabase.table("verificaciondigitalcdmx") \
                   .select("folios_asignac, folios_usados") \
                   .eq("id", user_id).execute().data[0]
    return render_template('registro_usuario.html', folios_info=info)

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

        hoy = datetime.now()
        supabase.table("folios_registrados").insert({
            "folio": folio,
            "marca": marca,
            "linea": linea,
            "anio":  anio,
            "numero_serie": numero_serie,
            "numero_motor": numero_motor,
            "fecha_expedicion": hoy.isoformat(),
            "fecha_vencimiento": (hoy + timedelta(days=vigencia)).isoformat()
        }).execute()

        # Generate PDF
        pdf_path = generar_pdf(folio, numero_serie)
        return send_file(
            pdf_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{folio}.pdf"
        )

    return render_template('registro_admin.html')

@app.route('/consulta_folio', methods=['GET', 'POST'])
def consulta_folio():
    resultado = None
    if request.method == 'POST':
        folio = request.form['folio']
        data  = supabase.table("folios_registrados").select("*").eq("folio", folio).execute().data
        if not data:
            resultado = {"estado": "NO SE ENCUENTRA REGISTRADO", "color": "rojo", "folio": folio}
        else:
            r  = data[0]
            fe = datetime.fromisoformat(r['fecha_expedicion'])
            fv = datetime.fromisoformat(r['fecha_vencimiento'])
            estado = "VIGENTE" if datetime.now() <= fv else "VENCIDO"
            resultado = {
                "estado": estado,
                "color": "verde" if estado=="VIGENTE" else "cafe",
                "folio": folio,
                "fecha_expedicion": fe.strftime('%d/%m/%Y'),
                "fecha_vencimiento": fv.strftime('%d/%m/%Y'),
                "marca": r['marca'],
                "linea": r['linea'],
                "año": r['anio'],
                "numero_serie": r['numero_serie'],
                "numero_motor": r['numero_motor']
            }
        return render_template('resultado_consulta.html', resultado=resultado)
    return render_template('consulta_folio.html')

@app.route('/descargar_pdf/<folio>')
def descargar_pdf(folio):
    return send_file(f"documentos/{folio}.pdf", as_attachment=True)

@app.route('/admin_folios')
def admin_folios():
    if 'admin' not in session:
        return redirect(url_for('login'))
    registros = supabase.table("folios_registrados").select("*").execute().data or []
    return render_template('admin_folios.html', folios=registros)

@app.route('/editar_folio/<folio>', methods=['GET', 'POST'])
def editar_folio(folio):
    if 'admin' not in session:
        return redirect(url_for('login'))
    if request.method=='POST':
        supabase.table("folios_registrados").update({
            "marca": request.form['marca'],
            "linea": request.form['linea'],
            "anio":  request.form['anio'],
            "numero_serie": request.form['numero_serie'],
            "numero_motor": request.form['numero_motor'],
            "fecha_expedicion": request.form['fecha_expedicion'],
            "fecha_vencimiento": request.form['fecha_vencimiento']
        }).eq("folio", folio).execute()
        flash("Folio actualizado correctamente.", "success")
        return redirect(url_for('admin_folios'))
    reg = supabase.table("folios_registrados").select("*").eq("folio", folio).execute().data
    if not reg:
        flash("Folio no encontrado.", "error")
        return redirect(url_for('admin_folios'))
    return render_template('editar_folio.html', folio=reg[0])

@app.route('/eliminar_folio', methods=['POST'])
def eliminar_folio():
    if 'admin' not in session:
        return redirect(url_for('login'))
    supabase.table("folios_registrados").delete().eq("folio", request.form['folio']).execute()
    flash("Folio eliminado correctamente.", "success")
    return redirect(url_for('admin_folios'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__=='__main__':
    app.run(debug=True)
