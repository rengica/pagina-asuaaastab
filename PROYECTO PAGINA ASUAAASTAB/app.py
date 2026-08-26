import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = 'clave_secreta_asuaaastab'

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///inventario.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- MANEJO DE CONSECUTIVO AUTOMÁTICO ---
CONSECUTIVO_FILE = 'consecutivo.txt'

def ver_siguiente_consecutivo():
    """Lee el consecutivo sin incrementarlo (para mostrar en el formulario)."""
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
    """Incrementa y guarda el consecutivo (al procesar la información)."""
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

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
]

# --- MODELOS DE BASE DE DATOS ---
class Producto(db.Model):
    __tablename__ = 'productos'
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    stock_actual = db.Column(db.Float, default=0.0)
    stock_minimo = db.Column(db.Float, default=5.0)
    unidad_medida = db.Column(db.String(20), nullable=False)
    estado = db.Column(db.String(20), default='Bueno')
    movimientos = db.relationship('Movimiento', backref='producto', lazy=True)

class Movimiento(db.Model):
    __tablename__ = 'movimientos'
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)
    cantidad = db.Column(db.Float, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    responsable = db.Column(db.String(100), nullable=False)
    observacion = db.Column(db.String(255), nullable=True)

with app.app_context():
    db.create_all()

# --- RUTAS DE NAVEGACIÓN ---
@app.route('/')
def inicio():
    return render_template('index.html')

# --- MÓDULO DE INVENTARIO ---
@app.route('/inventario')
def inventario():
    productos = Producto.query.all()
    return render_template('inventario.html', productos=productos)

@app.route('/inventario/producto/nuevo', methods=['GET', 'POST'])
def crear_producto():
    if request.method == 'POST':
        codigo = request.form.get('codigo').strip()
        nombre = request.form.get('nombre').strip()
        stock_inicial = float(request.form.get('stock_inicial') or 0.0)
        stock_minimo = float(request.form.get('stock_minimo') or 5.0)
        unidad_medida = request.form.get('unidad_medida').strip()
        estado = request.form.get('estado')

        prod_existente = Producto.query.filter_by(codigo=codigo).first()
        if prod_existente:
            flash(f'Error: El código "{codigo}" ya está registrado.', 'error')
            return redirect(url_for('crear_producto'))

        nuevo_prod = Producto(
            codigo=codigo,
            nombre=nombre,
            stock_actual=stock_inicial,
            stock_minimo=stock_minimo,
            unidad_medida=unidad_medida,
            estado=estado
        )

        db.session.add(nuevo_prod)
        db.session.commit()

        flash(f'Producto "{nombre}" creado exitosamente.', 'exito')
        return redirect(url_for('inventario'))

    return render_template('nuevo_producto.html')

@app.route('/inventario/movimiento', methods=['GET', 'POST'])
def registrar_movimiento():
    if request.method == 'POST':
        producto_id = request.form.get('producto_id')
        tipo = request.form.get('tipo')
        cantidad = float(request.form.get('cantidad'))
        responsable = request.form.get('responsable')
        observacion = request.form.get('observacion')

        producto = Producto.query.get(producto_id)

        if not producto:
            flash('Error: El producto no existe.', 'error')
            return redirect(url_for('registrar_movimiento'))

        if tipo == 'SALIDA':
            if producto.stock_actual < cantidad:
                flash(f'Error: Stock insuficiente. Hay {producto.stock_actual} {producto.unidad_medida} disponibles.', 'error')
                return redirect(url_for('registrar_movimiento'))
            producto.stock_actual -= cantidad
        elif tipo == 'ENTRADA':
            producto.stock_actual += cantidad

        nuevo_movimiento = Movimiento(
            producto_id=producto.id,
            tipo=tipo,
            cantidad=cantidad,
            responsable=responsable,
            observacion=observacion
        )

        db.session.add(nuevo_movimiento)
        db.session.commit()
        flash('Movimiento registrado con éxito.', 'exito')
        return redirect(url_for('inventario'))

    productos = Producto.query.all()
    return render_template('movimiento.html', productos=productos)

# --- MÓDULO DE DOCUMENTOS ---
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
            'nombre_empleado': request.form.get('nombre_empleado').strip(),
            'tipo_doc': request.form.get('tipo_doc'),
            'numero_doc': request.form.get('numero_doc').strip(),
            'cargo': request.form.get('cargo').strip(),
            'estado_laboral': estado_laboral,
            'fecha_inicio': fmt_fecha(request.form.get('fecha_inicio')),
            'fecha_fin': fecha_fin_txt,
            'funciones': request.form.get('funciones').strip(),
            'nombre_firmante': request.form.get('nombre_firmante').strip() or 'ANGIE RUEDA ERAZO',
            'cargo_firmante': request.form.get('cargo_firmante').strip() or 'Representante Legal',
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
            dia = f_dt.strftime('%d')
            mes = f_dt.strftime('%m')
            anio = f_dt.strftime('%Y')
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
            try:
                t_val = float(t) if t else 0.0
            except ValueError:
                t_val = 0.0

            try:
                vu_val = float(vu) if vu else 0.0
            except ValueError:
                vu_val = 0.0

            if c_val or t_val > 0:
                items.append({
                    'concepto': c_val,
                    'v_unitario': vu_val if vu_val > 0 else None,
                    'total': t_val if t_val > 0 else None
                })
                subtotal += t_val

        while len(items) < 6:
            items.append({'concepto': '', 'v_unitario': None, 'total': None})

        try:
            retefuente = float(request.form.get('retefuente') or 0.0)
        except ValueError:
            retefuente = 0.0

        try:
            reteica = float(request.form.get('reteica') or 0.0)
        except ValueError:
            reteica = 0.0

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

    # Carga del formulario vía GET: pre-diligencia el próximo número disponible
    consecutivo_vista = ver_siguiente_consecutivo()
    return render_template('documento_equivalente_form.html', consecutivo=consecutivo_vista, datetime=datetime.now().strftime('%Y-%m-%d'))

# Ejemplo de función independiente para el consecutivo de facturas
def obtener_siguiente_consecutivo_factura():
    # Si usas un archivo de texto o base de datos, cámbialo aquí para apuntar al contador de facturas.
    # Ejemplo básico usando un archivo 'consecutivo_factura.txt':
    try:
        if os.path.exists('consecutivo_factura.txt'):
            with open('consecutivo_factura.txt', 'r') as f:
                actual = int(f.read().strip())
        else:
            actual = 0
        
        siguiente = actual + 1
        with open('consecutivo_factura.txt', 'w') as f:
            f.write(str(siguiente))
            
        return f"{siguiente:03d}"  # Formato con ceros a la izquierda (ej. 001, 002)
    except Exception:
        return "001"

def ver_siguiente_consecutivo_factura():
    try:
        if os.path.exists('consecutivo_factura.txt'):
            with open('consecutivo_factura.txt', 'r') as f:
                actual = int(f.read().strip())
            return f"{(actual + 1):03d}"
    except Exception:
        pass
    return "001"
@app.route('/documentos/factura-venta', methods=['GET', 'POST'])
def factura_venta():
    if request.method == 'POST':
        # AQUÍ ESTABLECEMOS EL CONSECUTIVO INDEPENDIENTE DE FACTURA
        consecutivo = obtener_siguiente_consecutivo_factura()
        
        fecha_str = request.form.get('fecha', datetime.now().strftime('%Y-%m-%d'))
        
        try:
            f_dt = datetime.strptime(fecha_str, '%Y-%m-%d')
            dia, mes, anio = f_dt.strftime('%d'), f_dt.strftime('%m'), f_dt.strftime('%Y')
        except ValueError:
            f_hoy = datetime.now()
            dia, mes, anio = f_hoy.strftime('%d'), f_hoy.strftime('%m'), f_hoy.strftime('%Y')

        cliente = request.form.get('cliente', '').strip()
        documento = request.form.get('documento', '').strip()
        direccion = request.form.get('direccion', 'El Tablón de Gómez').strip()

        cantidades = request.form.getlist('cantidad[]')
        conceptos = request.form.getlist('concepto[]')
        v_unitarios = request.form.getlist('v_unitario[]')

        items = []
        subtotal = 0.0

        def fmt_cop(val):
            if val is None or val == '' or val == 0:
                return ''
            return f"$ {val:,.0f}".replace(',', '.')

        for i, (cant, conc, vu) in enumerate(zip(cantidades, conceptos, v_unitarios)):
            c_txt = conc.strip()
            try:
                cant_val = float(cant) if cant else 0.0
            except ValueError:
                cant_val = 0.0

            try:
                vu_val = float(vu) if vu else 0.0
            except ValueError:
                vu_val = 0.0

            total_item = (cant_val * vu_val) if (cant_val and vu_val) else (vu_val if vu_val else 0.0)

            if c_txt or total_item > 0:
                cant_disp = int(cant_val) if cant_val.is_integer() and cant_val > 0 else (cant_val if cant_val > 0 else '')
                items.append({
                    'cantidad': cant_disp,
                    'concepto': c_txt,
                    'v_unitario': fmt_cop(vu_val),
                    'total': fmt_cop(total_item),
                    'destacar_total': True if (i == 0 and total_item > 0) else False
                })
                subtotal += total_item

        while len(items) < 8:
            items.append({
                'cantidad': '',
                'concepto': '',
                'v_unitario': '',
                'total': '',
                'destacar_total': False
            })

        try:
            retefuente = float(request.form.get('retefuente') or 0.0)
        except ValueError:
            retefuente = 0.0

        try:
            reteica = float(request.form.get('reteica') or 0.0)
        except ValueError:
            reteica = 0.0

        neto = subtotal - retefuente - reteica

        datos = {
            'consecutivo': consecutivo,
            'dia': dia,
            'mes': mes,
            'anio': anio,
            'fecha_formateada': f"{dia}/{mes}/{anio}",
            'cliente': cliente,
            'documento': documento,
            'direccion': direccion,
            'lista_items': items,
            'subtotal': fmt_cop(subtotal),
            'retefuente': fmt_cop(retefuente),
            'reteica': fmt_cop(reteica),
            'neto': fmt_cop(neto)
        }
        return render_template('factura_venta_print.html', datos=datos)

    # Vista previa del consecutivo de factura independiente
    consecutivo_vista = ver_siguiente_consecutivo_factura()
    return render_template('factura_venta_form.html', consecutivo=consecutivo_vista, datetime=datetime.now().strftime('%Y-%m-%d'))

@app.route('/documentos/certificado-servicios', methods=['GET', 'POST'])
def certificado_servicios():
    if request.method == 'POST':
        trato_usuario = request.form.get('trato_usuario', 'El señor').strip()
        nombre_usuario = request.form.get('nombre_usuario', '').strip()
        documento = request.form.get('documento', '').strip()
        codigo_usuario = request.form.get('codigo_usuario', '').strip()
        direccion_predio = request.form.get('direccion_predio', '').strip()
        barrio = request.form.get('barrio', 'Centro').strip()
        estado_servicio = request.form.get('estado_servicio', 'ACTIVO Y A PAZ Y SALVO').strip()
        destinatario = request.form.get('destinatario', 'A QUIEN INTERESE').strip()
        fecha_expedicion_str = request.form.get('fecha_expedicion', datetime.now().strftime('%Y-%m-%d'))
        
        # Datos del Firmante
        nombre_firmante = request.form.get('nombre_firmante', 'ANGIE RUEDA ERAZO').strip()
        cargo_firmante = request.form.get('cargo_firmante', 'Representante Legal').strip()

        # Determinación de género y concordancia gramatical
        es_femenino = (trato_usuario == 'La señora')

        try:
            f_dt = datetime.strptime(fecha_expedicion_str, '%Y-%m-%d')
            meses = [
                'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'
            ]
            fecha_texto = f"a los {f_dt.day} días del mes de {meses[f_dt.month - 1]} de {f_dt.year}"
        except Exception:
            fecha_texto = datetime.now().strftime('%d/%m/%Y')

        datos = {
            'trato_usuario': trato_usuario,
            'nombre_usuario': nombre_usuario,
            'documento': documento,
            'codigo_usuario': codigo_usuario,
            'direccion_predio': direccion_predio,
            'barrio': barrio,
            'estado_servicio': estado_servicio,
            'destinatario': destinatario,
            'fecha_texto': fecha_texto,
            'nombre_firmante': nombre_firmante,
            'cargo_firmante': cargo_firmante,
            # Gramática dinámica
            'identificado': 'identificada' if es_femenino else 'identificado',
            'matriculado': 'matriculada' if es_femenino else 'matriculado',
            'vinculado': 'vinculada' if es_femenino else 'vinculado',
            'usuario_word': 'usuaria' if es_femenino else 'usuario',
            'el_usuario': 'la usuaria' if es_femenino else 'el usuario',
            'del_interesado': 'de la interesada' if es_femenino else 'del interesado'
        }
        return render_template('certificado_servicios_print.html', datos=datos)

    return render_template('certificado_servicios_form.html', datetime=datetime.now().strftime('%Y-%m-%d'))

# --- OTROS MÓDULOS ---
@app.route('/contratacion')
def contratacion():
    return "<h1>Módulo de Contratación</h1><p>En construcción...</p>"

@app.route('/pqrsf')
def pqrsf():
    return "<h1>Módulo de PQRSF</h1><p>En construcción...</p>"

@app.route('/matriculas')
def matriculas():
    return "<h1>Módulo de Matrículas</h1><p>En construcción...</p>"

if __name__ == '__main__':
    app.run(debug=True)