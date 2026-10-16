import io
import os
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

# Carga la variable DATABASE_URL del archivo .env automáticamente solo en entorno local
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import pandas as pd
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy 

# -------------------------------------------------------------------------
# 1. INICIALIZACIÓN Y CONFIGURACIÓN DE FLASK & SQLALCHEMY
# -------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = 'clave_secreta_asuaaastab'

# Configuración de base de datos (Render PostgreSQL o SQLite local)
database_url = os.environ.get('DATABASE_URL', 'sqlite:///inventario.db')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql+psycopg2://', 1)

if database_url and '-pooler' in database_url:
    database_url = database_url.replace('-pooler', '')

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

db = SQLAlchemy(app)

# Configuración de archivos subidos (Matrículas: Documentos y Fotos)
UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

EXTENSIONES_PERMITIDAS = {'pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx'}

def archivo_permitido(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in EXTENSIONES_PERMITIDAS

# -------------------------------------------------------------------------
# 2. FILTROS Y FUNCIONES AUXILIARES
# -------------------------------------------------------------------------
def cop_filter(val):
    try:
        if val is None:
            val = 0
        return f"$ {float(val):,.0f}".replace(',', '.')
    except (ValueError, TypeError):
        return "$ 0"

app.jinja_env.filters['cop'] = cop_filter

CONSECUTIVO_FILE = 'consecutivo.txt'
CONSECUTIVO_FACTURA_FILE = 'consecutivo_factura.txt'

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
]

def limpiar_monto(val):
    if val is None:
        return 0.0
    val_str = str(val).strip()
    if not val_str:
        return 0.0

    val_str = val_str.replace('$', '').replace(' ', '')

    if '.' in val_str and ',' in val_str:
        val_str = val_str.replace('.', '').replace(',', '.')
    elif '.' in val_str:
        parts = val_str.split('.')
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            val_str = "".join(parts)
    elif ',' in val_str:
        parts = val_str.split(',')
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            val_str = "".join(parts)
        else:
            val_str = val_str.replace(',', '.')

    try:
        return float(val_str)
    except (ValueError, TypeError):
        return 0.0

def ver_siguiente_consecutivo():
    contador = 0
    if os.path.exists(CONSECUTIVO_FILE):
        try:
            with open(CONSECUTIVO_FILE, 'r') as f:
                contenido = f.read().strip()
                if contenido.isdigit():
                    contador = int(contenido)
        except Exception:
            contador = 0
    return f"{(contador + 1):03d}"

def obtener_siguiente_consecutivo():
    contador = 0
    if os.path.exists(CONSECUTIVO_FILE):
        try:
            with open(CONSECUTIVO_FILE, 'r') as f:
                contenido = f.read().strip()
                if contenido.isdigit():
                    contador = int(contenido)
        except Exception:
            contador = 0

    contador += 1
    with open(CONSECUTIVO_FILE, 'w') as f:
        f.write(str(contador))

    return f"{contador:03d}"

def ver_siguiente_consecutivo_factura():
    try:
        if os.path.exists(CONSECUTIVO_FACTURA_FILE):
            with open(CONSECUTIVO_FACTURA_FILE, 'r') as f:
                actual = int(f.read().strip())
            return f"{(actual + 1):03d}"
    except Exception:
        pass
    return "001"

def obtener_siguiente_consecutivo_factura():
    try:
        if os.path.exists(CONSECUTIVO_FACTURA_FILE):
            with open(CONSECUTIVO_FACTURA_FILE, 'r') as f:
                actual = int(f.read().strip())
        else:
            actual = 0
        siguiente = actual + 1
        with open(CONSECUTIVO_FACTURA_FILE, 'w') as f:
            f.write(str(siguiente))
        return f"{siguiente:03d}"
    except Exception:
        return "001"

def calcular_meses_diferencia(mes_inicio, mes_final):
    try:
        y1, m1 = map(int, mes_inicio.split('-'))
        y2, m2 = map(int, mes_final.split('-'))
        diferencia = (y2 - y1) * 12 + (m2 - m1) + 1
        return diferencia if diferencia > 0 else 1
    except Exception:
        return 1

# -------------------------------------------------------------------------
# 3. MODELOS DE BASE DE DATOS
# -------------------------------------------------------------------------
class PQRSF(db.Model):
    __tablename__ = 'pqrsf'
    
    id = db.Column(db.Integer, primary_key=True)
    radicado = db.Column(db.String(50), unique=True, nullable=False)
    tipo = db.Column(db.String(50), nullable=False)
    nombre_solicitante = db.Column('nombre_solicitante', db.String(120), nullable=True)
    cedula_solicitante = db.Column('cedula_solicitante', db.String(20), nullable=True)
    correo = db.Column(db.String(120), nullable=True)
    telefono = db.Column(db.String(20), nullable=True)
    asunto = db.Column(db.String(200), nullable=True)
    descripcion = db.Column(db.Text, nullable=True)
    estado = db.Column(db.String(30), default='EN TRAMITE')
    fecha_radicacion = db.Column(db.DateTime, default=datetime.now)
    fecha_limite_respuesta = db.Column(db.DateTime, nullable=True)

class UsuarioMatricula(db.Model):
    __tablename__ = 'usuarios_matricula'
    
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    cedula = db.Column(db.String(20), nullable=False)
    estado_matricula = db.Column(db.String(20), default='ACTIVO')
    fecha_compra = db.Column(db.String(10), nullable=True)
    nota = db.Column(db.Text, nullable=True)
    documento_adjunto = db.Column(db.String(255), nullable=True)
    foto_ubicacion = db.Column(db.String(255), nullable=True)
    fecha_registro = db.Column(db.DateTime, default=datetime.now)

class Producto(db.Model):
    __tablename__ = 'producto'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    categoria = db.Column(db.String(50))
    cantidad = db.Column(db.Integer, default=0)
    unidad = db.Column(db.String(20), default='Unidades')
    ubicacion = db.Column(db.String(100))
    movimientos = db.relationship('MovimientoInventario', backref='producto', lazy=True, cascade="all, delete-orphan")

class MovimientoInventario(db.Model):
    __tablename__ = 'movimiento_inventario'
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    responsable = db.Column(db.String(100), nullable=False)
    motivo = db.Column(db.String(255), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.now)

class PagoAnticipado(db.Model):
    __tablename__ = 'pagos_anticipados'
    id = db.Column(db.Integer, primary_key=True)
    nombre_usuario = db.Column(db.String(120), nullable=False)
    documento = db.Column(db.String(20), nullable=False)
    codigo_usuario = db.Column(db.String(30), nullable=False)
    direccion_predio = db.Column(db.String(200), nullable=True)
    mes_inicio = db.Column(db.String(7), nullable=False)
    mes_final = db.Column(db.String(7), nullable=False)
    numero_meses = db.Column(db.Integer, nullable=False)
    meses_restantes = db.Column(db.Integer, nullable=False)
    valor_unitario = db.Column(db.Float, nullable=False)
    valor_total = db.Column(db.Float, nullable=False)
    saldo_pendiente = db.Column(db.Float, nullable=False)
    fecha_registro = db.Column(db.DateTime, default=datetime.now)

    @property
    def rango_periodo(self):
        try:
            y1, m1 = map(int, self.mes_inicio.split('-'))
            y2, m2 = map(int, self.mes_final.split('-'))
            meses_nombres = [
                'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
            ]
            inicio_str = f"{meses_nombres[m1-1]} {y1}"
            fin_str = f"{meses_nombres[m2-1]} {y2}"
            return f"{inicio_str} – {fin_str}"
        except Exception:
            return f"{self.mes_inicio} a {self.mes_final}"

class Configuracion(db.Model):
    __tablename__ = 'configuracion'
    clave = db.Column(db.String(50), primary_key=True)
    valor = db.Column(db.Float, default=0.0)

def obtener_cargo_mes_db():
    try:
        conf = db.session.get(Configuracion, 'total_cargo_mes')
        return conf.valor if conf else 0.0
    except Exception:
        db.session.rollback()
        return 0.0

def guardar_cargo_mes_db(nuevo_valor):
    try:
        conf = db.session.get(Configuracion, 'total_cargo_mes')
        if not conf:
            conf = Configuracion(clave='total_cargo_mes', valor=nuevo_valor)
            db.session.add(conf)
        else:
            conf.valor = nuevo_valor
        db.session.commit()
    except Exception:
        db.session.rollback()

# Inicialización segura de tablas en la base de datos
with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        print(f"Error al inicializar las tablas en la base de datos: {e}")

# -------------------------------------------------------------------------
# 4. RUTAS PRINCIPALES Y NAVEGACIÓN
# -------------------------------------------------------------------------
@app.route('/')
def inicio():
    return render_template('index.html')

@app.route('/contratacion')
def contratacion():
    return "<h1>Módulo de Contratación</h1><p>En construcción...</p>"

# -------------------------------------------------------------------------
# Configuración de carpeta de subida para PQRSF
# -------------------------------------------------------------------------
UPLOAD_FOLDER_PQRSF = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static', 'uploads_pqrsf')
app.config['UPLOAD_FOLDER_PQRSF'] = UPLOAD_FOLDER_PQRSF
os.makedirs(UPLOAD_FOLDER_PQRSF, exist_ok=True)

# -------------------------------------------------------------------------
# 3. MODELO PQRSF COMPLETO
# -------------------------------------------------------------------------
class PQRSF(db.Model):
    __tablename__ = 'PQRSF'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    radicado = db.Column(db.String(50), unique=True, nullable=False)
    tipo = db.Column(db.String(50), nullable=False)
    nombre = db.Column(db.String(120), nullable=True)
    documento = db.Column(db.String(30), nullable=True)
    correo = db.Column(db.String(120), nullable=True)
    telefono = db.Column(db.String(30), nullable=True)
    direccion = db.Column(db.String(200), nullable=True)
    sector = db.Column(db.String(100), nullable=True)
    asunto = db.Column(db.String(200), nullable=True)
    descripcion = db.Column(db.Text, nullable=True)
    archivo_adjunto = db.Column(db.String(255), nullable=True)
    estado = db.Column(db.String(30), default='Recibido')
    fecha_radicacion = db.Column(db.DateTime, default=datetime.now)
    fecha_limite = db.Column(db.DateTime, nullable=True)
    respuesta = db.Column(db.Text, nullable=True)
    funcionario_responsable = db.Column(db.String(120), nullable=True)

# -------------------------------------------------------------------------
# 5. MÓDULO DE PQRSF (RUTAS COMPLETAS)
# -------------------------------------------------------------------------
@app.route('/pqrsf')
def pqrsf():
    try:
        solicitudes = PQRSF.query.order_by(PQRSF.fecha_radicacion.desc()).all()
    except Exception as e:
        db.session.rollback()
        print(f"Error al consultar PQRSF: {e}")
        solicitudes = []
        
    return render_template('pqrsf.html', solicitudes=solicitudes)


@app.route('/pqrsf/radicar', methods=['POST'])
@app.route('/pqrsf/guardar', methods=['POST'])
def radicar_pqrsf():
    try:
        radicado = f"PQRSF-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        tipo = request.form.get('tipo', 'Petición')
        documento = request.form.get('documento', '').strip()
        nombre = request.form.get('nombre', '').strip()
        correo = request.form.get('correo', '').strip()
        telefono = request.form.get('telefono', '').strip()
        direccion = request.form.get('direccion', '').strip()
        sector = request.form.get('sector', '').strip()
        asunto = request.form.get('asunto', '').strip()
        descripcion = request.form.get('descripcion', '').strip()

        # Manejo del archivo adjunto
        file = request.files.get('archivo_soporte')
        nombre_archivo = None
        if file and archivo_permitido(file.filename):
            filename = secure_filename(f"{radicado}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER_PQRSF'], filename))
            nombre_archivo = filename

        # Fecha límite (5 días hábiles aproximadamente / 7 días calendario)
        fecha_radicacion = datetime.now()
        fecha_limite = fecha_radicacion + timedelta(days=7)

        nueva_solicitud = PQRSF(
            radicado=radicado,
            tipo=tipo,
            documento=documento,
            nombre=nombre,
            correo=correo,
            telefono=telefono,
            direccion=direccion,
            sector=sector,
            asunto=asunto,
            descripcion=descripcion,
            archivo_adjunto=nombre_archivo,
            estado='Recibido',
            fecha_radicacion=fecha_radicacion,
            fecha_limite=fecha_limite
        )

        db.session.add(nueva_solicitud)
        db.session.commit()
        flash(f'Solicitud radicado N° {radicado} guardada exitosamente.', 'exito')

    except Exception as e:
        db.session.rollback()
        print(f"Error en radicar_pqrsf: {e}")
        flash(f'Error al registrar solicitud: {e}', 'error')

    return redirect(url_for('pqrsf'))


@app.route('/pqrsf/responder/<int:pqrsf_id>', methods=['POST'])
def responder_pqrsf(pqrsf_id):
    try:
        solicitud = db.session.get(PQRSF, pqrsf_id)
        if solicitud:
            solicitud.estado = request.form.get('estado', 'Resuelto')
            solicitud.funcionario_responsable = request.form.get('funcionario_responsable', '').strip()
            solicitud.respuesta = request.form.get('respuesta', '').strip()
            db.session.commit()
            flash(f'Respuesta guardada para el radicado {solicitud.radicado}.', 'exito')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al guardar respuesta: {e}', 'error')

    return redirect(url_for('pqrsf'))


@app.route('/pqrsf/descargar-respuesta/<int:pqrsf_id>')
def descargar_respuesta_pqrsf(pqrsf_id):
    solicitud = db.session.get(PQRSF, pqrsf_id)
    if not solicitud:
        flash('Solicitud no encontrada.', 'error')
        return redirect(url_for('pqrsf'))
    
    # Genera una vista de impresión/descarga del documento de respuesta
    return render_template('certificado_pago_anticipado_print.html', pago=solicitud)


@app.route('/pqrsf/exportar-excel')
def exportar_pqrsf_excel():
    try:
        solicitudes = PQRSF.query.all()
    except Exception:
        db.session.rollback()
        solicitudes = []

    datos = []
    for s in solicitudes:
        datos.append({
            'Radicado': getattr(s, 'radicado', ''),
            'Tipo': getattr(s, 'tipo', ''),
            'Solicitante': getattr(s, 'nombre', ''),
            'Cédula / Documento': getattr(s, 'documento', ''),
            'Correo': getattr(s, 'correo', ''),
            'Teléfono': getattr(s, 'telefono', ''),
            'Dirección': getattr(s, 'direccion', ''),
            'Sector': getattr(s, 'sector', ''),
            'Asunto': getattr(s, 'asunto', ''),
            'Descripción': getattr(s, 'descripcion', ''),
            'Estado': getattr(s, 'estado', ''),
            'Fecha Radicación': s.fecha_radicacion.strftime('%Y-%m-%d %H:%M') if getattr(s, 'fecha_radicacion', None) else '',
            'Fecha Límite': s.fecha_limite.strftime('%Y-%m-%d') if getattr(s, 'fecha_limite', None) else '',
            'Funcionario Responsable': getattr(s, 'funcionario_responsable', ''),
            'Respuesta': getattr(s, 'respuesta', '')
        })

    df = pd.DataFrame(datos)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='PQRSF')
    output.seek(0)
    
    filename = f"PQRSF_ASUAAASTAB_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(
        output,
        download_name=filename,
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
# -------------------------------------------------------------------------
# 6. MÓDULO DE MATRÍCULAS
# -------------------------------------------------------------------------
@app.route('/matriculas')
def matriculas():
    usuarios = UsuarioMatricula.query.order_by(UsuarioMatricula.fecha_compra.desc()).all()
    total_usuarios = len(usuarios)
    total_activos = sum(1 for u in usuarios if u.estado_matricula == 'ACTIVO')
    total_inactivos = sum(1 for u in usuarios if u.estado_matricula == 'INACTIVO')
    total_suspendidos = sum(1 for u in usuarios if u.estado_matricula == 'SUSPENDIDO')
    return render_template(
        'matriculas.html',
        usuarios=usuarios,
        total_usuarios=total_usuarios,
        total_activos=total_activos,
        total_inactivos=total_inactivos,
        total_suspendidos=total_suspendidos
    )

@app.route('/matriculas/cambiar-estado/<int:user_id>', methods=['POST'])
def cambiar_estado_matricula(user_id):
    usuario = db.session.get(UsuarioMatricula, user_id)
    if usuario:
        nuevo_estado = request.form.get('estado_matricula')
        if nuevo_estado in ['ACTIVO', 'INACTIVO', 'SUSPENDIDO']:
            usuario.estado_matricula = nuevo_estado
            db.session.commit()
            flash(f'Estado del usuario {usuario.codigo} actualizado a {nuevo_estado}.', 'exito')
    return redirect(url_for('matriculas'))

@app.route('/matriculas/guardar', methods=['POST'])
def guardar_matricula():
    codigo = request.form.get('codigo', '').strip()
    nombre = request.form.get('nombre', '').strip()
    cedula = request.form.get('cedula', '').strip()
    estado_matricula = request.form.get('estado_matricula', 'ACTIVO')
    fecha_compra = request.form.get('fecha_compra', datetime.now().strftime('%Y-%m-%d'))
    nota = request.form.get('nota', '').strip()

    if UsuarioMatricula.query.filter_by(codigo=codigo).first():
        flash(f'El código de usuario "{codigo}" ya se encuentra registrado.', 'error')
        return redirect(url_for('matriculas'))

    file_doc = request.files.get('documento_adjunto')
    nombre_doc = None
    if file_doc and archivo_permitido(file_doc.filename):
        filename = secure_filename(f"doc_{codigo}_{file_doc.filename}")
        file_doc.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        nombre_doc = filename

    file_foto = request.files.get('foto_ubicacion')
    nombre_foto = None
    if file_foto and archivo_permitido(file_foto.filename):
        filename = secure_filename(f"foto_{codigo}_{file_foto.filename}")
        file_foto.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        nombre_foto = filename

    nuevo_usuario = UsuarioMatricula(
        codigo=codigo,
        nombre=nombre,
        cedula=cedula,
        estado_matricula=estado_matricula,
        fecha_compra=fecha_compra,
        nota=nota,
        documento_adjunto=nombre_doc,
        foto_ubicacion=nombre_foto
    )

    db.session.add(nuevo_usuario)
    db.session.commit()
    flash('Usuario matriculado exitosamente.', 'exito')
    return redirect(url_for('matriculas'))

@app.route('/matriculas/editar/<int:user_id>', methods=['POST'])
def editar_matricula(user_id):
    usuario = db.session.get(UsuarioMatricula, user_id)
    if not usuario:
        flash('El usuario solicitado no existe.', 'error')
        return redirect(url_for('matriculas'))
    
    usuario.nombre = request.form.get('nombre', '').strip()
    usuario.cedula = request.form.get('cedula', '').strip()
    usuario.estado_matricula = request.form.get('estado_matricula', 'ACTIVO')
    usuario.fecha_compra = request.form.get('fecha_compra')
    usuario.nota = request.form.get('nota', '').strip()

    file_doc = request.files.get('documento_adjunto')
    if file_doc and archivo_permitido(file_doc.filename):
        filename = secure_filename(f"doc_{usuario.codigo}_{file_doc.filename}")
        file_doc.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        usuario.documento_adjunto = filename

    file_foto = request.files.get('foto_ubicacion')
    if file_foto and archivo_permitido(file_foto.filename):
        filename = secure_filename(f"foto_{usuario.codigo}_{file_foto.filename}")
        file_foto.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        usuario.foto_ubicacion = filename

    db.session.commit()
    flash('Información de matrícula actualizada correctamente.', 'exito')
    return redirect(url_for('matriculas'))

@app.route('/matriculas/eliminar/<int:user_id>', methods=['POST'])
def eliminar_matricula(user_id):
    usuario = db.session.get(UsuarioMatricula, user_id)
    if usuario:
        db.session.delete(usuario)
        db.session.commit()
        flash('Usuario eliminado de la matrícula correctamente.', 'exito')
    return redirect(url_for('matriculas'))

# -------------------------------------------------------------------------
# 7. MÓDULO DE PAGOS ANTICIPADOS
# -------------------------------------------------------------------------
@app.route('/pagos-anticipados')
def pagos_anticipados():
    pagos = PagoAnticipado.query.all()
    total_recaudado = sum(p.valor_total or 0.0 for p in pagos)
    total_saldo_disponible = sum(p.saldo_pendiente or 0.0 for p in pagos)
    total_aplicado = total_recaudado - total_saldo_disponible
    total_cargo_mes = obtener_cargo_mes_db()
    consumido_es_cero = (total_cargo_mes == 0.0)
    return render_template(
        'pagos_anticipados.html',
        pagos=pagos,
        total_recaudado=total_recaudado,
        total_saldo_disponible=total_saldo_disponible,
        total_aplicado=total_aplicado,
        total_cargo_mes=total_cargo_mes,
        consumido_es_cero=consumido_es_cero
    )

@app.route('/pagos-anticipados/reiniciar-consumido', methods=['POST'])
def reiniciar_consumido_mes():
    guardar_cargo_mes_db(0.0)
    return redirect(url_for('pagos_anticipados')) 

@app.route('/pagos-anticipados/guardar', methods=['POST'])
def guardar_pago_anticipado():
    nombre_usuario = request.form.get('nombre_usuario')
    documento = request.form.get('cedula')
    codigo_usuario = request.form.get('codigo_usuario')
    direccion_predio = request.form.get('direccion_predio', 'N/A')
    
    numero_meses = int(request.form.get('numero_meses') or 1)
    mes_inicio = request.form.get('mes_inicio')
    mes_final = request.form.get('mes_final') or mes_inicio
    valor_total = float(request.form.get('valor_total') or 0.0)
    valor_unitario = valor_total / numero_meses if numero_meses > 0 else 0.0
    
    nuevo_pago = PagoAnticipado(
        nombre_usuario=nombre_usuario,
        documento=documento,
        codigo_usuario=codigo_usuario,
        direccion_predio=direccion_predio,
        mes_inicio=mes_inicio,
        mes_final=mes_final,
        numero_meses=numero_meses,
        meses_restantes=numero_meses,
        valor_unitario=valor_unitario,
        valor_total=valor_total,
        saldo_pendiente=valor_total
    )
    db.session.add(nuevo_pago)
    db.session.commit()
    flash('Pago anticipado registrado correctamente.', 'exito')
    return redirect(url_for('pagos_anticipados'))

@app.route('/pagos-anticipados/descontar/<int:id>', methods=['POST'])
def descontar_pago_anticipado(id):
    pago = db.session.get(PagoAnticipado, id)
    if pago and pago.meses_restantes > 0 and pago.saldo_pendiente > 0:
        pago.saldo_pendiente -= pago.valor_unitario
        if pago.saldo_pendiente < 0:
            pago.saldo_pendiente = 0.0
        pago.meses_restantes -= 1
        db.session.commit()
    return redirect(url_for('pagos_anticipados'))

@app.route('/pagos-anticipados/cargar-mes', methods=['POST'])
def cargar_mes_anticipado():
    target = request.form.get('target_usuario')
    if target == 'TODOS':
        pagos = PagoAnticipado.query.filter(PagoAnticipado.meses_restantes > 0).all()
    else:
        pagos = PagoAnticipado.query.filter(PagoAnticipado.id == int(target), PagoAnticipado.meses_restantes > 0).all()
    
    cargo_procesado_este_mes = 0.0
    for p in pagos:
        if p.meses_restantes > 0:
            cargo_procesado_este_mes += p.valor_unitario
            p.meses_restantes -= 1
            p.saldo_pendiente = p.valor_unitario * p.meses_restantes

    cargo_actual_db = obtener_cargo_mes_db()
    guardar_cargo_mes_db(cargo_actual_db + cargo_procesado_este_mes)
    
    db.session.commit()
    flash('Cargo mensual procesado correctamente.', 'exito')
    return redirect(url_for('pagos_anticipados'))

@app.route('/pagos-anticipados/eliminar/<int:pago_id>', methods=['POST'])
def eliminar_pago_anticipado(pago_id):
    pago = db.session.get(PagoAnticipado, pago_id)
    if pago:
        db.session.delete(pago)
        db.session.commit()
        flash('Registro de pago anticipado eliminado exitosamente.', 'exito')
    return redirect(url_for('pagos_anticipados'))

@app.route('/pagos-anticipados/certificado/<int:pago_id>')
def certificado_pago_anticipado(pago_id):
    pago = db.session.get(PagoAnticipado, pago_id)
    if not pago:
        flash('Registro no encontrado.', 'error')
        return redirect(url_for('pagos_anticipados'))
    hoy = datetime.now()
    return render_template(
        'certificado_pago_anticipado_print.html',
        pago=pago,
        dia_actual=hoy.day,
        mes_actual=MESES[hoy.month - 1],
        ano_actual=hoy.year
    )

@app.route('/pagos-anticipados/editar/<int:pago_id>', methods=['POST'])
def editar_pago_anticipado(pago_id):
    pago = db.session.get(PagoAnticipado, pago_id)
    if not pago:
        flash('Registro no encontrado.', 'error')
        return redirect(url_for('pagos_anticipados'))
    
    pago.nombre_usuario = request.form.get('nombre_usuario')
    pago.documento = request.form.get('cedula')
    pago.codigo_usuario = request.form.get('codigo_usuario')
    
    numero_meses = int(request.form.get('numero_meses') or 1)
    valor_total = float(request.form.get('valor_total') or 0.0)
    meses_restantes = int(request.form.get('meses_restantes') or numero_meses)
    
    pago.mes_inicio = request.form.get('mes_inicio')
    pago.mes_final = request.form.get('mes_final')
    pago.numero_meses = numero_meses
    pago.valor_total = valor_total
    pago.valor_unitario = valor_total / numero_meses if numero_meses > 0 else 0.0
    pago.meses_restantes = meses_restantes
    pago.saldo_pendiente = pago.valor_unitario * meses_restantes
    
    db.session.commit()
    flash('Registro de pago anticipado actualizado correctamente.', 'exito')
    return redirect(url_for('pagos_anticipados'))

@app.route('/pagos-anticipados/exportar-excel')
def exportar_excel_pagos():
    pagos = PagoAnticipado.query.all()
    datos = []
    for p in pagos:
        datos.append({
            'Usuario': p.nombre_usuario,
            'Cédula / Documento': p.documento,
            'Código Predio': p.codigo_usuario,
            'Dirección Predio': p.direccion_predio or 'N/A',
            'Mes Inicio': p.mes_inicio,
            'Mes Final': p.mes_final,
            'Meses Cancelados': p.numero_meses,
            'Meses Restantes': p.meses_restantes,
            'Valor Unitario ($)': p.valor_unitario,
            'Valor Total ($)': p.valor_total,
            'Saldo Pendiente ($)': p.saldo_pendiente,
            'Fecha Registro': p.fecha_registro.strftime('%Y-%m-%d %H:%M') if p.fecha_registro else ''
        })
    df = pd.DataFrame(datos)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Pagos Anticipados')
    output.seek(0)
    return send_file(
        output,
        download_name='Pagos_Anticipados_ASUAAASTAB.xlsx',
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

# -------------------------------------------------------------------------
# 8. MÓDULO DE INVENTARIO
# -------------------------------------------------------------------------
@app.route('/inventario')
def inventario():
    productos = Producto.query.all()
    return render_template('inventario.html', productos=productos)

@app.route('/inventario/crear', methods=['POST'])
def crear_producto():
    nombre = request.form.get('nombre')
    categoria = request.form.get('categoria')
    cantidad = int(request.form.get('cantidad', 0))
    unidad = request.form.get('unidad', 'Unidades')
    ubicacion = request.form.get('ubicacion')

    nuevo_producto = Producto(
        nombre=nombre,
        categoria=categoria,
        cantidad=cantidad,
        unidad=unidad,
        ubicacion=ubicacion
    )
    db.session.add(nuevo_producto)
    db.session.commit()
    flash('Producto registrado exitosamente.', 'success')
    return redirect(url_for('inventario'))

@app.route('/inventario/movimiento/<int:prod_id>', methods=['POST'])
def registrar_movimiento(prod_id):
    producto = Producto.query.get_or_404(prod_id)
    tipo = request.form.get('tipo')
    cantidad = int(request.form.get('cantidad', 0))
    responsable = request.form.get('responsable')
    motivo = request.form.get('motivo')

    if tipo == 'ENTRADA':
        producto.cantidad += cantidad
    elif tipo == 'SALIDA':
        if producto.cantidad < cantidad:
            flash('No hay suficiente stock para realizar esta salida.', 'danger')
            return redirect(url_for('inventario'))
        producto.cantidad -= cantidad

    nuevo_movimiento = MovimientoInventario(
        producto_id=producto.id,
        tipo=tipo,
        cantidad=cantidad,
        responsable=responsable,
        motivo=motivo
    )

    db.session.add(nuevo_movimiento)
    db.session.commit()
    flash('Movimiento registrado correctamente.', 'success')
    return redirect(url_for('inventario'))

@app.route('/inventario/editar/<int:prod_id>', methods=['POST'])
def editar_producto(prod_id):
    producto = Producto.query.get_or_404(prod_id)
    producto.nombre = request.form.get('nombre')
    producto.categoria = request.form.get('categoria')
    producto.unidad = request.form.get('unidad')
    producto.ubicacion = request.form.get('ubicacion')
    db.session.commit()
    flash('Producto actualizado correctamente.', 'success')
    return redirect(url_for('inventario'))

@app.route('/inventario/eliminar/<int:prod_id>', methods=['POST'])
def eliminar_producto(prod_id):
    producto = Producto.query.get_or_404(prod_id)
    db.session.delete(producto)
    db.session.commit()
    flash('Producto eliminado del inventario.', 'success')
    return redirect(url_for('inventario'))

@app.route('/inventario/historial/<int:prod_id>')
def historial_producto(prod_id):
    producto = Producto.query.get_or_404(prod_id)
    movimientos = MovimientoInventario.query.filter_by(producto_id=prod_id).order_by(MovimientoInventario.fecha.desc()).all()
    return render_template('historial_producto.html', producto=producto, movimientos=movimientos)

@app.route('/inventario/exportar-excel')
def exportar_inventario_excel():
    productos = Producto.query.all()
    datos = []
    for p in productos:
        datos.append({
            'ID / Código': p.id,
            'Nombre de Insumo / Producto': p.nombre,
            'Categoría': p.categoria or 'N/A',
            'Stock / Cantidad': p.cantidad,
            'Unidad de Medida': p.unidad,
            'Ubicación': p.ubicacion or 'N/A'
        })
    df = pd.DataFrame(datos)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Inventario')
    output.seek(0)
    filename = f"Inventario_ASUAAASTAB_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(output, download_name=filename, as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

# -------------------------------------------------------------------------
# 9. MÓDULO DE DOCUMENTOS
# -------------------------------------------------------------------------
@app.route('/documentos')
def documentos():
    tipos_documentos = [
        {
            'id': 'documento_equivalente',
            'titulo': 'Documento Equivalente',
            'descripcion': 'Generación de documento equivalente a la factura para operaciones con no obligados a expedir factura.',
            'icono': '📄'
        },
        {
            'id': 'factura_venta',
            'titulo': 'Factura de Venta',
            'descripcion': 'Emisión de facturas por cobro de servicios, venta de insumos o conceptos varios.',
            'icono': '🧾'
        },
        {
            'id': 'certificacion_laboral',
            'titulo': 'Certificación Laboral',
            'descripcion': 'Expedición de certificados para colaboradores, contratistas y personal administrativo.',
            'icono': '💼'
        },
        {
            'id': 'certificado_servicios',
            'titulo': 'Certificado de la Prestación de los Servicios de Acueducto, Aseo y Alcantarillado',
            'descripcion': 'Constancia formal de prestación y estado del servicio para usuarios o predios de la comunidad.',
            'icono': '🚰'
        }
    ]
    return render_template('documentos.html', documentos=tipos_documentos)

@app.route('/documentos/factura-venta', methods=['GET', 'POST'])
def factura_venta():
    if request.method == 'POST':
        consecutivo = obtener_siguiente_consecutivo_factura()
        return render_template('factura_venta_print.html', consecutivo=consecutivo)
    consecutivo_vista = ver_siguiente_consecutivo_factura()
    return render_template('factura_venta_form.html', consecutivo=consecutivo_vista)

@app.route('/documentos/certificado-servicios', methods=['GET', 'POST'])
def certificado_servicios():
    if request.method == 'POST':
        return render_template('certificado_servicios_print.html')
    return render_template('certificado_servicios_form.html')

@app.route('/documentos/certificacion-laboral', methods=['GET', 'POST'])
def certificacion_laboral():
    if request.method == 'POST':
        hoy = datetime.now()

        def fmt_fecha(fecha_str):
            if not fecha_str:
                return ""
            try:
                f = datetime.strptime(fecha_str, "%Y-%m-%d")
                return f"{f.day} de {MESES[f.month - 1]} de {f.year}"
            except ValueError:
                return fecha_str

        estado_laboral = request.form.get('estado_laboral')
        fecha_fin_raw = request.form.get('fecha_fin')
        fecha_fin_txt = fmt_fecha(fecha_fin_raw) if estado_laboral == 'FINALIZADO' else ''

        datos = {
            'trato': request.form.get('trato'),
            'nombre_empleado': request.form.get('nombre_empleado', '').strip(),
            'tipo_doc': request.form.get('tipo_doc'),
            'numero_doc': request.form.get('numero_doc', '').strip(),
            'cargo': request.form.get('cargo', '').strip(),
            'estado_laboral': estado_laboral,
            'fecha_inicio': fmt_fecha(request.form.get('fecha_inicio')),
            'fecha_fin': fecha_fin_txt,
            'funciones': request.form.get('funciones', '').strip(),
            'nombre_firmante': request.form.get('nombre_firmante', '').strip() or 'ANGIE RUEDA ERAZO',
            'cargo_firmante': request.form.get('cargo_firmante', '').strip() or 'Representante Legal',
            'dia_exp': hoy.day,
            'mes_exp': MESES[hoy.month - 1],
            'anio_exp': hoy.year
        }
        return render_template('certificacion_laboral_print.html', datos=datos)

    return render_template('certificacion_laboral_form.html')

@app.route('/documentos/documento-equivalente', methods=['GET', 'POST'])
def documento_equivalente():
    if request.method == 'POST':
        consecutivo = obtener_siguiente_consecutivo()
        fecha_str = request.form.get('fecha', datetime.now().strftime('%Y-%m-%d'))
        
        try:
            f_dt = datetime.strptime(fecha_str, '%Y-%m-%d')
            dia, mes, anio = f_dt.strftime('%d'), f_dt.strftime('%m'), f_dt.strftime('%Y')
            fecha_formateada = f"{dia}/{mes}/{anio}"
        except ValueError:
            f_hoy = datetime.now()
            dia, mes, anio = f_hoy.strftime('%d'), f_hoy.strftime('%m'), f_hoy.strftime('%Y')
            fecha_formateada = f"{dia}/{mes}/{anio}"

        beneficiario = request.form.get('beneficiario', '').strip()
        documento = request.form.get('documento', '').strip()
        direccion = request.form.get('direccion', '').strip()

        conceptos = request.form.getlist('concepto[]')
        v_unitarios = request.form.getlist('v_unitario[]')
        totales = request.form.getlist('total[]')

        items = []
        subtotal = 0.0

        for c, vu, t in zip(conceptos, v_unitarios, totales):
            c_val = c.strip()
            t_val = limpiar_monto(t)
            vu_val = limpiar_monto(vu)

            if c_val or t_val > 0:
                items.append({
                    'concepto': c_val,
                    'v_unitario': vu_val if vu_val > 0 else None,
                    'total': t_val if t_val > 0 else None
                })
                subtotal += t_val

        while len(items) < 6:
            items.append({'concepto': '', 'v_unitario': None, 'total': None})

        retefuente = limpiar_monto(request.form.get('retefuente'))
        reteica = limpiar_monto(request.form.get('reteica'))
        neto = subtotal - retefuente - reteica

        def fmt_cop(val):
            if val is None or val == '':
                return ''
            return f"$ {val:,.0f}".replace(',', '.')

        datos = {
            'consecutivo': consecutivo,
            'dia': dia,
            'mes': mes,
            'anio': anio,
            'fecha_formateada': fecha_formateada,
            'beneficiario': beneficiario,
            'documento': documento,
            'direccion': direccion,
            'lista_items': items,
            'subtotal': fmt_cop(subtotal),
            'retefuente': fmt_cop(retefuente) if retefuente > 0 else '',
            'reteica': fmt_cop(reteica) if reteica > 0 else '',
            'neto': fmt_cop(neto),
            'fmt_cop': fmt_cop
        }
        return render_template('documento_equivalente_print.html', datos=datos)

    consecutivo_vista = ver_siguiente_consecutivo()
    return render_template('documento_equivalente_form.html', consecutivo=consecutivo_vista, datetime=datetime.now().strftime('%Y-%m-%d'))

# -------------------------------------------------------------------------
# 10. EJECUCIÓN
# -------------------------------------------------------------------------
if __name__ == '__main__':
    app.run(debug=True)