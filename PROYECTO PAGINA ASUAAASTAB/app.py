import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = 'clave_secreta_asuaaastab'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///inventario.db'
# Obtener DATABASE_URL del servidor o usar SQLite local por defecto
database_url = os.environ.get('DATABASE_URL', 'sqlite:///inventario.db')

# Corrección de compatibilidad para Render/Heroku (SQLAlchemy requiere 'postgresql://' en lugar de 'postgres://')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url

# ===========================================================================
# FILTRO DE MONEDA EN JINJA (COP)
# ===========================================================================
def cop_filter(val):
    try:
        if val is None:
            val = 0
        return f"$ {float(val):,.0f}".replace(',', '.')
    except (ValueError, TypeError):
        return "$ 0"

app.jinja_env.filters['cop'] = cop_filter

db = SQLAlchemy(app)

# ===========================================================================
# AUXILIARES, MONEDA Y MANEJO DE CONSECUTIVOS
# ===========================================================================
CONSECUTIVO_FILE = 'consecutivo.txt'
CONSECUTIVO_FACTURA_FILE = 'consecutivo_factura.txt'

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
]

def limpiar_monto(val):
    """Limpia textos con formato de moneda ($ 15.000, 15.000, etc.) y los convierte a float."""
    if val is None:
        return 0.0
    val_str = str(val).strip()
    if not val_str:
        return 0.0

    # Quitar signo de pesos y espacios
    val_str = val_str.replace('$', '').replace(' ', '')

    # Manejar separadores de miles y decimales en formato colombiano/latino
    if '.' in val_str and ',' in val_str:
        val_str = val_str.replace('.', '').replace(',', '.')
    elif '.' in val_str:
        parts = val_str.split('.')
        # Si las partes despues del punto tienen 3 digitos, es separador de miles
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

# ===========================================================================
# MODELOS DE BASE DE DATOS
# ===========================================================================
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
    fecha = db.Column(db.DateTime, default=datetime.now)
    responsable = db.Column(db.String(100), nullable=False)
    observacion = db.Column(db.String(255), nullable=True)

class PagoAnticipado(db.Model):
    __tablename__ = 'pagos_anticipados'
    id = db.Column(db.Integer, primary_key=True)
    nombre_usuario = db.Column(db.String(120), nullable=False)
    documento = db.Column(db.String(20), nullable=False)
    codigo_usuario = db.Column(db.String(30), nullable=False)
    direccion_predio = db.Column(db.String(200), nullable=False)
    mes_inicio = db.Column(db.String(7), nullable=False)  # YYYY-MM
    mes_final = db.Column(db.String(7), nullable=False)   # YYYY-MM
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

with app.app_context():
    db.create_all()

# ===========================================================================
# RUTAS DE NAVEGACIÓN PRINCIPAL
# ===========================================================================
@app.route('/')
def inicio():
    return render_template('index.html')

@app.route('/contratacion')
def contratacion():
    return "<h1>Módulo de Contratación</h1><p>En construcción...</p>"

@app.route('/pqrsf')
def pqrsf():
    return "<h1>Módulo de PQRSF</h1><p>En construcción...</p>"

@app.route('/matriculas')
def matriculas():
    return "<h1>Módulo de Matrículas</h1><p>En construcción...</p>"

# ===========================================================================
# MÓDULO DE INVENTARIO
# ===========================================================================
@app.route('/inventario')
def inventario():
    productos = Producto.query.all()
    return render_template('inventario.html', productos=productos)

@app.route('/inventario/producto/nuevo', methods=['GET', 'POST'])
def crear_producto():
    if request.method == 'POST':
        codigo = request.form.get('codigo', '').strip()
        nombre = request.form.get('nombre', '').strip()
        stock_inicial = limpiar_monto(request.form.get('stock_inicial'))
        stock_minimo = limpiar_monto(request.form.get('stock_minimo')) or 5.0
        unidad_medida = request.form.get('unidad_medida', '').strip()
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
        cantidad = limpiar_monto(request.form.get('cantidad'))
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

# ===========================================================================
# MÓDULO DE DOCUMENTOS
# ===========================================================================
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

@app.route('/documentos/factura-venta', methods=['GET', 'POST'])
def factura_venta():
    if request.method == 'POST':
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
            cant_val = limpiar_monto(cant)
            vu_val = limpiar_monto(vu)
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

        retefuente = limpiar_monto(request.form.get('retefuente'))
        reteica = limpiar_monto(request.form.get('reteica'))
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

        nombre_firmante = request.form.get('nombre_firmante', 'ANGIE RUEDA ERAZO').strip()
        cargo_firmante = request.form.get('cargo_firmante', 'Representante Legal').strip()

        es_femenino = (trato_usuario == 'La señora')

        try:
            f_dt = datetime.strptime(fecha_expedicion_str, '%Y-%m-%d')
            fecha_texto = f"a los {f_dt.day} días del mes de {MESES[f_dt.month - 1]} de {f_dt.year}"
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
            'identificado': 'identificada' if es_femenino else 'identificado',
            'matriculado': 'matriculada' if es_femenino else 'matriculado',
            'vinculado': 'vinculada' if es_femenino else 'vinculado',
            'usuario_word': 'usuaria' if es_femenino else 'usuario',
            'el_usuario': 'la usuaria' if es_femenino else 'el usuario',
            'del_interesado': 'de la interesada' if es_femenino else 'del interesado'
        }
        return render_template('certificado_servicios_print.html', datos=datos)

    return render_template('certificado_servicios_form.html', datetime=datetime.now().strftime('%Y-%m-%d'))

# ===========================================================================
# MÓDULO DE PAGOS ANTICIPADOS
# ===========================================================================
@app.route('/pagos-anticipados', methods=['GET', 'POST'])
def pagos_anticipados():
    if request.method == 'POST':
        return guardar_pago_anticipado()

    pagos = PagoAnticipado.query.order_by(PagoAnticipado.id.desc()).all()

    total_recaudado = sum(p.valor_total for p in pagos)
    total_saldo_disponible = sum(p.saldo_pendiente for p in pagos)
    total_aplicado = total_recaudado - total_saldo_disponible
    total_cargo_mes = sum(p.valor_unitario for p in pagos if p.saldo_pendiente > 0 and p.meses_restantes > 0)

    return render_template(
        'pagos_anticipados.html',
        pagos=pagos,
        total_recaudado=total_recaudado,
        total_saldo_disponible=total_saldo_disponible,
        total_aplicado=total_aplicado,
        total_cargo_mes=total_cargo_mes,
        mes_actual_default=datetime.now().strftime('%Y-%m')
    )

@app.route('/pagos-anticipados/guardar', methods=['POST'])
def guardar_pago_anticipado():
    nombre_usuario = request.form.get('nombre_usuario', '').strip()
    documento = request.form.get('documento', '').strip()
    codigo_usuario = request.form.get('codigo_usuario', '').strip()
    direccion_predio = request.form.get('direccion_predio', '').strip()

    mes_inicio = request.form.get('mes_inicio', datetime.now().strftime('%Y-%m'))
    mes_final = request.form.get('mes_final', datetime.now().strftime('%Y-%m'))

    numero_meses = calcular_meses_diferencia(mes_inicio, mes_final)

    # Buscar el valor unitario en todos los nombres de campos posibles
    raw_val_unitario = (
        request.form.get('valor_unitario') or
        request.form.get('valor_mes') or
        request.form.get('tarifa') or
        request.form.get('valor') or
        request.form.get('valor_unitario_mes')
    )

    # Buscar el valor total en caso de que el formulario lo envie directamente
    raw_val_total = (
        request.form.get('valor_total') or
        request.form.get('total') or
        request.form.get('monto_total')
    )

    valor_unitario = limpiar_monto(raw_val_unitario)
    valor_total = limpiar_monto(raw_val_total)

    # Si se ingreso valor unitario pero no total, calcularlo
    if valor_unitario > 0 and valor_total == 0:
        valor_total = valor_unitario * numero_meses
    # Si se ingreso valor total pero no unitario, calcularlo
    elif valor_total > 0 and valor_unitario == 0 and numero_meses > 0:
        valor_unitario = valor_total / numero_meses

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
    flash('Pago anticipado registrado exitosamente.', 'exito')
    return redirect(url_for('pagos_anticipados'))

@app.route('/pagos-anticipados/descontar/<int:id>', methods=['POST'])
def descontar_pago_anticipado(id):
    pago = PagoAnticipado.query.get_or_404(id)
    if pago.meses_restantes > 0 and pago.saldo_pendiente > 0:
        pago.saldo_pendiente -= pago.valor_unitario
        if pago.saldo_pendiente < 0:
            pago.saldo_pendiente = 0.0
        pago.meses_restantes -= 1
        db.session.commit()
    return redirect(url_for('pagos_anticipados'))

@app.route('/pagos-anticipados/cargar-mes', methods=['POST'])
def cargar_mes_anticipado():
    # Detecta el valor enviado desde el select del modal
    target = (
        request.form.get('target_usuario', '') or 
        request.form.get('pago_id', '') or 
        request.form.get('codigo_usuario', '')
    ).strip()

    if not target:
        flash('No se seleccionó ningún usuario o parámetro válido.', 'error')
        return redirect(url_for('pagos_anticipados'))

    # OPCIÓN 1: Cargar cobro a TODOS los usuarios activos
    if target.upper() == "TODOS":
        pagos = PagoAnticipado.query.filter(
            PagoAnticipado.meses_restantes > 0, 
            PagoAnticipado.saldo_pendiente > 0
        ).all()
        
        if not pagos:
            flash('No hay usuarios con pagos pendientes por aplicar.', 'advertencia')
            return redirect(url_for('pagos_anticipados'))

        count = 0
        for pago in pagos:
            pago.saldo_pendiente -= pago.valor_unitario
            if pago.saldo_pendiente < 0:
                pago.saldo_pendiente = 0.0
            pago.meses_restantes -= 1
            count += 1

        db.session.commit()
        flash(f'Se aplicó el cobro del mes a {count} usuario(s) con saldo activo.', 'exito')
        return redirect(url_for('pagos_anticipados'))

    # OPCIÓN 2: Cargar cobro a UN SOLO usuario
    pago = None
    
    # 1. Intentar buscar por ID (si el select envía el ID numérico del registro)
    if target.isdigit():
        pago = PagoAnticipado.query.get(int(target))

    # 2. Si no lo encuentra por ID, buscar por código de usuario con meses activos
    if not pago:
        pago = PagoAnticipado.query.filter(
            PagoAnticipado.codigo_usuario == target,
            PagoAnticipado.meses_restantes > 0,
            PagoAnticipado.saldo_pendiente > 0
        ).first()

    # 3. Aplicar el descuento si existe y tiene saldo
    if pago and pago.meses_restantes > 0 and pago.saldo_pendiente > 0:
        pago.saldo_pendiente -= pago.valor_unitario
        if pago.saldo_pendiente < 0:
            pago.saldo_pendiente = 0.0
        pago.meses_restantes -= 1
        
        db.session.commit()
        flash(f'Se cargó el mes correctamente para: {pago.nombre_usuario}.', 'exito')
    else:
        flash('No se encontró un pago activo para la selección realizada o el usuario ya no tiene meses pendientes.', 'error')

    return redirect(url_for('pagos_anticipados'))

@app.route('/pagos-anticipados/eliminar/<int:pago_id>', methods=['POST'])
def eliminar_pago_anticipado(pago_id):
    pago = PagoAnticipado.query.get_or_404(pago_id)
    db.session.delete(pago)
    db.session.commit()
    flash('Registro de pago anticipado eliminado exitosamente.', 'exito')
    return redirect(url_for('pagos_anticipados'))

@app.route('/pagos-anticipados/certificado/<int:pago_id>')
def certificado_pago_anticipado(pago_id):
    pago = PagoAnticipado.query.get_or_404(pago_id)
    
    MESES = [
        'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
        'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'
    ]
    
    hoy = datetime.now()

    return render_template(
        'certificado_pago_anticipado_print.html',  # O el nombre de tu plantilla HTML
        pago=pago,
        dia_actual=hoy.day,
        mes_actual=MESES[hoy.month - 1],
        ano_actual=hoy.year
    )

# ARRANQUE DE LA APLICACIÓN
# ===========================================================================
import os

if __name__ == '__main__':
    # Lee el puerto dinámico que asigna Render (o usa 5000 si ejecutas localmente)
    port = int(os.environ.get('PORT', 5000))
    # Enlaza a 0.0.0.0 para escuchar en la red pública del servidor
    app.run(host='0.0.0.0', port=port)