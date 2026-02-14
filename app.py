from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import pandas as pd
import io
import os

app = Flask(__name__)

# Configuración de Seguridad y Base de Datos
app.secret_key = 'clave_secreta_memocont_2024' # Cambia esto por algo más complejo en producción
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'ventas_memocont.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- MODELOS DE LA BASE DE DATOS (SQLITE) ---

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(50), nullable=False)
    sede = db.Column(db.String(50), nullable=False)

class Venta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=datetime.now)
    vendedor = db.Column(db.String(50), nullable=False)
    sede = db.Column(db.String(50), nullable=False)
    dni_cliente = db.Column(db.String(15), nullable=True)
    detalle = db.Column(db.Text, nullable=False)
    metodo_pago = db.Column(db.String(20), nullable=False) # EFECTIVO o YAPE
    total = db.Column(db.Float, nullable=False)

# --- CREACIÓN DE BASE DE DATOS Y USUARIOS DE PRUEBA ---

with app.app_context():
    db.create_all()
    # Creamos usuarios por defecto si la base de datos está vacía
    if not Usuario.query.filter_by(username='admin').first():
        usuarios_iniciales = [
            Usuario(username='admin', password='123', sede='Sede Central'),
            Usuario(username='vendedor1', password='123', sede='Sede Norte'),
            Usuario(username='vendedor2', password='123', sede='Sede Sur')
        ]
        db.session.bulk_save_objects(usuarios_iniciales)
        db.session.commit()
        print("Base de datos inicializada con usuarios de prueba.")

# --- RUTAS DEL SISTEMA ---

@app.route('/')
def login_page():
    # Si ya está logueado, lo mandamos al sistema
    if 'user' in session:
        return redirect(url_for('pos_page'))
    return render_template('login.html')

@app.route('/auth', methods=['POST'])
def auth():
    user_input = request.form.get('user')
    pass_input = request.form.get('pass')
    
    usuario = Usuario.query.filter_by(username=user_input, password=pass_input).first()
    
    if usuario:
        session['user'] = usuario.username
        session['sede'] = usuario.sede
        return redirect(url_for('pos_page'))
    else:
        return "Usuario o contraseña incorrectos. <a href='/'>Volver a intentar</a>"

@app.route('/pos')
def pos_page():
    # Protección de ruta
    if 'user' not in session:
        return redirect(url_for('login_page'))
    return render_template('index.html', user=session['user'], sede=session['sede'])

@app.route('/save_venta', methods=['POST'])
def save_venta():
    if 'user' not in session:
        return jsonify({"status": "error", "message": "No autorizado"}), 401
    
    data = request.json
    try:
        nueva_venta = Venta(
            vendedor=session['user'],
            sede=session['sede'],
            dni_cliente=data.get('dni'),
            detalle=data.get('detalle'),
            metodo_pago=data.get('metodo_pago'),
            total=float(data.get('total'))
        )
        db.session.add(nueva_venta)
        db.session.commit()
        return jsonify({"status": "success", "id": nueva_venta.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/exportar')
def exportar():
    if 'user' not in session:
        return redirect(url_for('login_page'))
    
    # Consultamos todas las ventas de la base de datos
    ventas = Venta.query.all()
    
    # Creamos una lista de diccionarios para Pandas
    lista_ventas = []
    for v in ventas:
        lista_ventas.append({
            'ID Venta': v.id,
            'Fecha y Hora': v.fecha.strftime("%Y-%m-%d %H:%M:%S"),
            'Sede': v.sede,
            'Vendedor': v.vendedor,
            'DNI Cliente': v.dni_cliente if v.dni_cliente else "P. General",
            'Detalle Productos': v.detalle,
            'Método Pago': v.metodo_pago,
            'Total (S/.)': v.total
        })
    
    if not lista_ventas:
        return "No hay ventas registradas para exportar. <a href='/pos'>Volver</a>"

    # Convertimos a DataFrame de Pandas
    df = pd.DataFrame(lista_ventas)
    
    # Creamos el archivo Excel en memoria
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte Ventas')
        # Ajustar ancho de columnas automáticamente en el Excel
        worksheet = writer.sheets['Reporte Ventas']
        for i, col in enumerate(df.columns):
            column_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.set_column(i, i, column_len)

    output.seek(0)
    
    filename = f"Reporte_MemoCont_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(output, download_name=filename, as_attachment=True)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

if __name__ == '__main__':
    # Ejecutamos la app
    app.run(debug=True, port=5000)

@app.route('/caja')
def reporte_caja():
    if 'user' not in session: return redirect(url_for('login_page'))
    
    # Obtenemos las ventas del día actual
    hoy = datetime.now().date()
    ventas_hoy = Venta.query.filter(db.func.date(Venta.fecha) == hoy).all()
    
    # Calculamos totales
    total_efectivo = sum(v.total for v in ventas_hoy if v.metodo_pago == 'EFECTIVO')
    total_yape = sum(v.total for v in ventas_hoy if v.metodo_pago == 'YAPE')
    
    return render_template('reporte_caja.html', 
                           ventas=ventas_hoy, 
                           efectivo=total_efectivo, 
                           yape=total_yape, 
                           total=total_efectivo + total_yape,
                           user=session['user'], 
                           sede=session['sede'])