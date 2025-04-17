import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from datetime import datetime, timedelta
from supabase import create_client
import fitz  # PyMuPDF

app = Flask(__name__)
app.secret_key = 'clave_muy_segura_123456'

# Supabase
SUPABASE_URL = "https://xsagwqepoljfsogusubw.supabase.co"
SUPABASE_KEY = "TU_SUPABASE_KEY"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Carpeta de PDFs
os.makedirs('documentos', exist_ok=True)

def generar_pdf(folio, serie):
    doc = fitz.open("oaxacaverga.pdf")
    page = doc[0]
    fecha = datetime.now().strftime("%d/%m/%Y")
    hora  = datetime.now().strftime("%H:%M:%S")
    # Coordenadas
    page.insert_text((136, 141), fecha, fontsize=10)
    page.insert_text((136, 166), serie, fontsize=10)
    page.insert_text((146, 206), hora, fontsize=10)
    salida = os.path.join("documentos", f"{folio}.pdf")
    doc.save(salida)
    doc.close()
    return salida

@app.route('/')
def inicio():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        u = request.form['username']; p = request.form['password']
        if u=='Gsr89roja.' and p=='serg890105':
            session['admin']=True; return redirect(url_for('panel'))
        resp = supabase.table("verificaciondigitalcdmx")\
                       .select("*")\
                       .eq("username",u).eq("password",p).execute()
        if resp.data:
            session['user_id']=resp.data[0]['id']
            return redirect(url_for('registro_usuario'))
        flash('Credenciales incorrectas','error')
    return render_template('login.html')

@app.route('/panel')
def panel():
    if not session.get('admin'): return redirect(url_for('login'))
    return render_template('panel.html')

@app.route('/crear_usuario', methods=['GET','POST'])
def crear_usuario():
    if not session.get('admin'): return redirect(url_for('login'))
    if request.method=='POST':
        user=request.form['username']; pwd=request.form['password']; fol=int(request.form['folios'])
        existe = supabase.table("verificaciondigitalcdmx")\
                         .select("id").eq("username",user).execute()
        if existe.data:
            flash('Usuario ya existe','error')
        else:
            supabase.table("verificaciondigitalcdmx").insert({
                "username":user,"password":pwd,
                "folios_asignac":fol,"folios_usados":0
            }).execute()
            flash('Usuario creado','success')
    return render_template('crear_usuario.html')

@app.route('/registro_admin', methods=['GET','POST'])
def registro_admin():
    if not session.get('admin'): return redirect(url_for('login'))
    if request.method=='POST':
        fol=request.form['folio']; ser=request.form['serie']; vig=int(request.form['vigencia'])
        if supabase.table("folios_registrados").select("*").eq("folio",fol).execute().data:
            flash('Folio ya existe','error'); return render_template('registro_admin.html')
        hoy=datetime.now()
        supabase.table("folios_registrados").insert({
            "folio":fol,
            "marca":request.form['marca'],
            "linea":request.form['linea'],
            "anio":request.form['anio'],
            "numero_serie":ser,
            "numero_motor":request.form['motor'],
            "fecha_expedicion":hoy.isoformat(),
            "fecha_vencimiento":(hoy+timedelta(days=vig)).isoformat()
        }).execute()
        pdf=generar_pdf(fol,ser)
        if os.path.exists(pdf):
            return send_file(pdf, as_attachment=True, download_name=f"{fol}.pdf")
        flash('Error generando PDF','error')
    return render_template('registro_admin.html')

@app.route('/registro_usuario', methods=['GET','POST'])
def registro_usuario():
    if not session.get('user_id'): return redirect(url_for('login'))
    if request.method=='POST':
        fol=request.form['folio']; ser=request.form['serie']; vig=int(request.form['vigencia'])
        if supabase.table("folios_registrados").select("*").eq("folio",fol).execute().data:
            flash('Folio ya existe','error'); return redirect(url_for('registro_usuario'))
        u = supabase.table("verificaciondigitalcdmx")\
                    .select("folios_asignac,folios_usados")\
                    .eq("id",session['user_id']).execute().data[0]
        if u['folios_asignac']-u['folios_usados']<1:
            flash('Sin folios disponibles','error'); return redirect(url_for('registro_usuario'))
        hoy=datetime.now()
        supabase.table("folios_registrados").insert({
            "folio":fol,
            "marca":request.form['marca'],
            "linea":request.form['linea'],
            "anio":request.form['anio'],
            "numero_serie":ser,
            "numero_motor":request.form['motor'],
            "fecha_expedicion":hoy.isoformat(),
            "fecha_vencimiento":(hoy+timedelta(days=vig)).isoformat()
        }).execute()
        supabase.table("verificaciondigitalcdmx")\
                 .update({"folios_usados":u['folios_usados']+1})\
                 .eq("id",session['user_id']).execute()
        pdf=generar_pdf(fol,ser)
        if os.path.exists(pdf):
            return send_file(pdf,as_attachment=True,download_name=f"{fol}.pdf")
        flash('Error generando PDF','error')
    info = supabase.table("verificaciondigitalcdmx")\
                   .select("folios_asignac,folios_usados")\
                   .eq("id",session['user_id']).execute().data[0]
    return render_template('registro_usuario.html', folios_info=info)

@app.route('/consulta_folio', methods=['GET','POST'])
def consulta_folio():
    resultado=None
    if request.method=='POST':
        fol=request.form['folio']
        data=supabase.table("folios_registrados").select("*").eq("folio",fol).execute().data
        if not data:
            resultado={"estado":"No encontrado","folio":fol}
        else:
            r=data[0]
            fe=datetime.fromisoformat(r['fecha_expedicion'])
            fv=datetime.fromisoformat(r['fecha_vencimiento'])
            estado="VIGENTE" if datetime.now()<=fv else "VENCIDO"
            resultado={
                "estado":estado,
                "folio":fol,
                "fecha_expedicion":fe.strftime("%d/%m/%Y"),
                "fecha_vencimiento":fv.strftime("%d/%m/%Y"),
                "marca":r['marca'],
                "linea":r['linea'],
                "año":r['anio'],
                "numero_serie":r['numero_serie'],
                "numero_motor":r['numero_motor']
            }
    return render_template('consulta_folio.html', resultado=resultado)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__=='__main__':
    app.run(debug=True)
