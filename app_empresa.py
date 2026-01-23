import streamlit as st
import pandas as pd
import sqlite3
from datetime import date, datetime
import os
import hashlib
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import altair as alt
import base64
import json
import socket

# --- FUNCIONES DE USUARIO Y HASHING ---
def make_hashes(password):
    """Genera un hash SHA256 para una contraseña."""
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    """Verifica si una contraseña coincide con un hash."""
    if make_hashes(password) == hashed_text:
        return hashed_text
    return False

def get_user_id(username):
    """Obtiene el ID de un usuario a partir de su nombre de usuario."""
    conn = sqlite3.connect('produccion.db', timeout=30)
    c = conn.cursor()
    c.execute('SELECT id FROM usuarios WHERE username = ?', (username,))
    user_id = c.fetchone()
    conn.close()
    return user_id[0] if user_id else None

def get_user_role(username):
    """Obtiene el rol de un usuario (admin, ventas, operario)."""
    conn = sqlite3.connect('produccion.db', timeout=30)
    c = conn.cursor()
    try:
        c.execute('SELECT rol FROM usuarios WHERE username = ?', (username,))
        result = c.fetchone()
        return result[0] if result and result[0] else 'operario'
    except:
        return 'operario'
    finally:
        conn.close()

def add_userdata(username, password):
    """Agrega un nuevo usuario a la base de datos."""
    conn = sqlite3.connect('produccion.db', timeout=30)
    c = conn.cursor()
    try:
        c.execute('INSERT INTO usuarios(username, password) VALUES (?,?)', (username, make_hashes(password)))
        conn.commit()
        st.success(f"Usuario '{username}' creado exitosamente.")
        st.info("Ahora puedes ir a la sección de Login para iniciar sesión.")
    except sqlite3.IntegrityError:
        st.error(f"El nombre de usuario '{username}' ya existe.")
    finally:
        conn.close()


def login_user(username, password):
    """Verifica las credenciales de un usuario y lo loguea."""
    conn = sqlite3.connect('produccion.db', timeout=30)
    c = conn.cursor()
    c.execute('SELECT * FROM usuarios WHERE username =? AND password = ?', (username, make_hashes(password)))
    data = c.fetchall()
    conn.close()
    return data

# --- CONFIGURACIÓN DE LA BASE DE DATOS (BACKEND) ---
def init_db():
    """Inicializa la BD y actualiza el esquema de tablas si es necesario."""
    conn = sqlite3.connect('produccion.db', timeout=30)
    c = conn.cursor()

    # Habilitar claves foráneas para integridad referencial
    c.execute("PRAGMA foreign_keys = ON")

    # --- Función auxiliar para añadir columnas de forma segura ---
    def add_column_if_not_exists(table, column, type):
        c.execute(f"PRAGMA table_info({table})")
        if not any(col[1] == column for col in c.fetchall()):
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {type}")
            st.toast(f"Agregada columna '{column}' a la tabla '{table}'.")

    # --- 1. TABLA MAESTRA (EJE) ---
    c.execute('''
        CREATE TABLE IF NOT EXISTS proyectos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT, 
            nombre_proyecto TEXT,
            fecha_creacion DATETIME,
            estado TEXT,
            imagen_path TEXT,
            prioridad TEXT,
            estado_anterior TEXT
        )
    ''')

    # --- 2. TABLA VENTAS (PEDIDOS) ---
    c.execute('''
        CREATE TABLE IF NOT EXISTS info_ventas (
            proyecto_id INTEGER PRIMARY KEY,
            cliente TEXT,
            nombre_proyecto TEXT,
            numero_pedido TEXT,
            orden_produccion TEXT,
            fecha_entrega DATE,
            cantidad_solicitada INTEGER,
            logo_cliente_path TEXT,
            FOREIGN KEY (proyecto_id) REFERENCES proyectos (id) ON DELETE CASCADE
        )
    ''')

    # --- 3. TABLA TÉCNICA (INGENIERÍA) ---
    c.execute('''
        CREATE TABLE IF NOT EXISTS info_tecnica (
            proyecto_id INTEGER PRIMARY KEY,
            material TEXT,
            acabado TEXT,
            medidas TEXT,
            metros_lineales REAL,
            numero_cavidades INTEGER,
            posicion_etiqueta TEXT,
            numero_core TEXT,
            cantidad_por_core INTEGER,
            FOREIGN KEY (proyecto_id) REFERENCES proyectos (id) ON DELETE CASCADE
        )
    ''')

    # --- 4. TABLA PREPRENSA ---
    c.execute('''
        CREATE TABLE IF NOT EXISTS info_preprensa (
            proyecto_id INTEGER PRIMARY KEY,
            proveedor_preprensa TEXT,
            area_preprensa_cm2 REAL,
            numero_colores INTEGER,
            FOREIGN KEY (proyecto_id) REFERENCES proyectos (id) ON DELETE CASCADE
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS proyectos_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proyecto_id INTEGER NOT NULL,
            estado TEXT NOT NULL,
            timestamp_inicio DATETIME NOT NULL,
            timestamp_fin DATETIME,
            usuario_id INTEGER,
            maquina_utilizada TEXT,
            FOREIGN KEY (proyecto_id) REFERENCES proyectos (id),
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        )
    ''')

    # --- 5. TABLA IMPRESIÓN (CONFIGURACIÓN) ---
    c.execute('''
        CREATE TABLE IF NOT EXISTS info_impresion (
            proyecto_id INTEGER PRIMARY KEY,
            detalles_impresion TEXT,
            FOREIGN KEY (proyecto_id) REFERENCES proyectos (id) ON DELETE CASCADE
        )
    ''')

    # --- 6. TABLA TROQUELADO (HERRAMENTAL) ---
    c.execute('''
        CREATE TABLE IF NOT EXISTS info_troquel (
            proyecto_id INTEGER PRIMARY KEY,
            troquel_existente TEXT,
            numero_troquel TEXT,
            numero_lamina TEXT,
            FOREIGN KEY (proyecto_id) REFERENCES proyectos (id) ON DELETE CASCADE
        )
    ''')

    # --- MIGRACIÓN AUTOMÁTICA DE DATOS (SI EXISTEN) ---
    try:
        # Verificamos si la tabla info_ventas está vacía y si proyectos tiene datos antiguos
        c.execute("SELECT COUNT(*) FROM info_ventas")
        count_new = c.fetchone()[0]
        
        # Verificar columnas existentes en proyectos para saber si migrar
        c.execute("PRAGMA table_info(proyectos)")
        columns_proyectos = [info[1] for info in c.fetchall()]
        
        # Si la tabla nueva está vacía y la vieja tiene la columna 'material' (indicador de esquema viejo), migramos
        if count_new == 0 and 'material' in columns_proyectos:
            st.toast("⏳ Migrando base de datos a nueva estructura... No cierres la app.")
            
            # 1. Migrar Ventas
            # Nota: Usamos COALESCE o nombres directos si existen. Asumimos que existen por el check anterior.
            # SQLite permite seleccionar columnas que existen.
            c.execute('INSERT INTO info_ventas (proyecto_id, cliente, nombre_proyecto, numero_pedido, orden_produccion, fecha_entrega, cantidad_solicitada, logo_cliente_path) SELECT id, cliente, nombre_proyecto, numero_pedido, orden_produccion, fecha_entrega, cantidad_solicitada, logo_cliente_path FROM proyectos')
            
            # 2. Migrar Técnica
            c.execute('INSERT INTO info_tecnica (proyecto_id, material, acabado, medidas, metros_lineales, numero_cavidades, posicion_etiqueta, numero_core, cantidad_por_core) SELECT id, material, acabado, medidas, metros_lineales, numero_cavidades, posicion_etiqueta, numero_core, cantidad_por_core FROM proyectos')
            
            # 3. Migrar Preprensa
            c.execute('INSERT INTO info_preprensa (proyecto_id, proveedor_preprensa, area_preprensa_cm2, numero_colores) SELECT id, proveedor_preprensa, area_preprensa_cm2, numero_colores FROM proyectos')
            
            # 4. Migrar Impresión
            c.execute('INSERT INTO info_impresion (proyecto_id, detalles_impresion) SELECT id, detalles_impresion FROM proyectos')
            
            # 5. Migrar Troquel
            c.execute('INSERT INTO info_troquel (proyecto_id, troquel_existente, numero_troquel, numero_lamina) SELECT id, troquel_existente, numero_troquel, numero_lamina FROM proyectos')
            
            conn.commit()
            st.success("✅ Base de datos optimizada y datos migrados correctamente.")
    except Exception as e:
        # Si ocurre un error (ej. columnas no existen), lo ignoramos silenciosamente o mostramos en consola
        print(f"Nota de migración: {e}")

    # --- Actualización del Esquema de tablas existentes (Logs y Usuarios) ---
    add_column_if_not_exists('usuarios', 'rol', 'TEXT')

    # --- Actualización del Esquema de la tabla proyectos_log ---
    add_column_if_not_exists('proyectos_log', 'maquina_utilizada', 'TEXT')
    add_column_if_not_exists('proyectos_log', 'responsable', 'TEXT')
    add_column_if_not_exists('proyectos_log', 'observaciones', 'TEXT')
    add_column_if_not_exists('proyectos_log', 'codigo_bobina', 'TEXT')
    add_column_if_not_exists('proyectos_log', 'metros_impresos', 'REAL')
    add_column_if_not_exists('proyectos_log', 'desperdicio', 'REAL')
    add_column_if_not_exists('proyectos_log', 'cantidad_cores', 'INTEGER')
    add_column_if_not_exists('proyectos_log', 'numero_cajas', 'INTEGER')

    conn.commit()
    conn.close()

# --- Funciones de Proyectos y Analíticas ---
def agregar_proyecto(cliente, nombre, material, acabado, medidas, fecha, estado, username, imagen_path, cantidad_solicitada, metros_lineales, numero_pedido, orden_produccion, numero_cavidades, fecha_creacion, posicion_etiqueta, cantidad_por_core, numero_core, area_preprensa_cm2, numero_colores, prioridad, logo_cliente_path, troquel_existente, numero_troquel, numero_lamina):
    """Agrega un nuevo proyecto a la base de datos con todos sus detalles."""
    conn = sqlite3.connect('produccion.db', timeout=30)
    c = conn.cursor()
    
    # 1. Insertar en Tabla Maestra (Mantenemos cliente/nombre por compatibilidad si es NOT NULL, o usamos dummy)
    c.execute('''
        INSERT INTO proyectos (cliente, nombre_proyecto, fecha_creacion, estado, imagen_path, prioridad)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (cliente, nombre, fecha_creacion, estado, imagen_path, prioridad))
    proyecto_id = c.lastrowid

    # 2. Insertar en Tablas Satélite
    c.execute('INSERT INTO info_ventas (proyecto_id, cliente, nombre_proyecto, numero_pedido, orden_produccion, fecha_entrega, cantidad_solicitada, logo_cliente_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', 
              (proyecto_id, cliente, nombre, numero_pedido, orden_produccion, fecha, cantidad_solicitada, logo_cliente_path))
    
    c.execute('INSERT INTO info_tecnica (proyecto_id, material, acabado, medidas, metros_lineales, numero_cavidades, posicion_etiqueta, numero_core, cantidad_por_core) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
              (proyecto_id, material, acabado, medidas, metros_lineales, numero_cavidades, posicion_etiqueta, numero_core, cantidad_por_core))
    
    c.execute('INSERT INTO info_preprensa (proyecto_id, area_preprensa_cm2, numero_colores) VALUES (?, ?, ?)',
              (proyecto_id, area_preprensa_cm2, numero_colores))
    
    c.execute('INSERT INTO info_troquel (proyecto_id, troquel_existente, numero_troquel, numero_lamina) VALUES (?, ?, ?, ?)',
              (proyecto_id, troquel_existente, numero_troquel, numero_lamina))

    usuario_id = get_user_id(username)
    c.execute('''
        INSERT INTO proyectos_log (proyecto_id, estado, timestamp_inicio, usuario_id)
        VALUES (?, ?, ?, ?)
    ''', (proyecto_id, estado, datetime.now(), usuario_id))
    conn.commit()
    conn.close()
    st.success(f"✅ Proyecto '{nombre}' agregado exitosamente con estado inicial '{estado}'.")

def cambiar_estado_proyecto(proyecto_id, nuevo_estado, username, maquina=None, responsable=None, observaciones=None, codigo_bobina=None, metros_impresos=0.0, desperdicio=0.0, cantidad_cores=0, numero_cajas=0, proveedor_preprensa=None):
    """Registra el cambio de estado de un proyecto en el log, incluyendo la máquina utilizada."""
    conn = sqlite3.connect('produccion.db', timeout=30)
    c = conn.cursor()
    now = datetime.now()
    usuario_id = get_user_id(username)
    # Finaliza el estado anterior y guarda datos de cierre del proceso
    c.execute('''
        UPDATE proyectos_log 
        SET timestamp_fin = ?, responsable = ?, observaciones = ?, codigo_bobina = ?, metros_impresos = ?, desperdicio = ?, cantidad_cores = ?, numero_cajas = ?
        WHERE proyecto_id = ? AND timestamp_fin IS NULL
    ''', (now, responsable, observaciones, codigo_bobina, metros_impresos, desperdicio, cantidad_cores, numero_cajas, proyecto_id))
    # Inicia el nuevo estado
    c.execute('''
        INSERT INTO proyectos_log (proyecto_id, estado, timestamp_inicio, usuario_id, maquina_utilizada)
        VALUES (?, ?, ?, ?, ?)
    ''', (proyecto_id, nuevo_estado, now, usuario_id, maquina))
    # Actualiza el estado general del proyecto
    c.execute('UPDATE proyectos SET estado = ? WHERE id = ?', (nuevo_estado, proyecto_id))
    # Si se definió un proveedor de preprensa (en la etapa de diseño), lo guardamos en el proyecto
    if proveedor_preprensa:
        c.execute('UPDATE info_preprensa SET proveedor_preprensa = ? WHERE proyecto_id = ?', (proveedor_preprensa, proyecto_id))
    conn.commit()
    conn.close()
    st.success(f"Proyecto actualizado al estado '{nuevo_estado}'.")

def guardar_detalles_impresion(proyecto_id, detalles):
    """Guarda la configuración de anilox y colores en formato JSON."""
    conn = sqlite3.connect('produccion.db', timeout=30)
    c = conn.cursor()
    # Usamos INSERT OR REPLACE para asegurar que exista el registro
    c.execute('INSERT OR REPLACE INTO info_impresion (proyecto_id, detalles_impresion) VALUES (?, ?)', 
              (proyecto_id, json.dumps(detalles)))
    conn.commit()
    conn.close()

def actualizar_proyecto_info(proyecto_id, cliente, nombre, material, acabado, cantidad, fecha, prioridad, op, pedido, pos_etiqueta, n_core, cant_core, n_colores, medidas, metros_lineales, area_preprensa, troquel_existente, n_troquel, n_lamina, imagen_path, proveedor_preprensa):
    """Actualiza la información comercial y técnica completa de un proyecto."""
    conn = sqlite3.connect('produccion.db', timeout=30)
    c = conn.cursor()
    
    c.execute('UPDATE proyectos SET cliente=?, nombre_proyecto=?, prioridad=?, imagen_path=? WHERE id=?', (cliente, nombre, prioridad, imagen_path, proyecto_id))
    
    c.execute('UPDATE info_ventas SET cliente=?, nombre_proyecto=?, numero_pedido=?, orden_produccion=?, fecha_entrega=?, cantidad_solicitada=? WHERE proyecto_id=?', 
              (cliente, nombre, pedido, op, fecha, cantidad, proyecto_id))
    
    c.execute('UPDATE info_tecnica SET material=?, acabado=?, medidas=?, metros_lineales=?, posicion_etiqueta=?, numero_core=?, cantidad_por_core=? WHERE proyecto_id=?',
              (material, acabado, medidas, metros_lineales, pos_etiqueta, n_core, cant_core, proyecto_id))
    
    c.execute('UPDATE info_preprensa SET area_preprensa_cm2=?, numero_colores=?, proveedor_preprensa=? WHERE proyecto_id=?',
              (area_preprensa, n_colores, proveedor_preprensa, proyecto_id))
    
    c.execute('UPDATE info_troquel SET troquel_existente=?, numero_troquel=?, numero_lamina=? WHERE proyecto_id=?',
              (troquel_existente, n_troquel, n_lamina, proyecto_id))

    conn.commit()
    conn.close()
    st.toast(f"Proyecto {proyecto_id} actualizado correctamente.")

def eliminar_proyecto(proyecto_id):
    """Elimina un proyecto y sus registros de log."""
    conn = sqlite3.connect('produccion.db', timeout=30)
    c = conn.cursor()
    # Borrar de tablas satélite
    tablas = ['info_ventas', 'info_tecnica', 'info_preprensa', 'info_impresion', 'info_troquel']
    for t in tablas:
        c.execute(f'DELETE FROM {t} WHERE proyecto_id = ?', (proyecto_id,))

    c.execute('DELETE FROM proyectos_log WHERE proyecto_id = ?', (proyecto_id,))
    c.execute('DELETE FROM proyectos WHERE id = ?', (proyecto_id,))
    conn.commit()
    conn.close()
    st.toast(f"Proyecto {proyecto_id} eliminado.")

def actualizar_troquel(proyecto_id, numero_troquel, numero_lamina):
    """Actualiza la información del troquel para un proyecto existente."""
    conn = sqlite3.connect('produccion.db', timeout=30)
    c = conn.cursor()
    c.execute('UPDATE info_troquel SET troquel_existente = "Si", numero_troquel = ?, numero_lamina = ? WHERE proyecto_id = ?', (numero_troquel, numero_lamina, proyecto_id))
    conn.commit()
    conn.close()

def ver_proyectos():
    conn = sqlite3.connect('produccion.db', timeout=30)
    # JOIN masivo para reconstruir la vista completa del proyecto
    query = """
        SELECT 
            p.id, p.fecha_creacion, p.estado, p.imagen_path, p.prioridad, p.estado_anterior,
            v.cliente, v.nombre_proyecto, v.numero_pedido, v.orden_produccion, v.fecha_entrega, v.cantidad_solicitada, v.logo_cliente_path,
            t.material, t.acabado, t.medidas, t.metros_lineales, t.numero_cavidades, t.posicion_etiqueta, t.numero_core, t.cantidad_por_core,
            pp.proveedor_preprensa, pp.area_preprensa_cm2, pp.numero_colores,
            i.detalles_impresion,
            tr.troquel_existente, tr.numero_troquel, tr.numero_lamina
        FROM proyectos p
        LEFT JOIN info_ventas v ON p.id = v.proyecto_id
        LEFT JOIN info_tecnica t ON p.id = t.proyecto_id
        LEFT JOIN info_preprensa pp ON p.id = pp.proyecto_id
        LEFT JOIN info_impresion i ON p.id = i.proyecto_id
        LEFT JOIN info_troquel tr ON p.id = tr.proyecto_id
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def ver_log_procesos(proyecto_id):
    """Obtiene el historial de procesos para un proyecto y calcula duraciones."""
    conn = sqlite3.connect('produccion.db', timeout=30)
    query = """
        SELECT pl.estado, u.username, pl.maquina_utilizada, pl.timestamp_inicio, pl.timestamp_fin,
               pl.responsable, pl.observaciones, pl.codigo_bobina, pl.metros_impresos, pl.desperdicio,
               pl.cantidad_cores, pl.numero_cajas
        FROM proyectos_log pl
        LEFT JOIN usuarios u ON pl.usuario_id = u.id
        WHERE pl.proyecto_id = ? ORDER BY pl.timestamp_inicio
    """
    df = pd.read_sql_query(query, conn, params=(proyecto_id,))
    conn.close()

    if df.empty: return pd.DataFrame()

    df['timestamp_inicio'] = pd.to_datetime(df['timestamp_inicio'])
    df['timestamp_fin'] = pd.to_datetime(df['timestamp_fin'])
    
    df['Duracion (minutos)'] = df.apply(
        lambda row: round(((row['timestamp_fin'] if pd.notna(row['timestamp_fin']) else datetime.now()) - row['timestamp_inicio']).total_seconds() / 60, 2),
        axis=1
    )
    
    df.rename(columns={'estado': 'Estado', 'username': 'Operario', 'maquina_utilizada': 'Máquina', 'timestamp_inicio': 'Inicio', 'timestamp_fin': 'Fin'}, inplace=True)
    df['Inicio'] = df['Inicio'].dt.strftime('%Y-%m-%d %H:%M:%S')
    df['Fin'] = df['Fin'].dt.strftime('%Y-%m-%d %H:%M:%S')
    return df[['Estado', 'Máquina', 'Operario', 'responsable', 'Inicio', 'Fin', 'Duracion (minutos)', 'metros_impresos', 'desperdicio', 'codigo_bobina', 'cantidad_cores', 'numero_cajas', 'observaciones']]

def dibujar_montaje(ancho, largo, gap_avance, repeticiones, z_mm, cavidades, gap_ancho):
    """Genera un gráfico visual del montaje en el cilindro."""
    # Reducimos el tamaño a la mitad aprox (antes 4,6) para que sea más compacto
    fig, ax = plt.subplots(figsize=(2.5, 3.5))
    
    # Configuración del lienzo (simulando el sustrato)
    margen_x = 2
    ancho_contenido = (ancho * cavidades) + (gap_ancho * max(0, cavidades - 1))
    ancho_total = ancho_contenido + (margen_x * 2)
    
    # Dibujar el fondo (Sustrato / Banda)
    rect_sustrato = patches.Rectangle((0, 0), ancho_total, z_mm, linewidth=0, facecolor='#f1f5f9')
    ax.add_patch(rect_sustrato)
    
    # Líneas guía del cilindro (inicio y fin de la vuelta)
    ax.axhline(y=0, color='black', linestyle='-', linewidth=1)
    ax.axhline(y=z_mm, color='black', linestyle='-', linewidth=1)
    
    paso = z_mm / repeticiones
    
    for i in range(int(repeticiones)):
        y_pos = i * paso
        for j in range(int(cavidades)):
            x_pos = margen_x + (j * (ancho + gap_ancho))
            
            # Dibujar la etiqueta (Azul)
            rect_etiqueta = patches.Rectangle((x_pos, y_pos), ancho, largo, linewidth=0.5, edgecolor='#1e40af', facecolor='#60a5fa', alpha=0.8)
            ax.add_patch(rect_etiqueta)
            
            # Texto de medida solo en la primera columna para no saturar
            if j == 0:
                ax.text(x_pos + ancho/2, y_pos + largo/2, f"{int(largo)}", ha='center', va='center', fontsize=6, color='white', fontweight='bold')
            
            # Visualización del Gap (Rojo rayado) si existe
            if gap_avance > 0.1:
                rect_gap = patches.Rectangle((x_pos, y_pos + largo), ancho, gap_avance, linewidth=0, facecolor='#fca5a5', alpha=0.4, hatch='///')
                ax.add_patch(rect_gap)

    ax.set_xlim(0, ancho_total)
    ax.set_ylim(0, z_mm + (z_mm * 0.05)) # Un poco de margen visual arriba
    ax.set_title(f"Z ({z_mm:.1f}mm) x {int(cavidades)} cavs", fontsize=8)
    ax.set_ylabel("Avance", fontsize=7)
    ax.set_xticks([]) # Ocultar eje X para limpieza
    ax.tick_params(axis='y', labelsize=6)
    ax.set_aspect('equal', adjustable='box') # Mantener proporciones reales
    ax.axis('on')
    return fig

def get_local_ip():
    """Intenta obtener la IP local de la máquina para facilitar la conexión."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # no necesita ser alcanzable, solo para detectar la interfaz de salida
        s.connect(('8.8.8.8', 80))
        IP = s.getsockname()[0]
    except Exception:
        IP = "No detectada (Usa ipconfig)"
    finally:
        s.close()
    return IP

# --- INTERFAZ DE USUARIO (FRONTEND CON STREAMLIT) ---
def main_app():
    """Contiene la lógica principal de la aplicación una vez que el usuario ha iniciado sesión."""
    
    if 'form_key' not in st.session_state:
        st.session_state['form_key'] = 0

    # --- CABECERA CON LOGO DE LA EMPRESA ---
    col_h1, col_h2 = st.columns([2, 6])
    with col_h1:
        logo_path = os.path.join("img", "LOGO 2024ET_TRANSPARENTE.png")
        if os.path.exists(logo_path):
            st.image(logo_path, width=250)
        else:
            st.title("🏭")
    with col_h2:
        st.title("Sistema de Control de Producción")

    username = st.session_state['logged_in_user']

    st.sidebar.success(f"Usuario: {username}")
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state['logged_in_user'] = None
        st.rerun()
    
    # --- ESTILOS CSS PARA TABLETS Y PANTALLAS TÁCTILES ---
    st.markdown("""
        <style>
        /* Hacer los botones más grandes para facilitar el toque */
        div.stButton > button {
            height: 3em;
            width: 100%;
            font-weight: bold;
            border-radius: 10px;
        }
        /* Espaciado extra para evitar toques accidentales */
        div.stSelectbox, div.stTextInput, div.stNumberInput, div.stDateInput {
            margin-bottom: 10px;
        }
        </style>
    """, unsafe_allow_html=True)

    # --- NAVEGACIÓN POR BOTONES ---
    if 'current_page' not in st.session_state:
        st.session_state['current_page'] = "Nuevo Proyecto"

    if st.sidebar.button("📝 Nuevo Proyecto", key="nav_nuevo", type="primary" if st.session_state['current_page'] == "Nuevo Proyecto" else "secondary", use_container_width=True):
        st.session_state['current_page'] = "Nuevo Proyecto"
        st.rerun()

    if st.sidebar.button("📋 Ver Listado", key="nav_lista", type="primary" if st.session_state['current_page'] == "Ver Listado" else "secondary", use_container_width=True):
        st.session_state['current_page'] = "Ver Listado"
        st.rerun()

    if st.sidebar.button("📊 Analíticas", key="nav_analiticas", type="primary" if st.session_state['current_page'] == "Analíticas" else "secondary", use_container_width=True):
        st.session_state['current_page'] = "Analíticas"
        st.rerun()

    if st.sidebar.button("⚙️ Configuración", key="nav_config", type="primary" if st.session_state['current_page'] == "Configuración" else "secondary", use_container_width=True):
        st.session_state['current_page'] = "Configuración"
        st.rerun()

    choice = st.session_state['current_page']
    lista_estados = ["Por aprobar", "Diseño", "Preprensa", "Impresion", "Control calidad", "Troquelado", "Despacho", "Entregado"]

    maquinas_por_estado = {
        "Impresion": ["SP1", "FIT 350", "SUPERPRINT", "MARK ANDY"],
        "Control calidad": [f"Controladora {i+1}" for i in range(6)],
        "Troquelado": ["Troqueladora Plana"]
    }

    # Directorio para guardar imágenes
    if not os.path.exists("uploads"):
        os.makedirs("uploads")

    if choice == "Nuevo Proyecto":
        st.subheader("📝 Registrar Nueva Orden")

        # --- Definición de Z y cálculo de Largo ---
        Z_PITCH_MM = 3.175  # 1/8 de pulgada en mm
        # Usamos la lista de Zs proporcionada por el usuario
        Z_UNITS_LIST = [63, 70, 76, 80, 82, 84, 85, 88, 90, 96, 106, 114, 120, 130]
        Z_UNITS_MM = {z: round(z * Z_PITCH_MM, 3) for z in Z_UNITS_LIST}
        
        # --- SECCIÓN 1: INFORMACIÓN GENERAL ---
        with st.container(border=True):
            st.markdown("##### 📋 Información General del Pedido")
            c1, c2, c3 = st.columns(3)
            cliente = c1.text_input("Cliente", key=f"cliente_{st.session_state['form_key']}")
            nombre = c2.text_input("Nombre del Proyecto/Referencia", key=f"nombre_{st.session_state['form_key']}")
            prioridad = c3.selectbox("Prioridad", ["Normal", "Alta", "Urgente"], key=f"prioridad_{st.session_state['form_key']}")
            
            c4, c5, c6 = st.columns(3)
            orden_produccion = c4.text_input("Orden de Producción (OP)", key=f"op_{st.session_state['form_key']}")
            numero_pedido = c5.text_input("Número de Pedido", key=f"pedido_{st.session_state['form_key']}")
            fecha = c6.date_input("Fecha de Entrega", min_value=date.today(), key=f"fecha_{st.session_state['form_key']}")

        # --- SECCIÓN 2: ESPECIFICACIONES TÉCNICAS ---
        with st.container(border=True):
            st.markdown("##### ⚙️ Especificaciones Técnicas")
            c1, c2, c3, c4 = st.columns(4)
            material = c1.selectbox("Material", ["PPBB", "Esmaltado", "PPMet", "PPT", "Carton"], key=f"material_{st.session_state['form_key']}")
            acabado = c2.selectbox("Acabado", ["Lam Mate", "Lam Brillante", "Cold Foil Dorado", "Cold Foil Plata",  "UV Brillante", "UV Mate", "Sin acabado"], key=f"acabado_{st.session_state['form_key']}")
            numero_colores = c3.number_input("N° Colores", min_value=1, step=1, value=1, key=f"colores_{st.session_state['form_key']}")
            cantidad_solicitada = c4.number_input("Cantidad Total", min_value=1000, step=1000, value=1000, key=f"cantidad_{st.session_state['form_key']}")
            
            c5, c6, c7 = st.columns(3)
            posicion_etiqueta = c5.selectbox("Posición (Winding)", ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"], key=f"posicion_{st.session_state['form_key']}")
            numero_core = c6.selectbox("Core", ["1 pulgada", "3 pulgadas", "Otro"], key=f"core_{st.session_state['form_key']}")
            cantidad_por_core = c7.number_input("Cant. por Core", min_value=100, step=100, value=1000, key=f"cant_core_{st.session_state['form_key']}")

        # --- SECCIÓN 3: INGENIERÍA Y MONTAJE ---
        with st.container(border=True):
            st.markdown("##### 🛠️ Herramental")
            c_t1, c_t2, c_t3 = st.columns(3)
            troquel_existente_bool = c_t1.checkbox("¿Troquel Existente?", key=f"troquel_bool_{st.session_state['form_key']}")
            troquel_existente = "Si" if troquel_existente_bool else "No"
            numero_troquel = ""
            numero_lamina = ""
            if troquel_existente_bool:
                numero_troquel = c_t2.text_input("Número de Troquel", key=f"num_troquel_{st.session_state['form_key']}")
                numero_lamina = c_t3.text_input("Número de Lámina", key=f"num_lamina_{st.session_state['form_key']}")
            st.markdown("---")
            
            col_ing1, col_ing2 = st.columns([2, 1])
            
            with col_ing1:
                st.subheader("Dimensiones y Desarrollo")
                ancho = st.number_input("Ancho (cavidad) (mm)", min_value=1.0, step=1.0, format="%.2f", key=f"ancho_{st.session_state['form_key']}")
                gap_ancho = st.number_input("Gap al Ancho (mm)", min_value=0.0, step=0.1, format="%.2f", key=f"gap_ancho_{st.session_state['form_key']}")
                cavidades = st.number_input("Cavidades al Ancho", min_value=1, step=1, value=1, key=f"cavidades_{st.session_state['form_key']}")
                largo = st.number_input("Largo (avance) (mm)", min_value=1.0, step=1.0, format="%.2f", key=f"largo_{st.session_state['form_key']}")
                repeticiones = st.number_input("Número de Repeticiones", min_value=1, step=1, value=1, key=f"repeticiones_{st.session_state['form_key']}")
                
                # --- Lógica de Recomendación de Z ---
                best_z_index = 0
                recomendacion_info = ""
                if largo > 0 and repeticiones > 0:
                    # Buscar la Z que ofrezca el menor desperdicio (Gap) pero que sea viable (Gap >= 2mm)
                    posibles_z = []
                    for idx, z in enumerate(Z_UNITS_LIST):
                        circ = Z_UNITS_MM[z]
                        gap_calc = (circ / repeticiones) - largo
                        if gap_calc >= 2.0: # Margen mínimo de seguridad de 2mm
                            posibles_z.append((gap_calc, idx, z))
                    
                    if posibles_z:
                        posibles_z.sort() # Ordenar por menor gap (el primero es el más eficiente)
                        best_z_index = posibles_z[0][1]
                        recomendacion_info = f" | ⭐ Sugerido: Z{posibles_z[0][2]}"

                z_seleccionada = st.selectbox(
                    f"Unidad de Impresión (Z){recomendacion_info}",
                    options=Z_UNITS_LIST,
                    index=best_z_index,
                    help="La 'Z' corresponde al número de dientes del engranaje del cilindro (1Z = 1/8 pulgada).",
                    key=f"z_sel_{st.session_state['form_key']}_{best_z_index}"
                )

                # --- Cálculos automáticos ---
                gap = 0.0
                metros_lineales = 0.0
                area_preprensa_cm2 = 0.0
                circunferencia_mm = 0.0
                ancho_montaje_mm = 0.0
                largo_montaje_mm = 0.0

                if z_seleccionada and largo > 0 and repeticiones > 0:
                    circunferencia_mm = Z_UNITS_MM[z_seleccionada]
                    gap = (circunferencia_mm / repeticiones) - largo
                    
                    # Cálculo de metros lineales
                    if cantidad_solicitada > 0 and repeticiones > 0:
                        # Cada revolución del cilindro usa `circunferencia_mm` de material y produce `repeticiones` etiquetas.
                        # Por tanto, la longitud de material por etiqueta es (circunferencia_mm / repeticiones).
                        longitud_total_mm = cantidad_solicitada * (circunferencia_mm / repeticiones)
                        metros_lineales = longitud_total_mm / 1000
                    
                    # Cálculo de Área de Preprensa (cm²)
                    # Ancho Montaje (mm) = (ancho * cavidades) + gaps
                    ancho_montaje_mm = (ancho * cavidades) + (gap_ancho * max(0, cavidades - 1))
                    # Largo Montaje (mm) = circunferencia Z
                    largo_montaje_mm = circunferencia_mm
                    
                    # Fórmula: ((Ancho cm + 4) * (Largo cm + 2)) * numero_colores
                    area_placa_base = ((ancho_montaje_mm / 10) + 4) * ((largo_montaje_mm / 10) + 2)
                    area_preprensa_cm2 = area_placa_base * numero_colores

                st.text_input("Gap de Avance (mm)", value=f"{gap:.2f}", disabled=True, help="Separación vertical entre etiquetas. Se calcula: (Circunferencia Z / Repeticiones) - Largo.")
                st.text_input("Metros Lineales Estimados", value=f"{metros_lineales:.2f}", disabled=True, help="Longitud total de material requerida para la cantidad solicitada.")
                
                # Mostrar desglose y permitir edición manual
                breakdown_msg = f"Ancho: ({ancho_montaje_mm/10:.2f}cm [incluye gaps] + 4) x Largo: ({largo_montaje_mm/10:.2f}cm + 2) x {numero_colores} col" if area_preprensa_cm2 > 0 else "Ingrese medidas..."
                # Usamos el valor calculado en la key para forzar la actualización si cambian los inputs
                area_preprensa_final = st.number_input("Área Plancha Total (cm²)", value=float(f"{area_preprensa_cm2:.2f}"), step=10.0, help=breakdown_msg, key=f"area_{st.session_state['form_key']}_{area_preprensa_cm2}")
            
            with col_ing2:
                estado = st.selectbox("Estado Inicial", lista_estados, key=f"estado_ini_{st.session_state['form_key']}")
                
                # --- VISUALIZACIÓN DEL MONTAJE (Movid a la derecha y reducido) ---
                if z_seleccionada and largo > 0 and repeticiones > 0:
                    st.markdown("---")
                    fig = dibujar_montaje(ancho, largo, gap, repeticiones, circunferencia_mm, cavidades, gap_ancho)
                    st.pyplot(fig, use_container_width=False)

        uploaded_file = st.file_uploader("Cargar Arte / Imagen de referencia (PDF, JPG, PNG)", type=['png', 'jpg', 'jpeg', 'pdf'], key=f"file_{st.session_state['form_key']}")
        
        if uploaded_file is not None:
            st.markdown("### 🖼️ Previsualización del Arte")
            if uploaded_file.name.lower().endswith('.pdf'):
                base64_pdf = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
                pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="500" type="application/pdf"></iframe>'
                st.markdown(pdf_display, unsafe_allow_html=True)
            else:
                st.image(uploaded_file, caption="Arte cargado", use_container_width=True)

        if st.button("Guardar Proyecto"):
            if cliente and nombre and ancho > 0 and largo > 0 and uploaded_file is not None:
                # Formateamos las medidas en un solo string para guardarlo
                medidas = f"Ancho: {ancho}mm (Gap: {gap_ancho}mm) x {cavidades} cavs, Largo: {largo}mm | Z{z_seleccionada}, {repeticiones} reps, Gap Avance: {gap:.2f}mm"
                
                imagen_path = None
                # Guardar la imagen (ya validamos que existe)
                imagen_path = os.path.join("uploads", uploaded_file.name)
                with open(imagen_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                fecha_creacion = datetime.now()
                agregar_proyecto(cliente, nombre, material, acabado, medidas, fecha, estado, username, imagen_path, cantidad_solicitada, metros_lineales, numero_pedido, orden_produccion, cavidades, fecha_creacion, posicion_etiqueta, cantidad_por_core, numero_core, area_preprensa_final, numero_colores, prioridad, None, troquel_existente, numero_troquel, numero_lamina)
                st.session_state['form_key'] += 1
                st.rerun()
            else:
                if uploaded_file is None:
                    st.error("⚠️ Es OBLIGATORIO cargar una imagen o arte de referencia para guardar el proyecto.")
                else:
                    st.error("⚠️ Por favor ingresa Cliente, Nombre del proyecto, Ancho y Largo válidos.")

    elif choice == "Ver Listado":
        st.subheader("📋 Gestión de Proyectos y Estados")
        df_proyectos = ver_proyectos()
        if df_proyectos.empty:
            st.info("No hay proyectos registrados todavía.")
        else:
            # Obtener rol del usuario actual
            user_role = get_user_role(username)

            for index, proyecto in df_proyectos.iterrows():
                # --- Lógica de Alerta de Fecha ---
                alerta_entrega = ""
                dias_restantes = 999
                if proyecto['fecha_entrega']:
                    try:
                        fecha_entrega_dt = datetime.strptime(proyecto['fecha_entrega'], '%Y-%m-%d').date()
                        dias_restantes = (fecha_entrega_dt - date.today()).days
                        if dias_restantes <= 2 and proyecto['estado'] != "Entregado":
                            alerta_entrega = "🚨 "
                    except:
                        pass

                prioridad_icon = {"Alta": "🔴", "Urgente": "🔥", "Normal": "🟢"}.get(proyecto.get('prioridad', 'Normal'), "⚪")
                op_display = f"OP: {proyecto['orden_produccion']} | " if proyecto['orden_produccion'] else ""
                
                with st.expander(f"{prioridad_icon} {alerta_entrega}{op_display}Cliente: {proyecto['cliente']} | {proyecto['nombre_proyecto']} | Estado: {proyecto['estado']}"):
                    
                    ver_imagen_grande = False
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        pedido_display = f"- **Pedido:** {proyecto['numero_pedido']}\n" if proyecto['numero_pedido'] else ""
                        st.markdown(f"{pedido_display}- **Material:** {proyecto['material']}\n- **Acabado:** {proyecto['acabado']}\n- **Medidas:** {proyecto['medidas']}\n- **Fecha de Entrega:** {proyecto['fecha_entrega']}")
                        
                        if dias_restantes <= 2 and proyecto['estado'] != "Entregado":
                            st.error(f"⚠️ **ATENCIÓN:** Faltan {dias_restantes} días para la entrega.")

                        # Mostrar nuevos datos
                        st.markdown(f"- **Core:** {proyecto['numero_core']} ({proyecto['cantidad_por_core']} u/rollo) | **Posición:** {proyecto['posicion_etiqueta']}")
                        
                        troquel_msg = f"✅ **Troquel:** {proyecto['numero_troquel']} | **Lámina:** {proyecto['numero_lamina']}" if proyecto.get('troquel_existente') == 'Si' else "❌ **Troquel:** Nuevo / No existente"
                        st.markdown(troquel_msg)

                        # --- GESTIÓN DE TROQUEL (EDICIÓN) ---
                        with st.expander("🛠️ Asignar / Editar Troquel"):
                            c_t1, c_t2, c_t3 = st.columns([2, 2, 1])
                            n_troquel = c_t1.text_input("N° Troquel", value=proyecto['numero_troquel'] if proyecto['numero_troquel'] else "", key=f"nt_{proyecto['id']}")
                            n_lamina = c_t2.text_input("N° Lámina", value=proyecto['numero_lamina'] if proyecto['numero_lamina'] else "", key=f"nl_{proyecto['id']}")
                            if c_t3.button("Guardar", key=f"btn_t_{proyecto['id']}"):
                                actualizar_troquel(proyecto['id'], n_troquel, n_lamina)
                                st.rerun()

                        st.markdown(f"- **Área Plancha Total:** {proyecto['area_preprensa_cm2']:.2f} cm² ({proyecto['numero_colores']} colores)")
                        if proyecto['fecha_creacion']:
                            st.caption(f"📅 Creado el: {proyecto['fecha_creacion']}")
                            
                        st.markdown("---")

                        # --- SECCIÓN: CONFIGURACIÓN DE IMPRESIÓN (ANILOX / COLORES) ---
                        if proyecto['numero_colores'] and proyecto['numero_colores'] > 0:
                            with st.expander("🎨 Configuración de Colores y Anilox", expanded=False):
                                # Cargar detalles existentes
                                detalles_actuales = []
                                if proyecto['detalles_impresion']:
                                    try:
                                        detalles_actuales = json.loads(proyecto['detalles_impresion'])
                                    except:
                                        pass
                                
                                # Rellenar lista si faltan datos
                                while len(detalles_actuales) < proyecto['numero_colores']:
                                    detalles_actuales.append({"anilox": "", "tipo_color": "Policromía", "codigo_color": ""})
                                
                                with st.form(key=f"form_anilox_{proyecto['id']}"):
                                    nuevos_detalles = []
                                    anilox_opts = ["XS", "S", "M", "L", "348", "440", "813", "914", "100", "711", "356", "559"]
                                    tipo_opts = ["Policromía", "Pantone"]

                                    for i in range(proyecto['numero_colores']):
                                        st.markdown(f"**Unidad de Color {i+1}**")
                                        c_ani, c_tipo, c_cod = st.columns(3)
                                        
                                        curr_anilox = detalles_actuales[i].get("anilox", "")
                                        idx_anilox = anilox_opts.index(curr_anilox) if curr_anilox in anilox_opts else 0
                                        sel_anilox = c_ani.selectbox(f"Anilox", anilox_opts, index=idx_anilox, key=f"ani_{proyecto['id']}_{i}")
                                        
                                        curr_tipo = detalles_actuales[i].get("tipo_color", "Policromía")
                                        idx_tipo = tipo_opts.index(curr_tipo) if curr_tipo in tipo_opts else 0
                                        sel_tipo = c_tipo.selectbox(f"Tipo", tipo_opts, index=idx_tipo, key=f"tip_{proyecto['id']}_{i}")
                                        
                                        val_codigo = detalles_actuales[i].get("codigo_color", "")
                                        txt_codigo = c_cod.text_input(f"Código/Ref", value=val_codigo, key=f"cod_{proyecto['id']}_{i}", placeholder="Ej. Cyan o P-185C")
                                        
                                        nuevos_detalles.append({"anilox": sel_anilox, "tipo_color": sel_tipo, "codigo_color": txt_codigo})
                                        st.markdown("---")
                                    
                                    if st.form_submit_button("💾 Guardar Configuración de Impresión"):
                                        guardar_detalles_impresion(proyecto['id'], nuevos_detalles)
                                        st.toast("Configuración de impresión guardada.")
                                        st.rerun()

                        # --- SECCIÓN: CONTROL DE PAUSA / REANUDAR ---
                        if proyecto['estado'] != "Entregado":
                            st.markdown("#### ⏱️ Control de Operación")
                            if proyecto['estado'] == "Pausado":
                                st.warning(f"⚠️ **PROYECTO PAUSADO** (Estado previo: {proyecto['estado_anterior']})")
                                if st.button("▶️ REANUDAR OPERACIÓN", key=f"reanudar_{proyecto['id']}", type="primary"):
                                    estado_previo = proyecto['estado_anterior'] if proyecto['estado_anterior'] else "Impresion"
                                    cambiar_estado_proyecto(proyecto['id'], estado_previo, username, maquina="Reanudado")
                                    st.rerun()
                            else:
                                c_pause1, c_pause2 = st.columns([3, 1])
                                motivo_pausa = c_pause1.selectbox("Motivo de Pausa", ["Desayuno", "Almuerzo", "Cena", "Fin de Turno", "Mantenimiento", "Otro"], key=f"motivo_{proyecto['id']}")
                                if c_pause2.button("⏸️ PAUSAR", key=f"pausar_{proyecto['id']}"):
                                    # Guardar estado actual antes de pausar
                                    conn = sqlite3.connect('produccion.db', timeout=30)
                                    conn.execute('UPDATE proyectos SET estado_anterior = ? WHERE id = ?', (proyecto['estado'], proyecto['id']))
                                    conn.commit()
                                    conn.close()
                                    cambiar_estado_proyecto(proyecto['id'], "Pausado", username, maquina=f"Motivo: {motivo_pausa}")
                                    st.rerun()
                            st.markdown("---")

                        current_estado_index = -1
                        try:
                            current_estado_index = lista_estados.index(proyecto['estado'])
                        except ValueError:
                            st.warning(f"El estado '{proyecto['estado']}' no está en la lista de estados predefinidos.")
                        
                        if current_estado_index != -1 and current_estado_index < len(lista_estados) - 1:
                            opciones_siguientes = lista_estados[current_estado_index + 1:]
                            nuevo_estado = st.selectbox("Siguiente estado:", options=opciones_siguientes, key=f"estado_{proyecto['id']}")
                            
                            maquina_seleccionada = None
                            if nuevo_estado in maquinas_por_estado:
                                maquina_seleccionada = st.selectbox(
                                    f"Seleccionar Máquina para '{nuevo_estado}':", 
                                    options=maquinas_por_estado[nuevo_estado], 
                                    key=f"maquina_{proyecto['id']}_{nuevo_estado}"
                                )

                            # --- FORMULARIO DE CIERRE DE PROCESO ---
                            st.markdown(f"**📝 Reporte de Cierre: {proyecto['estado']}**")
                            
                            # Valores por defecto
                            responsable = username
                            codigo_bobina = None
                            metros_impresos = 0.0
                            desperdicio = 0.0
                            cantidad_cores = 0
                            numero_cajas = 0
                            observaciones = ""
                            proveedor_preprensa = None

                            if proyecto['estado'] == "Diseño":
                                responsable = st.selectbox("Responsable Diseño", ["Lucas Rodriguez", "Enrique Velasquez"], key=f"resp_dis_{proyecto['id']}")
                                proveedor_preprensa = st.selectbox("Proveedor Preprensa (Siguiente Paso)", ["TORREFFLEX", "IFLEXO", "GRAFIFLEX"], key=f"prov_pre_sel_{proyecto['id']}")
                                observaciones = st.text_area("Observaciones", key=f"obs_{proyecto['id']}")

                            elif proyecto['estado'] == "Preprensa":
                                prov_asignado = proyecto['proveedor_preprensa'] if proyecto.get('proveedor_preprensa') else "No definido"
                                responsable = st.text_input("Responsable (Proveedor)", value=prov_asignado, key=f"resp_pre_{proyecto['id']}")
                                observaciones = st.text_area("Observaciones", key=f"obs_{proyecto['id']}")

                            elif proyecto['estado'] == "Impresion":
                                c_imp1, c_imp2 = st.columns(2)
                                responsable = c_imp1.text_input("Responsable", value=username, key=f"resp_imp_{proyecto['id']}")
                                codigo_bobina = c_imp2.text_input("Código Bobina", key=f"bob_{proyecto['id']}")
                                c_imp3, c_imp4 = st.columns(2)
                                metros_impresos = c_imp3.number_input("Metros Impresos", min_value=0.0, step=0.1, key=f"met_{proyecto['id']}")
                                desperdicio = c_imp4.number_input("Desperdicio (m)", min_value=0.0, step=0.1, key=f"desp_{proyecto['id']}")
                                observaciones = st.text_area("Observaciones", key=f"obs_{proyecto['id']}")

                            elif proyecto['estado'] == "Control calidad":
                                st.info(f"ℹ️ Core del Proyecto: {proyecto['numero_core']}")
                                c_cc1, c_cc2 = st.columns(2)
                                responsable = c_cc1.text_input("Responsable", value=username, key=f"resp_cc_{proyecto['id']}")
                                cantidad_cores = c_cc2.number_input("Cantidad Cores Usados", min_value=0, step=1, key=f"cores_{proyecto['id']}")
                                observaciones = st.text_area("Observaciones", key=f"obs_{proyecto['id']}")

                            elif proyecto['estado'] == "Troquelado":
                                st.info(f"ℹ️ Troquel Asignado: {proyecto['numero_troquel'] if proyecto['numero_troquel'] else 'No asignado'}")
                                responsable = st.text_input("Responsable", value=username, key=f"resp_tro_{proyecto['id']}")
                                observaciones = st.text_area("Observaciones / Estado del Troquel (Reemplazo)", key=f"obs_{proyecto['id']}")

                            elif proyecto['estado'] == "Despacho":
                                c_des1, c_des2 = st.columns(2)
                                responsable = c_des1.text_input("Responsable", value=username, key=f"resp_des_{proyecto['id']}")
                                numero_cajas = c_des2.number_input("Número de Cajas", min_value=0, step=1, key=f"cajas_{proyecto['id']}")
                                observaciones = st.text_area("Observaciones", key=f"obs_{proyecto['id']}")

                            else:
                                # Formulario genérico para otros estados
                                responsable = st.text_input("Responsable", value=username, key=f"resp_def_{proyecto['id']}")
                                observaciones = st.text_area("Observaciones", key=f"obs_{proyecto['id']}")
                            

                            if st.button("Avanzar Estado", key=f"avanzar_{proyecto['id']}"):
                                cambiar_estado_proyecto(proyecto['id'], nuevo_estado, username, maquina=maquina_seleccionada, responsable=responsable, observaciones=observaciones, codigo_bobina=codigo_bobina, metros_impresos=metros_impresos, desperdicio=desperdicio, cantidad_cores=cantidad_cores, numero_cajas=numero_cajas, proveedor_preprensa=proveedor_preprensa)
                                st.rerun()

                        elif current_estado_index == len(lista_estados) - 1:
                            st.success("Este proyecto ha sido entregado y completado.")
                    
                    with col2:
                        if proyecto['imagen_path'] and os.path.exists(proyecto['imagen_path']):
                            if proyecto['imagen_path'].lower().endswith('.pdf'):
                                with open(proyecto['imagen_path'], "rb") as f:
                                    pdf_data = f.read()
                                st.download_button("📄 Ver/Descargar PDF", data=pdf_data, file_name=os.path.basename(proyecto['imagen_path']), mime="application/pdf", key=f"pdf_{proyecto['id']}")
                            else:
                                st.image(proyecto['imagen_path'], width=150)
                                ver_imagen_grande = st.checkbox("🔍 Ampliar", key=f"zoom_{proyecto['id']}")
                        else:
                            st.info("Sin imagen")
                    
                    if ver_imagen_grande and proyecto['imagen_path'] and not proyecto['imagen_path'].lower().endswith('.pdf'):
                        st.image(proyecto['imagen_path'], caption=f"Arte Ampliado: {proyecto['nombre_proyecto']}", use_container_width=True)

                    # --- SECCIÓN DE EDICIÓN (SOLO ADMIN Y VENTAS) ---
                    if user_role in ['admin', 'ventas']:
                        st.markdown("---")
                        with st.expander(f"✏️ Editar Datos del Pedido (Solo {user_role.capitalize()})"):
                            with st.form(key=f"edit_form_{proyecto['id']}"):
                                c1, c2, c3 = st.columns(3)
                                new_cliente = c1.text_input("Cliente", value=proyecto['cliente'])
                                new_nombre = c2.text_input("Nombre", value=proyecto['nombre_proyecto'])
                                new_prioridad = c3.selectbox("Prioridad", ["Normal", "Alta", "Urgente"], index=["Normal", "Alta", "Urgente"].index(proyecto['prioridad']) if proyecto['prioridad'] in ["Normal", "Alta", "Urgente"] else 0)
                                
                                c4, c5, c6 = st.columns(3)
                                new_op = c4.text_input("OP", value=proyecto['orden_produccion'])
                                new_pedido = c5.text_input("Pedido", value=proyecto['numero_pedido'])
                                
                                val_fecha = date.today()
                                if proyecto['fecha_entrega']:
                                    try: val_fecha = datetime.strptime(proyecto['fecha_entrega'], '%Y-%m-%d').date()
                                    except: pass
                                new_fecha = c6.date_input("Fecha Entrega", value=val_fecha)

                                c7, c8, c9 = st.columns(3)
                                new_material = c7.selectbox("Material", ["PPBB", "Esmaltado", "PPMet", "PPT", "Carton"], index=["PPBB", "Esmaltado", "PPMet", "PPT", "Carton"].index(proyecto['material']) if proyecto['material'] in ["PPBB", "Esmaltado", "PPMet", "PPT", "Carton"] else 0)
                                new_acabado = c8.selectbox("Acabado", ["Lam Mate", "Lam Brillante", "Cold Foil Dorado", "Cold Foil Plata",  "UV Brillante", "UV Mate", "Sin acabado"], index=["Lam Mate", "Lam Brillante", "Cold Foil Dorado", "Cold Foil Plata",  "UV Brillante", "UV Mate", "Sin acabado"].index(proyecto['acabado']) if proyecto['acabado'] in ["Lam Mate", "Lam Brillante", "Cold Foil Dorado", "Cold Foil Plata",  "UV Brillante", "UV Mate", "Sin acabado"] else 0)
                                new_cantidad = c9.number_input("Cantidad", value=proyecto['cantidad_solicitada'])

                                c10, c11, c12, c13 = st.columns(4)
                                new_pos = c10.selectbox("Posición", ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"], index=["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"].index(proyecto['posicion_etiqueta']) if proyecto['posicion_etiqueta'] in ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"] else 0)
                                new_core = c11.selectbox("Core", ["1 pulgada", "3 pulgadas", "Otro"], index=["1 pulgada", "3 pulgadas", "Otro"].index(proyecto['numero_core']) if proyecto['numero_core'] in ["1 pulgada", "3 pulgadas", "Otro"] else 0)
                                new_cant_core = c12.number_input("Cant/Core", value=proyecto['cantidad_por_core'])
                                new_colores = c13.number_input("Colores", value=proyecto['numero_colores'])

                                # --- NUEVOS CAMPOS TÉCNICOS ---
                                st.markdown("##### 📏 Medidas y Datos Técnicos")
                                c14, c15 = st.columns([3, 1])
                                new_medidas = c14.text_input("Descripción de Medidas", value=proyecto['medidas'])
                                new_metros = c15.number_input("Metros Lineales", value=proyecto['metros_lineales'])
                                
                                c16, c17, c18, c19 = st.columns(4)
                                new_area = c16.number_input("Área Preprensa", value=proyecto['area_preprensa_cm2'])
                                
                                troquel_idx = 0
                                if proyecto['troquel_existente'] == 'Si': troquel_idx = 1
                                new_troquel_existente = c17.selectbox("¿Troquel?", ["No", "Si"], index=troquel_idx)
                                
                                new_n_troquel = c18.text_input("N° Troquel", value=proyecto['numero_troquel'] if proyecto['numero_troquel'] else "")
                                new_n_lamina = c19.text_input("N° Lámina", value=proyecto['numero_lamina'] if proyecto['numero_lamina'] else "")

                                new_proveedor_preprensa = st.selectbox("Proveedor Preprensa", ["TORREFFLEX", "IFLEXO", "GRAFIFLEX"], index=["TORREFFLEX", "IFLEXO", "GRAFIFLEX"].index(proyecto['proveedor_preprensa']) if proyecto['proveedor_preprensa'] in ["TORREFFLEX", "IFLEXO", "GRAFIFLEX"] else 0)

                                # --- ACTUALIZAR IMAGEN ---
                                st.markdown("##### 🖼️ Arte / Imagen de Referencia")
                                if not proyecto['imagen_path']:
                                    st.warning("⚠️ Este proyecto no tiene imagen. Sube una para completar el registro.")
                                else:
                                    st.caption(f"Archivo actual: {os.path.basename(proyecto['imagen_path'])}")
                                new_uploaded_file = st.file_uploader("Cargar/Reemplazar Imagen (PDF, JPG, PNG)", type=['png', 'jpg', 'jpeg', 'pdf'], key=f"up_edit_{proyecto['id']}")

                                if st.form_submit_button("💾 Guardar Cambios"):
                                    final_imagen_path = proyecto['imagen_path']
                                    if new_uploaded_file is not None:
                                        if not os.path.exists("uploads"):
                                            os.makedirs("uploads")
                                        final_imagen_path = os.path.join("uploads", new_uploaded_file.name)
                                        with open(final_imagen_path, "wb") as f:
                                            f.write(new_uploaded_file.getbuffer())
                                    
                                    actualizar_proyecto_info(proyecto['id'], new_cliente, new_nombre, new_material, new_acabado, new_cantidad, new_fecha, new_prioridad, new_op, new_pedido, new_pos, new_core, new_cant_core, new_colores, new_medidas, new_metros, new_area, new_troquel_existente, new_n_troquel, new_n_lamina, final_imagen_path, new_proveedor_preprensa)
                                    st.rerun()

                    # --- BOTÓN DE ELIMINAR PROYECTO ---
                    st.markdown("---")
                    if st.button("🗑️ Eliminar Proyecto (Irreversible)", key=f"del_{proyecto['id']}", type="primary"):
                        eliminar_proyecto(proyecto['id'])
                        st.rerun()

    elif choice == "Analíticas":
        st.subheader("📊 Analíticas de Tiempos por Proceso")
        proyectos_df = ver_proyectos()
        if proyectos_df.empty:
            st.info("No hay proyectos para analizar.")
        else:
            # --- GRÁFICO DE TORTA (DISTRIBUCIÓN GENERAL) ---
            st.markdown("### 🥧 Distribución de Pedidos por Área (Total General)")
            
            # Agrupar por estado para el gráfico
            conteo_estados = proyectos_df['estado'].value_counts().reset_index()
            conteo_estados.columns = ['Estado', 'Cantidad']
            
            base = alt.Chart(conteo_estados).encode(
                theta=alt.Theta("Cantidad", stack=True)
            )
            
            pie = base.mark_arc(outerRadius=120, innerRadius=50).encode(
                color=alt.Color("Estado", scale=alt.Scale(scheme='category20b')),
                order=alt.Order("Cantidad", sort="descending"),
                tooltip=["Estado", "Cantidad"]
            )
            
            text = base.mark_text(radius=140).encode(
                text="Cantidad",
                order=alt.Order("Cantidad", sort="descending"),
                color=alt.value("#e2e8f0")  # Color claro para tema oscuro
            )
            
            st.altair_chart(pie + text, use_container_width=True)
            st.markdown("---")

            lista_proyectos = {f"{row['id']} - {row['nombre_proyecto']}": row['id'] for index, row in proyectos_df.iterrows()}
            proyecto_sel_nombre = st.selectbox("Selecciona un Proyecto para ver su historial:", options=lista_proyectos.keys())
            if proyecto_sel_nombre:
                proyecto_id = lista_proyectos[proyecto_sel_nombre]
                log_df = ver_log_procesos(proyecto_id)
                if log_df.empty:
                    st.warning("No hay historial de procesos para este proyecto.")
                else:
                    st.markdown(f"### Historial del Proyecto: {proyecto_sel_nombre}")
                    st.dataframe(log_df, use_container_width=True)
                    
                    st.markdown("### Tiempo por Estado (en minutos)")
                    # Agrupamos por estado y sumamos duraciones si un estado se repite
                    chart_data = log_df.groupby('Estado')['Duracion (minutos)'].sum()
                    
                    # --- GRÁFICO MEJORADO CON ALTAIR ---
                    chart_df = chart_data.reset_index()
                    c = alt.Chart(chart_df).mark_bar().encode(
                        x=alt.X('Estado', sort='-y'),
                        y='Duracion (minutos)',
                        color=alt.Color('Estado', scale=alt.Scale(scheme='viridis')), # Esquema de colores profesional
                        tooltip=['Estado', 'Duracion (minutos)']
                    ).properties(title="Distribución de Tiempos por Fase")
                    
                    st.altair_chart(c, use_container_width=True)

    elif choice == "Configuración":
        st.subheader("⚙️ Configuración y Mantenimiento")
        
        local_ip = get_local_ip()
        st.info(f"📡 **Conexión de Tablets:**\n1. Asegúrate de que el PC y la Tablet estén en la misma red.\n2. Ingresa esta dirección en la tablet: **http://{local_ip}:8501**\n3. Si no carga, revisa el **Firewall de Windows** en el PC y asegura usar el puerto correcto (usualmente 8501).")

        # --- COPIA DE SEGURIDAD ---
        st.markdown("### 💾 Respaldo de Información")
        st.caption("Descarga una copia de la base de datos para guardarla en otro lugar (USB, Nube) por seguridad.")
        if os.path.exists("produccion.db"):
            with open("produccion.db", "rb") as f:
                st.download_button(
                    label="📥 Descargar Copia de Seguridad (Base de Datos)",
                    data=f,
                    file_name=f"produccion_backup_{datetime.now().strftime('%Y-%m-%d_%H%M')}.db",
                    mime="application/x-sqlite3"
                )

        st.error("🚨 **Acción Peligrosa** 🚨")
        st.warning("Haz clic aquí solo si la app no funciona bien y sospechas que la DB está corrupta. **Se borrarán todos los datos.**")
        if st.button("Borrar y Reiniciar Base de Datos"):
            db_file = "produccion.db"
            try:
                if os.path.exists(db_file): os.remove(db_file)
                
                # Limpiar también las imágenes subidas para un reinicio limpio
                if os.path.exists("uploads"):
                    for archivo in os.listdir("uploads"):
                        ruta_archivo = os.path.join("uploads", archivo)
                        if os.path.isfile(ruta_archivo):
                            os.unlink(ruta_archivo)
                            
                init_db()
                st.session_state['logged_in_user'] = None  # Cerrar sesión para obligar a re-ingresar
                st.success("Sistema reiniciado completamente.")
                st.rerun()
            except Exception as e:
                st.error(f"Ocurrió un error al borrar la base de datos: {e}")

    # --- LOGO DE LA EMPRESA (ABAJO) ---
    st.sidebar.markdown("---")
    
    # Mostrar IP en el sidebar para facilitar conexión
    local_ip = get_local_ip()
    st.sidebar.markdown(f"📡 **IP Tablets:**\n`http://{local_ip}:8501`")

    logo_path = os.path.join("img", "logo_jota.png")
    if os.path.exists(logo_path):
        st.sidebar.image(logo_path, width=220)

def login_signup_page():
    """Muestra la página de login/signup."""
    st.title("Sistema de Producción")
    choice = st.sidebar.selectbox("Acceso", ["Login", "SignUp"])
    if choice == "Login":
        st.subheader("Iniciar Sesión")
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type='password')
        if st.button("Login"):
            if login_user(username, password):
                st.session_state['logged_in_user'] = username
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")
    elif choice == "SignUp":
        st.subheader("Crear Nueva Cuenta de Operario")
        new_username = st.text_input("Nuevo Usuario", key="new_user")
        new_password = st.text_input("Contraseña", type='password', key="new_pass")
        if st.button("Crear Cuenta"):
            if new_username and new_password:
                add_userdata(new_username, new_password)
            else:
                st.warning("Por favor, ingresa un nombre de usuario y contraseña.")

def main():
    """Función principal que dirige el flujo de la aplicación."""
    st.set_page_config(page_title="Gestión de Producción", layout="wide")
    init_db() 

    # --- DIAGNOSTIC CODE ---
    st.info("--- INICIO DE DIAGNÓSTICO ---")
    try:
        conn_diag = sqlite3.connect('produccion.db', timeout=10)
        c = conn_diag.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='proyectos'")
        if c.fetchone():
            df_diag = pd.read_sql_query("SELECT * FROM proyectos", conn_diag)
            st.success(f"✅ DIAGNÓSTICO: ¡Conexión exitosa! La tabla 'proyectos' existe y se encontraron {len(df_diag)} registros (proyectos) en ella.")
        else:
            st.warning("🟡 DIAGNÓSTICO: La conexión a la base de datos 'produccion.db' fue exitosa, pero la tabla 'proyectos' NO EXISTE.")
        conn_diag.close()
    except Exception as e:
        st.error(f"❌ DIAGNÓSTICO: ¡ERROR! No se pudo leer la base de datos 'produccion.db'. Razón: {e}")
    st.info("--- FIN DE DIAGNÓSTICO ---")
    # --- END DIAGNOSTIC CODE ---

    # --- AUTO-LOGIN (MODO DESARROLLO) ---
    # Garantiza que exista el usuario 'admin' y lo loguea automáticamente al recargar (F5).
    conn = sqlite3.connect('produccion.db', timeout=30)
    c = conn.cursor()
    try:
        # Asegurar que admin tenga rol de admin
        c.execute("SELECT * FROM usuarios WHERE username='admin'")
        if not c.fetchone():
            c.execute("INSERT INTO usuarios (username, password, rol) VALUES (?, ?, ?)", ('admin', make_hashes('admin'), 'admin'))
        else:
            c.execute("UPDATE usuarios SET rol='admin' WHERE username='admin'")
        
        # Crear usuario ventas para pruebas
        c.execute("INSERT OR IGNORE INTO usuarios (username, password, rol) VALUES (?, ?, ?)", ('ventas', make_hashes('ventas'), 'ventas'))
        
        # Crear usuarios operativos para tablets (Contraseña = Usuario)
        lista_operarios = [
            "IMPRESOR SP1", "IMPRESOR SUPER PRINT", "IMPRESOR FIT 350",
            "JEFE PRODUCCION",
            "CONTROLADOR 1", "CONTROLADOR 2", "CONTROLADOR 3", "CONTROLADOR 4", "CONTROLADOR 5", "CONTROLADOR 6",
            "TROQUELADOR1", "TROQUELADOR 2",
            "DESPACHO 1"
        ]
        for op_user in lista_operarios:
            # Contraseña: minúsculas y espacios reemplazados por guiones
            op_password = op_user.lower().replace(" ", "-")
            c.execute("INSERT OR IGNORE INTO usuarios (username, password, rol) VALUES (?, ?, ?)", (op_user, make_hashes(op_password), 'operario'))
            # Actualizar contraseña por si el usuario ya existía con el formato anterior
            c.execute("UPDATE usuarios SET password = ? WHERE username = ?", (make_hashes(op_password), op_user))

        conn.commit()
    except sqlite3.IntegrityError:
        pass # El usuario ya existe, continuamos
    conn.close()

    if 'logged_in_user' not in st.session_state:
        st.session_state['logged_in_user'] = 'admin'

    if st.session_state['logged_in_user']:
        main_app()
    else:
        login_signup_page()

if __name__ == '__main__':
    main()