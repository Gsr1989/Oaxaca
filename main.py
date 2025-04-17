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
        response = supabase.table("verificaciondigitalcdmx")\
            .select("*")\
            .eq("username", username)\
            .eq("password", password)\
            .execute()
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
    template_path = "oaxacaverga.pdf"
    doc = fitz.open(template_path)
    page = doc[0]
    # Coordenadas
    x_hora, y_hora = 146, 206
    x_serie, y_serie = 136, 166
    x_fecha, y_fecha = x_serie, y_serie - 25
    hora_actual = datetime.now().strftime("%H:%M:%S")
    fecha_expedicion = datetime.now().strftime("%d/%m/%Y")
    page.insert_text((x_fecha, y_fecha), fecha_expedicion, fontsize=10)
    page.insert_text((x_serie, y_serie), numero_serie, fontsize=10)
    page.insert_text((x_hora, y_hora), hora_actual, fontsize=10)
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
        # Validar folio
        if supabase.table("folios_registrados").select("*").eq("folio", folio).execute().data:
            flash('Error: el folio ya existe.', 'error')
            return redirect(url_for('registro_usuario'))
        # Verificar disponibilidad
        u = supabase.table("verificaciondigitalcdmx")\
            .select("folios_asignac, folios_usados")\
            .eq("id", user_id).execute().data[0]
        restantes = u['folios_asignac'] - u['folios_usados']
        if restantes <= 0:
            flash("No tienes folios disponibles.", 'error')
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
        supabase.table("verificaciondigitalcdmx")\
            .update({"folios_usados": u["folios_usados"] + 1})\
            .eq("id", user_id).execute()
        pdf_path = generar_pdf(folio, marca, linea, anio, numero_serie, numero_motor, vigencia)
        flash("Folio registrado correctamente.", 'success')
        return send_file(pdf_path, as_attachment=True)
    u = supabase.table("verificaciondigitalcdmx")\
        .select("folios_asignac, folios_usados")\
        .eq("id", user_id).execute().data[0]
    return render_template("registro_usuario.html", folios_info=u)

# — RUTA PARA ADMINISTRADOR — #
@app.route('/registro_admin', methods=['GET', 'POST'])
def registro_admin():
    if 'admin' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        folio = request.form['folio']
        marca = request.form['marca']
        linea = request.form['linea']
        anio = request.form['anio']
        numero_serie = request.form['serie']
        numero_motor = request.form['motor']
        vigencia = int(request.form['vigencia'])
        if supabase.table("folios_registrados").select("*").eq("folio", folio).execute().data:
            flash('Error: el folio ya existe.', 'error')
            return render_template('registro_admin.html')
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
        flash("Folio registrado correctamente.", 'success')
        return redirect(url_for('admin'))
    return render_template('registro_admin.html')

# — RUTA DE CONSULTA DE FOLIO — #
@app.route('/consulta_folio', methods=['GET', 'POST'])
def consulta_folio():
    resultado = None
    if request.method == 'POST':
        folio = request.form['folio']
        r = supabase.table("folios_registrados").select("*").eq("folio", folio).execute().data
        if not r:
            resultado = {"estado": "No encontrado", "folio": folio}
        else:
            reg = r[0]
            fe = datetime.fromisoformat(reg['fecha_expedicion'])
            fv = datetime.fromisoformat(reg['fecha_vencimiento'])
            estado = "VIGENTE" if datetime.now() <= fv else "VENCIDO"
            resultado = {
                "estado": estado,
                "folio": folio,
                "fecha_expedicion": fe.strftime("%d/%m/%Y"),
                "fecha_vencimiento": fv.strftime("%d/%m/%Y"),
                "marca": reg['marca'],
                "linea": reg['linea'],
                "año": reg['anio'],
                "numero_serie": reg['numero_serie'],
                "numero_motor": reg['numero_motor']
            }
    return render_template("consulta_folio.html", resultado=resultado)

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
        folios = int(request.form['folios'])
        if supabase.table("verificaciondigitalcdmx").select("id").eq("username", username).execute().data:
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

@app.route('/admin_folios')
def admin_folios():
    if 'admin' not in session:
        return redirect(url_for('login'))
    filtro = request.args.get('filtro', '')
    criterio = request.args.get('criterio', 'folio')
    ordenar = request.args.get('ordenar', 'desc')
    estado_filtro = request.args.get('estado', 'todos')
    fecha_inicio = request.args.get('fecha_inicio', '')
    fecha_fin = request.args.get('fecha_fin', '')

    data = supabase.table("folios_registrados").select("*").execute().data or []
    filtrados = []
    for f in data:
        try:
            fe = datetime.fromisoformat(f['fecha_expedicion'])
            fv = datetime.fromisoformat(f['fecha_vencimiento'])
        except:
            continue
        est = "VIGENTE" if datetime.now() <= fv else "VENCIDO"
        f['estado'] = est
        if estado_filtro in ['vigente','vencido'] and est.upper() != estado_filtro.upper():
            continue
        if filtro:
            campo = f[criterio] if criterio in f else ''
            if filtro.lower() not in str(campo).lower():
                continue
        filtrados.append(f)
    filtrados.sort(key=lambda x: x['fecha_expedicion'], reverse=(ordenar=='desc'))

    return render_template('admin_folios.html',
                           folios=filtrados,
                           filtro=filtro,
                           criterio=criterio,
                           ordenar=ordenar,
                           estado=estado_filtro,
                           fecha_inicio=fecha_inicio,
                           fecha_fin=fecha_fin)

@app.route('/eliminar_folio', methods=['POST'])
def eliminar_folio():
    if 'admin' not in session:
        return redirect(url_for('login'))
    supabase.table("folios_registrados").delete().eq("folio", request.form['folio']).execute()
    flash('Folio eliminado correctamente.', 'success')
    return redirect(url_for('admin_folios'))

@app.route('/editar_folio/<folio>', methods=['GET', 'POST'])
def editar_folio(folio):
    if 'admin' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        supabase.table("folios_registrados").update({
            "marca": request.form['marca'],
            "linea": request.form['linea'],
            "anio": request.form['anio'],
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

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
