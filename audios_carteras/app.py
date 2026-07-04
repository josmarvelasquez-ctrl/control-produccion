import streamlit as st
import sqlite3
import hashlib
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "audios_carteras.db")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
EXTENSIONES_PERMITIDAS = {".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac"}
CREAR_NUEVO = "➕ Crear nuevo..."

# --- AUTENTICACIÓN ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    return make_hashes(password) == hashed_text

def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS carteras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS playbooks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cartera_id INTEGER NOT NULL,
        nombre TEXT NOT NULL,
        FOREIGN KEY (cartera_id) REFERENCES carteras(id) ON DELETE CASCADE,
        UNIQUE(cartera_id, nombre)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS casos_uso (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        playbook_id INTEGER NOT NULL,
        nombre TEXT NOT NULL,
        FOREIGN KEY (playbook_id) REFERENCES playbooks(id) ON DELETE CASCADE,
        UNIQUE(playbook_id, nombre)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS audios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        caso_uso_id INTEGER NOT NULL,
        nombre_original TEXT NOT NULL,
        ruta_archivo TEXT NOT NULL,
        descripcion TEXT,
        subido_por TEXT,
        fecha_subida DATETIME,
        FOREIGN KEY (caso_uso_id) REFERENCES casos_uso(id) ON DELETE CASCADE
    )''')
    conn.commit()
    conn.close()

def add_userdata(username, password):
    conn = get_connection()
    try:
        conn.execute('INSERT INTO usuarios(username, password) VALUES (?,?)', (username, make_hashes(password)))
        conn.commit()
        st.success(f"Usuario '{username}' creado. Ahora inicia sesión.")
    except sqlite3.IntegrityError:
        st.error(f"El usuario '{username}' ya existe.")
    finally:
        conn.close()

def login_user(username, password):
    conn = get_connection()
    c = conn.execute('SELECT password FROM usuarios WHERE username = ?', (username,))
    row = c.fetchone()
    conn.close()
    return bool(row) and check_hashes(password, row[0])

# --- ESTRUCTURA: CARTERAS / PLAYBOOKS / CASOS DE USO ---
def listar_carteras():
    conn = get_connection()
    filas = conn.execute('SELECT id, nombre FROM carteras ORDER BY nombre').fetchall()
    conn.close()
    return {nombre: id_ for id_, nombre in filas}

def crear_cartera(nombre):
    conn = get_connection()
    conn.execute('INSERT INTO carteras(nombre) VALUES (?)', (nombre,))
    conn.commit()
    conn.close()

def listar_playbooks(cartera_id):
    conn = get_connection()
    filas = conn.execute('SELECT id, nombre FROM playbooks WHERE cartera_id = ? ORDER BY nombre', (cartera_id,)).fetchall()
    conn.close()
    return {nombre: id_ for id_, nombre in filas}

def crear_playbook(cartera_id, nombre):
    conn = get_connection()
    conn.execute('INSERT INTO playbooks(cartera_id, nombre) VALUES (?, ?)', (cartera_id, nombre))
    conn.commit()
    conn.close()

def listar_casos_uso(playbook_id):
    conn = get_connection()
    filas = conn.execute('SELECT id, nombre FROM casos_uso WHERE playbook_id = ? ORDER BY nombre', (playbook_id,)).fetchall()
    conn.close()
    return {nombre: id_ for id_, nombre in filas}

def crear_caso_uso(playbook_id, nombre):
    conn = get_connection()
    conn.execute('INSERT INTO casos_uso(playbook_id, nombre) VALUES (?, ?)', (playbook_id, nombre))
    conn.commit()
    conn.close()

def listar_audios(caso_uso_id):
    conn = get_connection()
    filas = conn.execute(
        'SELECT id, nombre_original, ruta_archivo, descripcion, subido_por, fecha_subida '
        'FROM audios WHERE caso_uso_id = ? ORDER BY fecha_subida DESC',
        (caso_uso_id,)
    ).fetchall()
    conn.close()
    columnas = ["id", "nombre_original", "ruta_archivo", "descripcion", "subido_por", "fecha_subida"]
    return [dict(zip(columnas, fila)) for fila in filas]

def agregar_audio(caso_uso_id, nombre_original, ruta_archivo, descripcion, subido_por):
    conn = get_connection()
    conn.execute(
        'INSERT INTO audios(caso_uso_id, nombre_original, ruta_archivo, descripcion, subido_por, fecha_subida) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (caso_uso_id, nombre_original, ruta_archivo, descripcion, subido_por, datetime.now())
    )
    conn.commit()
    conn.close()

def eliminar_audio(audio_id, ruta_archivo):
    conn = get_connection()
    conn.execute('DELETE FROM audios WHERE id = ?', (audio_id,))
    conn.commit()
    conn.close()
    if os.path.exists(ruta_archivo):
        os.remove(ruta_archivo)

# --- SELECTOR CON OPCIÓN DE CREAR SOBRE LA MARCHA ---
def selector_o_crear(label, opciones, key, on_create):
    """opciones: dict {nombre: id}. Devuelve el id elegido, o None si aún no hay selección."""
    # Streamlit no permite tocar el session_state de un widget ya instanciado en el
    # mismo run, así que el valor pendiente se aplica antes de crear el selectbox.
    pendiente_key = f"pendiente_{key}"
    if pendiente_key in st.session_state:
        st.session_state[f"sel_{key}"] = st.session_state.pop(pendiente_key)

    nombres = list(opciones.keys())
    seleccion = st.selectbox(label, nombres + [CREAR_NUEVO], key=f"sel_{key}")
    if seleccion == CREAR_NUEVO:
        nuevo_nombre = st.text_input(f"Nombre de la nueva {label.lower()}", key=f"txt_{key}")
        if st.button(f"Crear {label.lower()}", key=f"btn_{key}"):
            nombre_limpio = nuevo_nombre.strip()
            if not nombre_limpio:
                st.warning("Escribe un nombre antes de crear.")
            elif nombre_limpio in opciones:
                st.warning(f"Ya existe una {label.lower()} con ese nombre.")
            else:
                on_create(nombre_limpio)
                st.session_state[pendiente_key] = nombre_limpio
                st.rerun()
        return None
    return opciones[seleccion]

def ruta_segura(*partes):
    carpeta = os.path.join(UPLOADS_DIR, *[str(p) for p in partes])
    os.makedirs(carpeta, exist_ok=True)
    return carpeta

# --- PÁGINAS ---
def pagina_cargar_audio(username):
    st.subheader("⬆️ Cargar audio")

    carteras = listar_carteras()
    cartera_id = selector_o_crear("Cartera", carteras, "cartera", crear_cartera)
    if cartera_id is None:
        return

    playbooks = listar_playbooks(cartera_id)
    playbook_id = selector_o_crear("PlayBook", playbooks, "playbook", lambda nombre: crear_playbook(cartera_id, nombre))
    if playbook_id is None:
        return

    casos_uso = listar_casos_uso(playbook_id)
    caso_uso_id = selector_o_crear("Caso de uso", casos_uso, "caso_uso", lambda nombre: crear_caso_uso(playbook_id, nombre))
    if caso_uso_id is None:
        return

    st.markdown("---")
    descripcion = st.text_input("Descripción (opcional)", key="descripcion_audio")
    archivo = st.file_uploader(
        "Selecciona el archivo de audio",
        type=[ext.lstrip(".") for ext in EXTENSIONES_PERMITIDAS],
        key="uploader_audio",
    )

    if st.button("Guardar audio", type="primary", disabled=archivo is None):
        extension = os.path.splitext(archivo.name)[1].lower()
        if extension not in EXTENSIONES_PERMITIDAS:
            st.error("Formato de audio no soportado.")
            return
        carpeta_destino = ruta_segura(cartera_id, playbook_id, caso_uso_id)
        nombre_archivo = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{archivo.name}"
        ruta_destino = os.path.join(carpeta_destino, nombre_archivo)
        with open(ruta_destino, "wb") as f:
            f.write(archivo.getbuffer())
        agregar_audio(caso_uso_id, archivo.name, ruta_destino, descripcion, username)
        st.success(f"Audio '{archivo.name}' guardado correctamente.")
        st.rerun()

def pagina_escuchar_audios():
    st.subheader("🎧 Escuchar audios")

    carteras = listar_carteras()
    if not carteras:
        st.info("Todavía no hay carteras creadas. Ve a 'Cargar audio' para crear la primera.")
        return
    cartera_id = carteras[st.selectbox("Cartera", list(carteras.keys()), key="ver_cartera")]

    playbooks = listar_playbooks(cartera_id)
    if not playbooks:
        st.info("Esta cartera todavía no tiene PlayBooks.")
        return
    playbook_id = playbooks[st.selectbox("PlayBook", list(playbooks.keys()), key="ver_playbook")]

    casos_uso = listar_casos_uso(playbook_id)
    if not casos_uso:
        st.info("Este PlayBook todavía no tiene casos de uso.")
        return
    caso_uso_id = casos_uso[st.selectbox("Caso de uso", list(casos_uso.keys()), key="ver_caso_uso")]

    st.markdown("---")
    audios = listar_audios(caso_uso_id)
    if not audios:
        st.info("Todavía no hay audios cargados para este caso de uso.")
        return

    for audio in audios:
        with st.container(border=True):
            st.markdown(f"**{audio['nombre_original']}**")
            if audio["descripcion"]:
                st.caption(audio["descripcion"])
            st.caption(f"Subido por {audio['subido_por']} el {audio['fecha_subida']}")
            if os.path.exists(audio["ruta_archivo"]):
                st.audio(audio["ruta_archivo"])
            else:
                st.warning("El archivo de audio no se encuentra en el servidor.")
            if st.button("🗑️ Eliminar", key=f"del_{audio['id']}"):
                eliminar_audio(audio["id"], audio["ruta_archivo"])
                st.rerun()

def main_app():
    username = st.session_state["logged_in_user"]

    col_h1, col_h2 = st.columns([1, 6])
    with col_h1:
        st.title("🎙️")
    with col_h2:
        st.title("Audios de Carteras, PlayBooks y Casos de Uso")

    st.sidebar.success(f"Usuario: {username}")
    if st.sidebar.button("Cerrar sesión"):
        st.session_state["logged_in_user"] = None
        st.rerun()

    if "pagina_actual" not in st.session_state:
        st.session_state["pagina_actual"] = "Cargar audio"

    if st.sidebar.button("⬆️ Cargar audio", use_container_width=True,
                          type="primary" if st.session_state["pagina_actual"] == "Cargar audio" else "secondary"):
        st.session_state["pagina_actual"] = "Cargar audio"
        st.rerun()
    if st.sidebar.button("🎧 Escuchar audios", use_container_width=True,
                          type="primary" if st.session_state["pagina_actual"] == "Escuchar audios" else "secondary"):
        st.session_state["pagina_actual"] = "Escuchar audios"
        st.rerun()

    if st.session_state["pagina_actual"] == "Cargar audio":
        pagina_cargar_audio(username)
    else:
        pagina_escuchar_audios()

def login_signup_page():
    st.title("🎙️ Audios de Carteras, PlayBooks y Casos de Uso")
    eleccion = st.sidebar.selectbox("Acceso", ["Login", "Crear cuenta"])

    if eleccion == "Login":
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        if st.button("Iniciar sesión", type="primary"):
            if login_user(username, password):
                st.session_state["logged_in_user"] = username
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")
    else:
        nuevo_usuario = st.text_input("Nuevo usuario")
        nueva_password = st.text_input("Nueva contraseña", type="password")
        if st.button("Crear cuenta", type="primary"):
            if nuevo_usuario.strip() and nueva_password:
                add_userdata(nuevo_usuario.strip(), nueva_password)
            else:
                st.warning("Completa usuario y contraseña.")

def main():
    st.set_page_config(page_title="Audios de Carteras", page_icon="🎙️", layout="centered")
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    init_db()

    if "logged_in_user" not in st.session_state:
        st.session_state["logged_in_user"] = None

    if st.session_state["logged_in_user"]:
        main_app()
    else:
        login_signup_page()

if __name__ == "__main__":
    main()
