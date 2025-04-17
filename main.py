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

        response = supabase.table("verificaciondigitalcdmx").select("*").eq("username", username).eq("password", password).execute()
        usuarios = response.data

        if usuarios:
            session['user_id'] = usuarios[0]['id']
            session['username'] = usuarios[0]['username']
            return redirect(url_for('registro_usuario'))
        else:
            flash('Credenciales incorrectas', 'error')

    return render_template('login.html')


# Función para generar el PDF
def generar_pdf(folio, marca, linea, anio, numero_serie, numero_motor, vigencia):
    # Abrir la plantilla
    template_path = "path_to_your_template/oaxacaverga.pdf"  # Cambia la ruta si es necesario
    doc = fitz.open(template_path)
    page = doc[0]

    # Coordenadas de los datos
    x_hora, y_hora = 146, 206
    x_serie, y_serie = 136, 166
    x_fecha, y_fecha = x_serie, y_serie - 25

    # Datos automáticos
    hora_actual = datetime.now().strftime("%H:%M:%S")
    fecha_expedicion = datetime.now().strftime("%d/%m/%Y")

    # Insertar datos en las posiciones correspondientes
    page.insert_text((x_fecha, y_fecha), fecha_expedicion, fontsize=10)  # Fecha
    page.insert_text((x_serie, y_serie), numero_serie, fontsize=10)      # Serie
    page.insert_text((x_hora, y_hora), hora_actual, fontsize=10)         # Hora

    # Guardar el PDF con los datos insertados
    output_path = "/mnt/data/oaxacaverga_completo_final.pdf"
    doc.save(output_path)
    doc.close()

    return output_path


@app.route('/registro_usuario', methods=['GET', 'POST'])
def registro_usuario():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    if request.method == 'POST':
        folio = request.form['folio']
        marca = request.form['marca']
        linea = request.form['linea']
        anio = request.form['anio']
        numero_serie = request.form['serie']
        numero_motor = request.form['motor']
        vigencia = int(request.form['vigencia'])

        existente = supabase.table("folios_registrados").select("*").eq("folio", folio).execute()
        if existente.data:
            flash('Error: el folio ya existe.', 'error')
            return redirect(url_for('registro_usuario'))

        usuario_data = supabase.table("verificaciondigitalcdmx").select("folios_asignac, folios_usados").eq("id", user_id).execute()
        if not usuario_data.data:
            flash("No se pudo obtener la información del usuario.", "error")
            return redirect(url_for('registro_usuario'))

        folios = usuario_data.data[0]
        restantes = folios['folios_asignac'] - folios['folios_usados']
        if restantes <= 0:
            flash("No tienes folios disponibles para registrar.", "error")
            return redirect(url_for('registro_usuario'))

        fecha_expedicion = datetime.now()
        fecha_vencimiento = fecha_expedicion + timedelta(days=vigencia)

        data = {
            "folio": folio,
            "marca": marca,
            "linea": linea,
            "anio": anio,
            "numero_serie": numero_serie,
            "numero_motor": numero_motor,
            "fecha_expedicion": fecha_expedicion.isoformat(),
            "fecha_vencimiento": fecha_vencimiento.isoformat()
        }

        supabase.table("folios_registrados").insert(data).execute()
        supabase.table("verificaciondigitalcdmx").update({
            "folios_usados": folios["folios_usados"] + 1
        }).eq("id", user_id).execute()

        # Generar PDF con los datos del folio
        pdf_path = generar_pdf(folio, marca, linea, anio, numero_serie, numero_motor, vigencia)
        
        flash("Folio registrado correctamente.", "success")

        # Enviar el archivo PDF generado como respuesta
        return send_file(pdf_path, as_attachment=True)

    response = supabase.table("verificaciondigitalcdmx").select("folios_asignac, folios_usados").eq("id", user_id).execute()
    folios_info = response.data[0] if response.data else {}
    return render_template("registro_usuario.html", folios_info=folios_info)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)
