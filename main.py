import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from datetime import datetime, timedelta
from supabase import create_client
import fitz  # PyMuPDF

# ------------------------
# Configuración de la app
# ------------------------
app = Flask(__name__)
app.secret_key = 'clave_muy_segura_123456'

# Credenciales de Supabase
SUPABASE_URL = "https://xsagwqepoljfsogusubw.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhzYWd3cWVwbXplY3VzdWJ3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDM5NjM3NTUsImV4cCI6MjA1OTUzOTc1NX0.NUixULn0m2o49At8j6X58UqbXre2O2_JStqzls_8Gws"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Carpeta donde vamos a guardar los PDFs generados
os.makedirs('documentos', exist_ok=True)


# ------------------------
#  Función para generar PDF
# ------------------------
def generar_pdf(folio, numero_serie):
    # Abrimos la plantilla
    plantilla = "oaxacaverga.pdf"
    doc = fitz.open(plantilla)
    page = doc[0]

    # Coordenadas
    x_fecha, y_fecha = 136, 141    # 25 puntos arriba de la serie
    x_serie, y_serie = 136, 166
    x_hora, y_hora   = 146, 206

    # Datos dinámicos
    fecha = datetime.now().strftime("%d/%m/%Y")
    hora  = datetime.now().strftime("%H:%M:%S")

    # Insertamos
    page.insert_text((x_fecha, y_fecha), fecha, fontsize=10)
    page.insert_text((x_serie, y_serie), numero_serie, fontsize=10)
    page.insert_text((x_hora, y_hora), hora, fontsize=10)

    # Guardamos
    salida = os.path.join("documentos", f"{folio}.pdf")
    doc.save(salida)
    doc.close()
    return salida


# ------------------------
#  Rutas de la aplicación
# ------------------------

@app.route('/')
def inicio():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form['username']
        pwd  = request.form['password']

        # Admin hardcodeado
        if user == 'Gsr89roja.' and pwd == 'serg890105':
            session['admin'] = True
            return redirect(url_for('panel'))

        # Usuario normal
        resp = supabase.table("verificaciondigitalcdmx") \
                       .select("*") \
                       .eq("username", user) \
                       .eq("password", pwd) \
                       .execute()
        if resp.data:
            session['user_id']  = resp.data[0]['id']
            session['username'] = user
            return redirect(url_for('registro_usuario'))

        flash('Credenciales incorrectas', 'error')

    return render_template('login.html')


@app.route('/panel')
def panel():
    if not session.get('admin'):
        return redirect(url_for('login'))
    return render_template('panel.html')


@app.route('/crear_usuario', methods=['GET', 'POST'])
def crear_usuario():
    if not session.get('admin'):
        return redirect(url_for('login'))
    if request.method == 'POST':
        user   = request.form['username']
        pwd    = request.form['password']
        folios = int(request.form['folios'])

        existe = supabase.table("verificaciondigitalcdmx") \
                         .select("id") \
                         .eq("username", user) \
                         .execute()
        if existe.data:
            flash('El usuario ya existe.', 'error')
        else:
            supabase.table("verificaciondigitalcdmx").insert({
                "username": user,
                "password": pwd,
                "folios_asignac": folios,
                "folios_usados": 0
            }).execute()
            flash('Usuario creado.', 'success')

    return render_template('crear_usuario.html')


@app.route('/registro_admin', methods=['GET', 'POST'])
def registro_admin():
    if not session.get('admin'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        folio = request.form['folio']
        serie = request.form['serie']
        vig   = int(request.form['vigencia'])

        # Preguardado
        if supabase.table("folios_registrados").select("*").eq("folio", folio).execute().data:
            flash('Folio ya existe.', 'error')
            return render_template('registro_admin.html')

        # Insert BD
        hoy = datetime.now()
        supabase.table("folios_registrados").insert({
            "folio": folio,
            "marca": request.form['marca'],
            "linea": request.form['linea'],
            "anio": request.form['anio'],
            "numero_serie": serie,
            "numero_motor": request.form['motor'],
            "fecha_expedicion": hoy.isoformat(),
            "fecha_vencimiento": (hoy + timedelta(days=vig)).isoformat()
        }).execute()

        # Generar PDF y enviar
        pdf = generar_pdf(folio, serie)
        if os.path.exists(pdf):
            return send_file(pdf, as_attachment=True, download_name=f"{folio}.pdf")
        else:
            flash('Error generando PDF.', 'error')

    return render_template('registro_admin.html')


@app.route('/registro_usuario', methods=['GET', 'POST'])
def registro_usuario():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        folio = request.form['folio']
        serie = request.form['serie']
        vig   = int(request.form['vigencia'])

        # Ya existe?
        if supabase.table("folios_registrados").select("*").eq("folio", folio).execute().data:
            flash('Folio ya existe.', 'error')
            return redirect(url_for('registro_usuario'))

        # Quedan folios?
        u = supabase.table("verificaciondigitalcdmx") \
                    .select("folios_asignac,folios_usados") \
                    .eq("id", session['user_id']).execute().data[0]
        if u['folios_asignac'] - u['folios_usados'] < 1:
            flash('No tienes folios disponibles.', 'error')
            return redirect(url_for('registro_usuario'))

        # Insert y actualizar contador
        hoy = datetime.now()
        supabase.table("folios_registrados").insert({
            "folio": folio,
            "marca": request.form['marca'],
            "linea": request.form['linea'],
            "anio": request.form['anio'],
            "numero_serie": serie,
            "numero_motor": request.form['motor'],
            "fecha_expedicion": hoy.isoformat(),
            "fecha_vencimiento": (hoy + timedelta(days=vig)).isoformat()
        }).execute()
        supabase.table("verificaciondigitalcdmx") \
                 .update({"folios_usados": u['folios_usados'] + 1}) \
                 .eq("id", session['user_id']).execute()

        # Generar y enviar PDF
        pdf = generar_pdf(folio, serie)
        if os.path.exists(pdf):
            return send_file(pdf, as_attachment=True, download_name=f"{folio}.pdf")
        else:
            flash('Error generando PDF.', 'error')

    # Mostrar info de folios
    info = supabase.table("verificaciondigitalcdmx") \
                   .select("folios_asignac,folios_usados") \
                   .eq("id", session['user_id']).execute().data[0]
    return render_template('registro_usuario.html', folios_info=info)


@app.route('/consulta_folio', methods=['GET', 'POST'])
def consulta_folio():
    resultado = None
    if request.method == 'POST':
        folio = request.form['folio']
        data  = supabase.table("folios_registrados").select("*").eq("folio", folio).execute().data
        if not data:
            resultado = {"estado": "No encontrado", "folio": folio}
        else:
            r   = data[0]
            fe  = datetime.fromisoformat(r['fecha_expedicion'])
            fv  = datetime.fromisoformat(r['fecha_vencimiento'])
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
                "numero_motor": r['numero_motor']
            }
    return render_template('consulta_folio.html', resultado=resultado)


@app.route('/admin_folios')
def admin_folios():
    if not session.get('admin'):
        return redirect(url_for('login'))
    registros = supabase.table("folios_registrados").select("*").execute().data or []
    return render_template('admin_folios.html', folios=registros)


@app.route('/editar_folio/<folio>', methods=['GET', 'POST'])
def editar_folio(folio):
    if not session.get('admin'):
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
        flash("Actualizado.", "success")
        return redirect(url_for('admin_folios'))
    reg = supabase.table("folios_registrados").select("*").eq("folio", folio).execute().data
    if not reg:
        flash("No existe.", "error")
        return redirect(url_for('admin_folios'))
    return render_template('editar_folio.html', folio=reg[0])


@app.route('/eliminar_folio', methods=['POST'])
def eliminar_folio():
    if not session.get('admin'):
        return redirect(url_for('login'))
    supabase.table("folios_registrados").delete().eq("folio", request.form['folio']).execute()
    flash("Eliminado.", "success")
    return redirect(url_for('admin_folios'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)
