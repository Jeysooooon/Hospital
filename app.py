import os
from datetime import datetime
from functools import wraps

import mysql.connector
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from werkzeug.security import check_password_hash, generate_password_hash


def load_env_file():
    env_path = ".env"
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


load_env_file()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "prohospital-dev-secret")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Inicia sesion para continuar."
login_manager.login_message_category = "warning"

DB_HOST = os.environ.get("MYSQLHOST", "localhost")
DB_USER = os.environ.get("MYSQLUSER", "root")
DB_PASSWORD = os.environ.get("MYSQLPASSWORD", "")
DB_NAME = os.environ.get("MYSQLDATABASE", "railway")
DB_PORT = int(os.environ.get("MYSQLPORT", 3306))

DIAS_SEMANA = [
    "lunes",
    "martes",
    "miercoles",
    "jueves",
    "viernes",
    "sabado",
    "domingo",
]

schema_ready = False


class SystemUser(UserMixin):
    def __init__(self, user_id, username, nombre, rol, pac_codigo=None, doc_codigo=None):
        self.id = str(user_id)
        self.username = username
        self.nombre = nombre
        self.rol = rol
        self.pac_codigo = pac_codigo
        self.doc_codigo = doc_codigo


def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        port=DB_PORT,
        auth_plugin="mysql_native_password",
    )


def column_exists(cursor, table_name, column_name):
    cursor.execute(f"SHOW COLUMNS FROM {table_name} LIKE %s", (column_name,))
    return cursor.fetchone() is not None


def constraint_exists(cursor, table_name, constraint_name):
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.TABLE_CONSTRAINTS
        WHERE TABLE_SCHEMA = %s
            AND TABLE_NAME = %s
            AND CONSTRAINT_NAME = %s
        LIMIT 1
        """,
        (DB_NAME, table_name, constraint_name),
    )
    return cursor.fetchone() is not None


def ensure_citas_table(conn):
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS citas (
            CitCodigo INT AUTO_INCREMENT PRIMARY KEY,
            PacCodigo INT NOT NULL,
            DocCodigo INT NOT NULL,
            CitFecha DATE NOT NULL,
            CitHora TIME NOT NULL,
            CitEstado VARCHAR(30) NOT NULL DEFAULT 'Programada',
            CitMotivo VARCHAR(150) NOT NULL,
            CitObservaciones TEXT NULL
        )
        """
    )
    conn.commit()
    cursor.close()


def ensure_profile_columns(conn):
    cursor = conn.cursor()
    profile_columns = {
        "PacTipoSangre": "ALTER TABLE pacientes ADD COLUMN PacTipoSangre VARCHAR(10) NULL",
        "PacAlergias": "ALTER TABLE pacientes ADD COLUMN PacAlergias TEXT NULL",
        "PacPeso": "ALTER TABLE pacientes ADD COLUMN PacPeso DECIMAL(5,2) NULL",
    }

    for column_name, statement in profile_columns.items():
        if not column_exists(cursor, "pacientes", column_name):
            cursor.execute(statement)

    conn.commit()
    cursor.close()


def ensure_usuarios_table(conn):
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            UsuCodigo INT AUTO_INCREMENT PRIMARY KEY,
            PacCodigo INT NULL,
            DocCodigo INT NULL,
            UsuNombre VARCHAR(120) NOT NULL,
            UsuUsername VARCHAR(80) NOT NULL UNIQUE,
            UsuCorreo VARCHAR(120) NULL,
            UsuPasswordHash VARCHAR(255) NOT NULL,
            UsuRol ENUM('admin', 'paciente', 'doctor') NOT NULL DEFAULT 'paciente',
            UsuActivo TINYINT(1) NOT NULL DEFAULT 1,
            FechaCreacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_usuarios_pacientes
                FOREIGN KEY (PacCodigo) REFERENCES pacientes(PacCodigo)
                ON DELETE SET NULL,
            CONSTRAINT fk_usuarios_doctores
                FOREIGN KEY (DocCodigo) REFERENCES doctores(DocCodigo)
                ON DELETE SET NULL
        )
        """
    )
    conn.commit()
    cursor.close()


def ensure_usuarios_role_support(conn):
    cursor = conn.cursor()

    if not column_exists(cursor, "usuarios", "DocCodigo"):
        cursor.execute("ALTER TABLE usuarios ADD COLUMN DocCodigo INT NULL AFTER PacCodigo")

    cursor.execute(
        """
        ALTER TABLE usuarios
        MODIFY COLUMN UsuRol ENUM('admin', 'paciente', 'doctor') NOT NULL DEFAULT 'paciente'
        """
    )

    if not constraint_exists(cursor, "usuarios", "fk_usuarios_doctores"):
        cursor.execute(
            """
            ALTER TABLE usuarios
            ADD CONSTRAINT fk_usuarios_doctores
            FOREIGN KEY (DocCodigo) REFERENCES doctores(DocCodigo)
            ON DELETE SET NULL
            """
        )

    conn.commit()
    cursor.close()


def ensure_historial_table(conn):
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS historial_clinico (
            HcCodigo INT AUTO_INCREMENT PRIMARY KEY,
            CitCodigo INT NOT NULL UNIQUE,
            HcDiagnostico TEXT NOT NULL,
            HcTratamiento TEXT NULL,
            HcObservaciones TEXT NULL,
            HcFechaRegistro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_historial_citas
                FOREIGN KEY (CitCodigo) REFERENCES citas(CitCodigo)
                ON DELETE CASCADE
        )
        """
    )
    conn.commit()
    cursor.close()


def ensure_horarios_table(conn):
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS horarios_medicos (
            HorCodigo INT AUTO_INCREMENT PRIMARY KEY,
            DocCodigo INT NOT NULL,
            HorDiaSemana VARCHAR(15) NOT NULL,
            HorHoraInicio TIME NOT NULL,
            HorHoraFin TIME NOT NULL,
            HorActivo TINYINT(1) NOT NULL DEFAULT 1,
            CONSTRAINT fk_horarios_doctores
                FOREIGN KEY (DocCodigo) REFERENCES doctores(DocCodigo)
                ON DELETE CASCADE
        )
        """
    )
    conn.commit()
    cursor.close()


def ensure_default_admin(conn):
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT UsuCodigo
        FROM usuarios
        WHERE UsuRol = 'admin'
        LIMIT 1
        """
    )
    admin = cursor.fetchone()

    if not admin:
        default_username = os.environ.get("DEFAULT_ADMIN_USERNAME", "admin")
        default_password = os.environ.get("DEFAULT_ADMIN_PASSWORD", "Admin123!")
        default_name = os.environ.get("DEFAULT_ADMIN_NAME", "Administrador Principal")
        default_email = os.environ.get("DEFAULT_ADMIN_EMAIL", "admin@prohospital.local")
        cursor.execute(
            """
            INSERT INTO usuarios (
                PacCodigo,
                UsuNombre,
                UsuUsername,
                UsuCorreo,
                UsuPasswordHash,
                UsuRol,
                UsuActivo
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                None,
                default_name,
                default_username,
                default_email,
                generate_password_hash(default_password),
                "admin",
                1,
            ),
        )
        conn.commit()

    cursor.close()


def prepare_database():
    global schema_ready
    if schema_ready:
        return

    conn = get_db_connection()
    try:
        ensure_citas_table(conn)
        ensure_profile_columns(conn)
        ensure_usuarios_table(conn)
        ensure_usuarios_role_support(conn)
        ensure_historial_table(conn)
        ensure_horarios_table(conn)
        ensure_default_admin(conn)
        schema_ready = True
    finally:
        conn.close()


@app.before_request
def bootstrap_database():
    if request.endpoint == "static":
        return
    prepare_database()


def build_user(row):
    if not row:
        return None

    display_name = row["UsuNombre"] or row["UsuUsername"]
    patient_name = (row.get("PacienteNombre") or "").strip()
    doctor_name = (row.get("DoctorNombre") or "").strip()
    if row["UsuRol"] == "paciente" and patient_name:
        display_name = patient_name
    elif row["UsuRol"] == "doctor" and doctor_name:
        display_name = doctor_name

    return SystemUser(
        user_id=row["UsuCodigo"],
        username=row["UsuUsername"],
        nombre=display_name,
        rol=row["UsuRol"],
        pac_codigo=row["PacCodigo"],
        doc_codigo=row.get("DocCodigo"),
    )


@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
            u.UsuCodigo,
            u.PacCodigo,
            u.DocCodigo,
            u.UsuNombre,
            u.UsuUsername,
            u.UsuRol,
            CONCAT(IFNULL(p.PacNombre, ''), ' ', IFNULL(p.PacApellido, '')) AS PacienteNombre,
            CONCAT(IFNULL(d.DocNombre, ''), ' ', IFNULL(d.DocApellido, '')) AS DoctorNombre
        FROM usuarios u
        LEFT JOIN pacientes p ON u.PacCodigo = p.PacCodigo
        LEFT JOIN doctores d ON u.DocCodigo = d.DocCodigo
        WHERE u.UsuCodigo = %s AND u.UsuActivo = 1
        """,
        (user_id,),
    )
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return build_user(row)


def dashboard_endpoint_for_role(role):
    if role == "admin":
        return "admin_dashboard"
    if role == "doctor":
        return "doctor_panel"
    return "mi_panel"


def admin_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if current_user.rol != "admin":
            flash("Esta seccion es solo para administradores.", "danger")
            return redirect(url_for(dashboard_endpoint_for_role(current_user.rol)))
        return view_func(*args, **kwargs)

    return wrapped_view


def patient_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if current_user.rol != "paciente":
            flash("Esta seccion es solo para pacientes.", "danger")
            return redirect(url_for(dashboard_endpoint_for_role(current_user.rol)))
        if not current_user.pac_codigo:
            logout_user()
            flash("Tu usuario no esta vinculado a un paciente. Revisa la tabla usuarios.", "danger")
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    return wrapped_view


def doctor_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if current_user.rol != "doctor":
            flash("Esta seccion es solo para doctores.", "danger")
            return redirect(url_for(dashboard_endpoint_for_role(current_user.rol)))
        if not current_user.doc_codigo:
            logout_user()
            flash("Tu usuario no esta vinculado a un doctor. Revisa la tabla usuarios.", "danger")
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    return wrapped_view


def get_pacientes_doctores(conn):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT PacCodigo, PacNombre, PacApellido
        FROM pacientes
        ORDER BY PacNombre, PacApellido
        """
    )
    pacientes = cursor.fetchall()

    cursor.execute(
        """
        SELECT DocCodigo, DocNombre, DocApellido, DocEspecialidad
        FROM doctores
        ORDER BY DocNombre, DocApellido
        """
    )
    doctores = cursor.fetchall()
    cursor.close()
    return pacientes, doctores


def get_citas_resumen(lista_citas):
    total = len(lista_citas)
    programadas = sum(1 for cita in lista_citas if cita["CitEstado"] == "Programada")
    confirmadas = sum(1 for cita in lista_citas if cita["CitEstado"] == "Confirmada")
    completadas = sum(1 for cita in lista_citas if cita["CitEstado"] == "Completada")
    return {
        "total": total,
        "programadas": programadas,
        "confirmadas": confirmadas,
        "completadas": completadas,
    }


def username_exists(conn, username, exclude_user_id=None):
    cursor = conn.cursor()
    if exclude_user_id:
        cursor.execute(
            """
            SELECT 1
            FROM usuarios
            WHERE UsuUsername = %s AND UsuCodigo <> %s
            LIMIT 1
            """,
            (username, exclude_user_id),
        )
    else:
        cursor.execute(
            """
            SELECT 1
            FROM usuarios
            WHERE UsuUsername = %s
            LIMIT 1
            """,
            (username,),
        )
    exists = cursor.fetchone() is not None
    cursor.close()
    return exists


def doctor_schedule_message(conn, doc_codigo, fecha, hora, cita_excluir=None):
    dia_semana = DIAS_SEMANA[datetime.strptime(fecha, "%Y-%m-%d").weekday()]
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM horarios_medicos
        WHERE DocCodigo = %s
            AND HorActivo = 1
            AND LOWER(HorDiaSemana) = %s
            AND %s >= HorHoraInicio
            AND %s < HorHoraFin
        """,
        (doc_codigo, dia_semana, hora, hora),
    )
    horario = cursor.fetchone()

    if horario["total"] == 0:
        cursor.close()
        return (
            False,
            "La cita no se puede agendar porque el doctor no tiene horario registrado para ese dia y hora.",
        )

    query = """
        SELECT COUNT(*) AS total
        FROM citas
        WHERE DocCodigo = %s
            AND CitFecha = %s
            AND CitHora = %s
            AND CitEstado <> 'Cancelada'
    """
    params = [doc_codigo, fecha, hora]
    if cita_excluir:
        query += " AND CitCodigo <> %s"
        params.append(cita_excluir)

    cursor.execute(query, tuple(params))
    conflicto = cursor.fetchone()
    cursor.close()

    if conflicto["total"] > 0:
        return False, "Ese doctor ya tiene una cita programada en esa fecha y hora."

    return True, None


def get_patient_profile(conn, pac_codigo):
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
            PacCodigo,
            PacNombre,
            PacApellido,
            PacDNI,
            PacTelefono,
            PacDireccion,
            PacTipoSangre,
            PacAlergias,
            PacPeso
        FROM pacientes
        WHERE PacCodigo = %s
        """,
        (pac_codigo,),
    )
    profile = cursor.fetchone()
    cursor.close()
    return profile


def get_patient_appointments(conn, pac_codigo):
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
            c.CitCodigo,
            c.CitFecha,
            c.CitHora,
            c.CitEstado,
            c.CitMotivo,
            c.CitObservaciones,
            CONCAT(d.DocNombre, ' ', d.DocApellido) AS DoctorNombre,
            d.DocEspecialidad,
            hc.HcDiagnostico
        FROM citas c
        INNER JOIN doctores d ON c.DocCodigo = d.DocCodigo
        LEFT JOIN historial_clinico hc ON c.CitCodigo = hc.CitCodigo
        WHERE c.PacCodigo = %s
        ORDER BY c.CitFecha DESC, c.CitHora DESC
        """
        ,
        (pac_codigo,),
    )
    citas = cursor.fetchall()
    cursor.close()
    return citas


def get_patient_history(conn, pac_codigo):
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
            hc.HcCodigo,
            hc.HcDiagnostico,
            hc.HcTratamiento,
            hc.HcObservaciones,
            hc.HcFechaRegistro,
            c.CitFecha,
            c.CitHora,
            c.CitMotivo,
            CONCAT(d.DocNombre, ' ', d.DocApellido) AS DoctorNombre,
            d.DocEspecialidad
        FROM historial_clinico hc
        INNER JOIN citas c ON hc.CitCodigo = c.CitCodigo
        INNER JOIN doctores d ON c.DocCodigo = d.DocCodigo
        WHERE c.PacCodigo = %s
        ORDER BY c.CitFecha DESC, c.CitHora DESC
        """
        ,
        (pac_codigo,),
    )
    historial = cursor.fetchall()
    cursor.close()
    return historial


def get_doctor_profile(conn, doc_codigo):
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
            DocCodigo,
            DocNombre,
            DocApellido,
            DocEspecialidad,
            DocTelefono,
            DocCorreo
        FROM doctores
        WHERE DocCodigo = %s
        """,
        (doc_codigo,),
    )
    doctor = cursor.fetchone()
    cursor.close()
    return doctor


def get_doctor_appointments(conn, doc_codigo, limit=None):
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT
            c.CitCodigo,
            c.PacCodigo,
            c.CitFecha,
            c.CitHora,
            c.CitEstado,
            c.CitMotivo,
            c.CitObservaciones,
            CONCAT(p.PacNombre, ' ', p.PacApellido) AS PacienteNombre,
            p.PacTelefono,
            p.PacTipoSangre,
            hc.HcCodigo,
            hc.HcDiagnostico
        FROM citas c
        INNER JOIN pacientes p ON c.PacCodigo = p.PacCodigo
        LEFT JOIN historial_clinico hc ON c.CitCodigo = hc.CitCodigo
        WHERE c.DocCodigo = %s
        ORDER BY c.CitFecha ASC, c.CitHora ASC
    """
    params = [doc_codigo]
    if limit:
        query += " LIMIT %s"
        params.append(limit)

    cursor.execute(query, tuple(params))
    citas = cursor.fetchall()
    cursor.close()
    return citas


def get_doctor_schedule_entries(conn, doc_codigo):
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
            HorCodigo,
            HorDiaSemana,
            HorHoraInicio,
            HorHoraFin,
            HorActivo
        FROM horarios_medicos
        WHERE DocCodigo = %s
        ORDER BY
            CASE LOWER(HorDiaSemana)
                WHEN 'lunes' THEN 1
                WHEN 'martes' THEN 2
                WHEN 'miercoles' THEN 3
                WHEN 'jueves' THEN 4
                WHEN 'viernes' THEN 5
                WHEN 'sabado' THEN 6
                WHEN 'domingo' THEN 7
                ELSE 99
            END,
            HorHoraInicio
        """,
        (doc_codigo,),
    )
    horarios = cursor.fetchall()
    cursor.close()
    return horarios


def get_doctor_patients(conn, doc_codigo, search_term=""):
    cursor = conn.cursor(dictionary=True)
    pattern = f"%{search_term}%"
    cursor.execute(
        """
        SELECT
            p.PacCodigo,
            p.PacNombre,
            p.PacApellido,
            p.PacDNI,
            p.PacTelefono,
            p.PacTipoSangre,
            p.PacAlergias,
            p.PacPeso,
            COUNT(DISTINCT c.CitCodigo) AS TotalCitas,
            MAX(c.CitFecha) AS UltimaCita
        FROM pacientes p
        INNER JOIN citas c ON p.PacCodigo = c.PacCodigo
        WHERE c.DocCodigo = %s
            AND (
                %s = ''
                OR p.PacNombre LIKE %s
                OR p.PacApellido LIKE %s
                OR p.PacDNI LIKE %s
            )
        GROUP BY
            p.PacCodigo,
            p.PacNombre,
            p.PacApellido,
            p.PacDNI,
            p.PacTelefono,
            p.PacTipoSangre,
            p.PacAlergias,
            p.PacPeso
        ORDER BY UltimaCita DESC, p.PacNombre, p.PacApellido
        """,
        (doc_codigo, search_term, pattern, pattern, pattern),
    )
    pacientes = cursor.fetchall()
    cursor.close()
    return pacientes


def get_doctor_patient_profile(conn, doc_codigo, pac_codigo):
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
            p.PacCodigo,
            p.PacNombre,
            p.PacApellido,
            p.PacDNI,
            p.PacTelefono,
            p.PacDireccion,
            p.PacTipoSangre,
            p.PacAlergias,
            p.PacPeso,
            COUNT(DISTINCT c.CitCodigo) AS TotalCitasConDoctor,
            MAX(c.CitFecha) AS UltimaCitaConDoctor
        FROM pacientes p
        INNER JOIN citas c ON p.PacCodigo = c.PacCodigo
        WHERE p.PacCodigo = %s
            AND c.DocCodigo = %s
        GROUP BY
            p.PacCodigo,
            p.PacNombre,
            p.PacApellido,
            p.PacDNI,
            p.PacTelefono,
            p.PacDireccion,
            p.PacTipoSangre,
            p.PacAlergias,
            p.PacPeso
        """,
        (pac_codigo, doc_codigo),
    )
    paciente = cursor.fetchone()
    cursor.close()
    return paciente


def get_patient_consultations(conn, pac_codigo):
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
            c.CitCodigo,
            c.CitFecha,
            c.CitHora,
            c.CitEstado,
            c.CitMotivo,
            hc.HcCodigo,
            hc.HcDiagnostico,
            hc.HcTratamiento,
            hc.HcObservaciones,
            CONCAT(d.DocNombre, ' ', d.DocApellido) AS DoctorNombre,
            d.DocEspecialidad
        FROM citas c
        INNER JOIN doctores d ON c.DocCodigo = d.DocCodigo
        LEFT JOIN historial_clinico hc ON c.CitCodigo = hc.CitCodigo
        WHERE c.PacCodigo = %s
        ORDER BY c.CitFecha DESC, c.CitHora DESC
        """,
        (pac_codigo,),
    )
    consultas = cursor.fetchall()
    cursor.close()
    return consultas


def get_time_minutes(value):
    if hasattr(value, "hour"):
        return value.hour * 60 + value.minute
    if hasattr(value, "total_seconds"):
        total_seconds = int(value.total_seconds())
        return total_seconds // 60
    hours, minutes = str(value).split(":")[:2]
    return int(hours) * 60 + int(minutes)


def get_doctor_current_appointment(citas):
    today = datetime.now().date()
    citas_hoy = [
        cita
        for cita in citas
        if cita["CitFecha"] == today and cita["CitEstado"] != "Cancelada"
    ]
    if not citas_hoy:
        return None

    now_minutes = datetime.now().hour * 60 + datetime.now().minute
    futuras = [cita for cita in citas_hoy if get_time_minutes(cita["CitHora"]) >= now_minutes]
    if futuras:
        return futuras[0]
    return citas_hoy[-1]


def get_admin_metrics(conn):
    cursor = conn.cursor(dictionary=True)
    metrics = {}

    counters = {
        "total_especialidades": "SELECT COUNT(*) AS total FROM especialidad",
        "total_doctores": "SELECT COUNT(*) AS total FROM doctores",
        "total_pacientes": "SELECT COUNT(*) AS total FROM pacientes",
        "total_citas": "SELECT COUNT(*) AS total FROM citas",
        "total_usuarios": "SELECT COUNT(*) AS total FROM usuarios",
        "total_historiales": "SELECT COUNT(*) AS total FROM historial_clinico",
    }

    for key, query in counters.items():
        cursor.execute(query)
        metrics[key] = cursor.fetchone()["total"]

    cursor.execute(
        """
        SELECT
            c.CitCodigo,
            c.CitFecha,
            c.CitHora,
            c.CitEstado,
            CONCAT(p.PacNombre, ' ', p.PacApellido) AS PacienteNombre,
            CONCAT(d.DocNombre, ' ', d.DocApellido) AS DoctorNombre
        FROM citas c
        INNER JOIN pacientes p ON c.PacCodigo = p.PacCodigo
        INNER JOIN doctores d ON c.DocCodigo = d.DocCodigo
        ORDER BY c.CitFecha ASC, c.CitHora ASC
        LIMIT 5
        """
    )
    metrics["proximas_citas"] = cursor.fetchall()
    cursor.close()
    return metrics


@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for(dashboard_endpoint_for_role(current_user.rol)))
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for(dashboard_endpoint_for_role(current_user.rol)))

    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                u.UsuCodigo,
                u.PacCodigo,
                u.DocCodigo,
                u.UsuNombre,
                u.UsuUsername,
                u.UsuCorreo,
                u.UsuPasswordHash,
                u.UsuRol,
                CONCAT(IFNULL(p.PacNombre, ''), ' ', IFNULL(p.PacApellido, '')) AS PacienteNombre,
                CONCAT(IFNULL(d.DocNombre, ''), ' ', IFNULL(d.DocApellido, '')) AS DoctorNombre
            FROM usuarios u
            LEFT JOIN pacientes p ON u.PacCodigo = p.PacCodigo
            LEFT JOIN doctores d ON u.DocCodigo = d.DocCodigo
            WHERE u.UsuUsername = %s AND u.UsuActivo = 1
            LIMIT 1
            """,
            (username,),
        )
        user_row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not user_row or not check_password_hash(user_row["UsuPasswordHash"], password):
            flash("Usuario o contrasena incorrectos.", "danger")
            return render_template("auth/login.html")

        login_user(build_user(user_row))
        flash("Sesion iniciada correctamente.", "success")
        next_page = request.args.get("next")
        if next_page:
            return redirect(next_page)
        return redirect(url_for(dashboard_endpoint_for_role(user_row["UsuRol"])))

    return render_template("auth/login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesion cerrada correctamente.", "info")
    return redirect(url_for("login"))


@app.route("/admin/")
@login_required
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    metrics = get_admin_metrics(conn)
    conn.close()
    return render_template("admin/dashboard.html", metrics=metrics)


@app.route("/mi-panel")
@login_required
@patient_required
def mi_panel():
    conn = get_db_connection()
    profile = get_patient_profile(conn, current_user.pac_codigo)
    citas = get_patient_appointments(conn, current_user.pac_codigo)
    historial = get_patient_history(conn, current_user.pac_codigo)
    conn.close()

    return render_template(
        "paciente/dashboard.html",
        profile=profile,
        citas=citas[:5],
        historial=historial[:3],
    )


@app.route("/mi-citas")
@login_required
@patient_required
def mis_citas():
    conn = get_db_connection()
    citas = get_patient_appointments(conn, current_user.pac_codigo)
    conn.close()
    return render_template("paciente/citas.html", citas=citas)


@app.route("/mi-citas/agendar", methods=["GET", "POST"])
@login_required
@patient_required
def mis_citas_agendar():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT DocCodigo, DocNombre, DocApellido, DocEspecialidad
        FROM doctores
        ORDER BY DocNombre, DocApellido
        """
    )
    doctores = cursor.fetchall()
    cursor.close()

    if request.method == "POST":
        doctor = request.form["DocCodigo"]
        fecha = request.form["CitFecha"]
        hora = request.form["CitHora"]
        motivo = request.form["CitMotivo"]
        observaciones = request.form["CitObservaciones"]

        disponible, mensaje = doctor_schedule_message(conn, doctor, fecha, hora)
        if not disponible:
            flash(mensaje, "danger")
            conn.close()
            return render_template("paciente/agendar_cita.html", doctores=doctores)

        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO citas (
                PacCodigo,
                DocCodigo,
                CitFecha,
                CitHora,
                CitEstado,
                CitMotivo,
                CitObservaciones
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                current_user.pac_codigo,
                doctor,
                fecha,
                hora,
                "Programada",
                motivo,
                observaciones,
            ),
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash("Tu cita fue agendada correctamente.", "success")
        return redirect(url_for("mis_citas"))

    conn.close()
    return render_template("paciente/agendar_cita.html", doctores=doctores)


@app.route("/mi-perfil", methods=["GET", "POST"])
@login_required
@patient_required
def mi_perfil():
    conn = get_db_connection()

    if request.method == "POST":
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE pacientes
            SET
                PacNombre = %s,
                PacApellido = %s,
                PacDNI = %s,
                PacTelefono = %s,
                PacDireccion = %s,
                PacTipoSangre = %s,
                PacAlergias = %s,
                PacPeso = %s
            WHERE PacCodigo = %s
            """,
            (
                request.form["PacNombre"],
                request.form["PacApellido"],
                request.form["PacDNI"],
                request.form["PacTelefono"],
                request.form["PacDireccion"],
                request.form["PacTipoSangre"],
                request.form["PacAlergias"],
                request.form["PacPeso"] or None,
                current_user.pac_codigo,
            ),
        )
        conn.commit()
        cursor.close()
        flash("Tu perfil fue actualizado.", "success")

    profile = get_patient_profile(conn, current_user.pac_codigo)
    conn.close()
    return render_template("paciente/perfil.html", profile=profile)


@app.route("/mi-historial")
@login_required
@patient_required
def mi_historial():
    conn = get_db_connection()
    historial = get_patient_history(conn, current_user.pac_codigo)
    conn.close()
    return render_template("paciente/historial.html", historial=historial)


@app.route("/doctor/")
@login_required
@doctor_required
def doctor_panel():
    conn = get_db_connection()
    doctor = get_doctor_profile(conn, current_user.doc_codigo)
    citas = get_doctor_appointments(conn, current_user.doc_codigo)
    horarios = get_doctor_schedule_entries(conn, current_user.doc_codigo)
    pacientes = get_doctor_patients(conn, current_user.doc_codigo)
    conn.close()

    citas_hoy = [cita for cita in citas if cita["CitFecha"] == datetime.now().date()]
    metrics = {
        "total_citas": len(citas),
        "citas_hoy": len(citas_hoy),
        "pacientes_unicos": len({cita["PacCodigo"] for cita in citas}),
        "horarios_activos": len([horario for horario in horarios if horario["HorActivo"]]),
        "historiales_pendientes": len(
            [
                cita
                for cita in citas
                if cita["CitEstado"] != "Cancelada" and not cita["HcCodigo"]
            ]
        ),
    }

    return render_template(
        "doctor/dashboard.html",
        doctor=doctor,
        metrics=metrics,
        citas=citas[:5],
        horarios=horarios[:4],
        pacientes=pacientes[:5],
        cita_actual=get_doctor_current_appointment(citas),
    )


@app.route("/doctor/agenda")
@login_required
@doctor_required
def doctor_agenda():
    conn = get_db_connection()
    citas = get_doctor_appointments(conn, current_user.doc_codigo)
    conn.close()
    return render_template(
        "doctor/agenda.html",
        lista_citas=citas,
        resumen=get_citas_resumen(citas),
        cita_actual=get_doctor_current_appointment(citas),
    )


@app.route("/doctor/horarios", methods=["GET", "POST"])
@login_required
@doctor_required
def doctor_horarios():
    conn = get_db_connection()

    if request.method == "POST":
        dia_semana = request.form["HorDiaSemana"].lower()
        hora_inicio = request.form["HorHoraInicio"]
        hora_fin = request.form["HorHoraFin"]

        if hora_inicio >= hora_fin:
            flash("La hora de inicio debe ser menor que la hora de fin.", "danger")
        else:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO horarios_medicos (
                    DocCodigo,
                    HorDiaSemana,
                    HorHoraInicio,
                    HorHoraFin,
                    HorActivo
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (current_user.doc_codigo, dia_semana, hora_inicio, hora_fin, 1),
            )
            conn.commit()
            cursor.close()
            conn.close()
            flash("Tu horario fue actualizado.", "success")
            return redirect(url_for("doctor_horarios"))

    doctor = get_doctor_profile(conn, current_user.doc_codigo)
    horarios = get_doctor_schedule_entries(conn, current_user.doc_codigo)
    conn.close()
    return render_template("doctor/horarios.html", doctor=doctor, horarios=horarios, dias=DIAS_SEMANA)


@app.route("/doctor/horarios/eliminar/<string:codigo>", methods=["POST"])
@login_required
@doctor_required
def doctor_horarios_eliminar(codigo):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM horarios_medicos WHERE HorCodigo = %s AND DocCodigo = %s",
        (codigo, current_user.doc_codigo),
    )
    conn.commit()
    cursor.close()
    conn.close()
    flash("Bloque de horario eliminado.", "info")
    return redirect(url_for("doctor_horarios"))


@app.route("/doctor/pacientes")
@login_required
@doctor_required
def doctor_pacientes():
    search = request.args.get("q", "").strip()
    conn = get_db_connection()
    pacientes = get_doctor_patients(conn, current_user.doc_codigo, search)
    conn.close()
    return render_template("doctor/pacientes.html", pacientes=pacientes, search=search)


@app.route("/doctor/pacientes/<string:codigo>")
@login_required
@doctor_required
def doctor_paciente_detalle(codigo):
    conn = get_db_connection()
    paciente = get_doctor_patient_profile(conn, current_user.doc_codigo, codigo)
    if not paciente:
        conn.close()
        flash("No tienes acceso a ese paciente o aun no tiene citas contigo.", "danger")
        return redirect(url_for("doctor_pacientes"))

    consultas = get_patient_consultations(conn, codigo)
    conn.close()
    return render_template(
        "doctor/paciente_detalle.html",
        paciente=paciente,
        consultas=consultas,
    )


# ==========================================
# CRUD 1: ESPECIALIDAD
# ==========================================
@app.route("/especialidad/")
@login_required
@admin_required
def especialidad_index():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM especialidad")
    datos = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("especialidad/index.html", lista_especialidades=datos)


@app.route("/especialidad/agregar", methods=["GET", "POST"])
@login_required
@admin_required
def especialidad_agregar():
    if request.method == "POST":
        conn = get_db_connection()
        cursor = conn.cursor()
        nombre = request.form["EspNombre"]
        descripcion = request.form["EspDescripcion"]
        cursor.execute(
            "INSERT INTO especialidad (EspNombre, EspDescripcion) VALUES (%s, %s)",
            (nombre, descripcion),
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash("Especialidad agregada correctamente.", "success")
        return redirect(url_for("especialidad_index"))
    return render_template("especialidad/agregar.html")


@app.route("/especialidad/editar/<string:codigo>", methods=["GET", "POST"])
@login_required
@admin_required
def especialidad_editar(codigo):
    if request.method == "GET":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM especialidad WHERE EspCodigo = %s", (codigo,))
        especialidad = cursor.fetchone()
        cursor.close()
        conn.close()
        return render_template("especialidad/editar.html", especialidad=especialidad)

    conn = get_db_connection()
    cursor = conn.cursor()
    nombre = request.form["EspNombre"]
    descripcion = request.form["EspDescripcion"]
    cursor.execute(
        "UPDATE especialidad SET EspNombre=%s, EspDescripcion=%s WHERE EspCodigo=%s",
        (nombre, descripcion, codigo),
    )
    conn.commit()
    cursor.close()
    conn.close()
    flash("Especialidad actualizada.", "success")
    return redirect(url_for("especialidad_index"))


@app.route("/especialidad/eliminar/<string:codigo>", methods=["GET", "POST"])
@login_required
@admin_required
def especialidad_eliminar(codigo):
    if request.method == "GET":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM especialidad WHERE EspCodigo = %s", (codigo,))
        especialidad = cursor.fetchone()
        cursor.close()
        conn.close()
        return render_template("especialidad/eliminar.html", especialidad=especialidad)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM especialidad WHERE EspCodigo=%s", (codigo,))
    conn.commit()
    cursor.close()
    conn.close()
    flash("Especialidad eliminada.", "info")
    return redirect(url_for("especialidad_index"))


# ==========================================
# CRUD 2: DOCTORES
# ==========================================
@app.route("/doctores/")
@login_required
@admin_required
def doctores_index():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
            d.DocCodigo,
            d.DocNombre,
            d.DocApellido,
            d.DocEspecialidad,
            d.DocTelefono,
            d.DocCorreo,
            u.UsuCodigo,
            u.UsuUsername
        FROM doctores d
        LEFT JOIN usuarios u ON d.DocCodigo = u.DocCodigo AND u.UsuRol = 'doctor'
        ORDER BY d.DocNombre, d.DocApellido
        """
    )
    datos = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("doctores/index.html", lista_doctores=datos)


@app.route("/doctores/agregar", methods=["GET", "POST"])
@login_required
@admin_required
def doctores_agregar():
    if request.method == "POST":
        conn = get_db_connection()
        cursor = conn.cursor()
        nombre = request.form["DocNombre"]
        apellido = request.form["DocApellido"]
        especialidad = request.form["DocEspecialidad"]
        telefono = request.form["DocTelefono"]
        correo = request.form["DocCorreo"]
        usuario = request.form["UsuUsername"].strip()
        correo_usuario = request.form["UsuCorreo"].strip()
        password = request.form["UsuPassword"]

        if (usuario and not password) or (password and not usuario):
            cursor.close()
            conn.close()
            flash("Para crear el acceso del doctor debes indicar usuario y contrasena.", "danger")
            return render_template("doctores/agregar.html")

        if usuario and username_exists(conn, usuario):
            cursor.close()
            conn.close()
            flash("Ese nombre de usuario ya esta en uso.", "danger")
            return render_template("doctores/agregar.html")

        cursor.execute(
            """
            INSERT INTO doctores (
                DocNombre,
                DocApellido,
                DocEspecialidad,
                DocTelefono,
                DocCorreo
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (nombre, apellido, especialidad, telefono, correo),
        )
        doc_codigo = cursor.lastrowid

        if usuario and password:
            cursor.execute(
                """
                INSERT INTO usuarios (
                    PacCodigo,
                    DocCodigo,
                    UsuNombre,
                    UsuUsername,
                    UsuCorreo,
                    UsuPasswordHash,
                    UsuRol,
                    UsuActivo
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    None,
                    doc_codigo,
                    f"{nombre} {apellido}",
                    usuario,
                    correo_usuario or None,
                    generate_password_hash(password),
                    "doctor",
                    1,
                ),
            )

        conn.commit()
        cursor.close()
        conn.close()
        flash("Doctor agregado correctamente.", "success")
        return redirect(url_for("doctores_index"))
    return render_template("doctores/agregar.html")


@app.route("/doctores/editar/<string:codigo>", methods=["GET", "POST"])
@login_required
@admin_required
def doctores_editar(codigo):
    if request.method == "GET":
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                d.DocCodigo,
                d.DocNombre,
                d.DocApellido,
                d.DocEspecialidad,
                d.DocTelefono,
                d.DocCorreo,
                u.UsuCodigo,
                u.UsuUsername,
                IFNULL(u.UsuCorreo, '') AS UsuCorreo
            FROM doctores d
            LEFT JOIN usuarios u ON d.DocCodigo = u.DocCodigo AND u.UsuRol = 'doctor'
            WHERE d.DocCodigo = %s
            LIMIT 1
            """,
            (codigo,),
        )
        doctor = cursor.fetchone()
        cursor.close()
        conn.close()
        return render_template("doctores/editar.html", doctor=doctor)

    conn = get_db_connection()
    cursor = conn.cursor()
    nombre = request.form["DocNombre"]
    apellido = request.form["DocApellido"]
    especialidad = request.form["DocEspecialidad"]
    telefono = request.form["DocTelefono"]
    correo = request.form["DocCorreo"]
    usu_codigo = request.form["UsuCodigo"] or None
    usuario = request.form["UsuUsername"].strip()
    correo_usuario = request.form["UsuCorreo"].strip()
    password = request.form["UsuPassword"]

    if (usuario and not usu_codigo and not password) or (password and not usuario):
        cursor.close()
        conn.close()
        flash("Para crear el acceso del doctor debes indicar usuario y contrasena.", "danger")
        return redirect(url_for("doctores_editar", codigo=codigo))

    if usuario and username_exists(conn, usuario, usu_codigo):
        cursor.close()
        conn.close()
        flash("Ese nombre de usuario ya esta en uso.", "danger")
        return redirect(url_for("doctores_editar", codigo=codigo))

    cursor.execute(
        """
        UPDATE doctores
        SET
            DocNombre = %s,
            DocApellido = %s,
            DocEspecialidad = %s,
            DocTelefono = %s,
            DocCorreo = %s
        WHERE DocCodigo = %s
        """,
        (nombre, apellido, especialidad, telefono, correo, codigo),
    )

    if usu_codigo and usuario:
        if password:
            cursor.execute(
                """
                UPDATE usuarios
                SET
                    UsuNombre = %s,
                    UsuUsername = %s,
                    UsuCorreo = %s,
                    UsuPasswordHash = %s
                WHERE UsuCodigo = %s
                """,
                (
                    f"{nombre} {apellido}",
                    usuario,
                    correo_usuario or None,
                    generate_password_hash(password),
                    usu_codigo,
                ),
            )
        else:
            cursor.execute(
                """
                UPDATE usuarios
                SET
                    UsuNombre = %s,
                    UsuUsername = %s,
                    UsuCorreo = %s
                WHERE UsuCodigo = %s
                """,
                (f"{nombre} {apellido}", usuario, correo_usuario or None, usu_codigo),
            )
    elif usuario and password:
        cursor.execute(
            """
            INSERT INTO usuarios (
                PacCodigo,
                DocCodigo,
                UsuNombre,
                UsuUsername,
                UsuCorreo,
                UsuPasswordHash,
                UsuRol,
                UsuActivo
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                None,
                codigo,
                f"{nombre} {apellido}",
                usuario,
                correo_usuario or None,
                generate_password_hash(password),
                "doctor",
                1,
            ),
        )

    conn.commit()
    cursor.close()
    conn.close()
    flash("Doctor actualizado.", "success")
    return redirect(url_for("doctores_index"))


@app.route("/doctores/eliminar/<string:codigo>", methods=["GET", "POST"])
@login_required
@admin_required
def doctores_eliminar(codigo):
    if request.method == "GET":
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                DocCodigo,
                DocNombre,
                DocApellido,
                DocEspecialidad
            FROM doctores
            WHERE DocCodigo = %s
            """,
            (codigo,),
        )
        doctor = cursor.fetchone()
        cursor.close()
        conn.close()
        return render_template("doctores/eliminar.html", doctor=doctor)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM usuarios WHERE DocCodigo = %s", (codigo,))
    cursor.execute("DELETE FROM doctores WHERE DocCodigo=%s", (codigo,))
    conn.commit()
    cursor.close()
    conn.close()
    flash("Doctor eliminado.", "info")
    return redirect(url_for("doctores_index"))


# ==========================================
# CRUD 3: PACIENTES
# ==========================================
@app.route("/pacientes/")
@login_required
@admin_required
def pacientes_index():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            PacCodigo,
            PacNombre,
            PacApellido,
            PacDNI,
            PacTelefono,
            PacDireccion,
            PacTipoSangre,
            PacPeso
        FROM pacientes
        """
    )
    datos = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("pacientes/index.html", lista_pacientes=datos)


@app.route("/pacientes/agregar", methods=["GET", "POST"])
@login_required
@admin_required
def pacientes_agregar():
    if request.method == "POST":
        conn = get_db_connection()
        cursor = conn.cursor()
        nombre = request.form["PacNombre"]
        apellido = request.form["PacApellido"]
        dni = request.form["PacDNI"]
        telefono = request.form["PacTelefono"]
        direccion = request.form["PacDireccion"]
        tipo_sangre = request.form["PacTipoSangre"]
        alergias = request.form["PacAlergias"]
        peso = request.form["PacPeso"] or None
        usuario = request.form["UsuUsername"].strip()
        correo = request.form["UsuCorreo"].strip()
        password = request.form["UsuPassword"]

        if usuario and username_exists(conn, usuario):
            cursor.close()
            conn.close()
            flash("Ese nombre de usuario ya esta en uso.", "danger")
            return render_template("pacientes/agregar.html")

        cursor.execute(
            """
            INSERT INTO pacientes (
                PacNombre,
                PacApellido,
                PacDNI,
                PacTelefono,
                PacDireccion,
                PacTipoSangre,
                PacAlergias,
                PacPeso
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (nombre, apellido, dni, telefono, direccion, tipo_sangre, alergias, peso),
        )
        pac_codigo = cursor.lastrowid

        if usuario and password:
            cursor.execute(
                """
                INSERT INTO usuarios (
                    PacCodigo,
                    UsuNombre,
                    UsuUsername,
                    UsuCorreo,
                    UsuPasswordHash,
                    UsuRol,
                    UsuActivo
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    pac_codigo,
                    f"{nombre} {apellido}",
                    usuario,
                    correo or None,
                    generate_password_hash(password),
                    "paciente",
                    1,
                ),
            )

        conn.commit()
        cursor.close()
        conn.close()
        flash("Paciente agregado correctamente.", "success")
        return redirect(url_for("pacientes_index"))

    return render_template("pacientes/agregar.html")


@app.route("/pacientes/editar/<string:codigo>", methods=["GET", "POST"])
@login_required
@admin_required
def pacientes_editar(codigo):
    conn = get_db_connection()

    if request.method == "GET":
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                PacCodigo,
                PacNombre,
                PacApellido,
                PacDNI,
                PacTelefono,
                PacDireccion,
                PacTipoSangre,
                PacAlergias,
                PacPeso
            FROM pacientes
            WHERE PacCodigo = %s
            """,
            (codigo,),
        )
        paciente = cursor.fetchone()
        cursor.execute(
            """
            SELECT
                UsuCodigo,
                UsuUsername,
                IFNULL(UsuCorreo, '')
            FROM usuarios
            WHERE PacCodigo = %s
            LIMIT 1
            """,
            (codigo,),
        )
        usuario = cursor.fetchone()
        cursor.close()
        conn.close()
        return render_template("pacientes/editar.html", paciente=paciente, usuario=usuario)

    cursor = conn.cursor()
    nombre = request.form["PacNombre"]
    apellido = request.form["PacApellido"]
    dni = request.form["PacDNI"]
    telefono = request.form["PacTelefono"]
    direccion = request.form["PacDireccion"]
    tipo_sangre = request.form["PacTipoSangre"]
    alergias = request.form["PacAlergias"]
    peso = request.form["PacPeso"] or None
    usu_codigo = request.form["UsuCodigo"] or None
    usuario = request.form["UsuUsername"].strip()
    correo = request.form["UsuCorreo"].strip()
    password = request.form["UsuPassword"]

    if usuario and username_exists(conn, usuario, usu_codigo):
        cursor.close()
        conn.close()
        flash("Ese nombre de usuario ya esta en uso.", "danger")
        return redirect(url_for("pacientes_editar", codigo=codigo))

    cursor.execute(
        """
        UPDATE pacientes
        SET
            PacNombre = %s,
            PacApellido = %s,
            PacDNI = %s,
            PacTelefono = %s,
            PacDireccion = %s,
            PacTipoSangre = %s,
            PacAlergias = %s,
            PacPeso = %s
        WHERE PacCodigo = %s
        """,
        (nombre, apellido, dni, telefono, direccion, tipo_sangre, alergias, peso, codigo),
    )

    if usu_codigo and usuario:
        if password:
            cursor.execute(
                """
                UPDATE usuarios
                SET
                    UsuNombre = %s,
                    UsuUsername = %s,
                    UsuCorreo = %s,
                    UsuPasswordHash = %s
                WHERE UsuCodigo = %s
                """,
                (
                    f"{nombre} {apellido}",
                    usuario,
                    correo or None,
                    generate_password_hash(password),
                    usu_codigo,
                ),
            )
        else:
            cursor.execute(
                """
                UPDATE usuarios
                SET
                    UsuNombre = %s,
                    UsuUsername = %s,
                    UsuCorreo = %s
                WHERE UsuCodigo = %s
                """,
                (f"{nombre} {apellido}", usuario, correo or None, usu_codigo),
            )
    elif usuario and password:
        cursor.execute(
            """
            INSERT INTO usuarios (
                PacCodigo,
                UsuNombre,
                UsuUsername,
                UsuCorreo,
                UsuPasswordHash,
                UsuRol,
                UsuActivo
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                codigo,
                f"{nombre} {apellido}",
                usuario,
                correo or None,
                generate_password_hash(password),
                "paciente",
                1,
            ),
        )

    conn.commit()
    cursor.close()
    conn.close()
    flash("Paciente actualizado.", "success")
    return redirect(url_for("pacientes_index"))


@app.route("/pacientes/eliminar/<string:codigo>", methods=["GET", "POST"])
@login_required
@admin_required
def pacientes_eliminar(codigo):
    if request.method == "GET":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pacientes WHERE PacCodigo = %s", (codigo,))
        paciente = cursor.fetchone()
        cursor.close()
        conn.close()
        return render_template("pacientes/eliminar.html", paciente=paciente)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM usuarios WHERE PacCodigo = %s", (codigo,))
    cursor.execute("DELETE FROM pacientes WHERE PacCodigo=%s", (codigo,))
    conn.commit()
    cursor.close()
    conn.close()
    flash("Paciente eliminado.", "info")
    return redirect(url_for("pacientes_index"))


# ==========================================
# CRUD 4: CITAS
# ==========================================
@app.route("/citas/")
@login_required
@admin_required
def citas_index():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT
            c.CitCodigo,
            c.CitFecha,
            c.CitHora,
            c.CitEstado,
            c.CitMotivo,
            c.CitObservaciones,
            p.PacCodigo,
            CONCAT(p.PacNombre, ' ', p.PacApellido) AS PacienteNombre,
            d.DocCodigo,
            CONCAT(d.DocNombre, ' ', d.DocApellido) AS DoctorNombre,
            d.DocEspecialidad,
            hc.HcCodigo
        FROM citas c
        INNER JOIN pacientes p ON c.PacCodigo = p.PacCodigo
        INNER JOIN doctores d ON c.DocCodigo = d.DocCodigo
        LEFT JOIN historial_clinico hc ON c.CitCodigo = hc.CitCodigo
        ORDER BY c.CitFecha ASC, c.CitHora ASC
    """
    cursor.execute(query)
    datos = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template(
        "citas/index.html",
        lista_citas=datos,
        resumen=get_citas_resumen(datos),
    )


@app.route("/citas/agregar", methods=["GET", "POST"])
@login_required
@admin_required
def citas_agregar():
    conn = get_db_connection()

    if request.method == "POST":
        paciente = request.form["PacCodigo"]
        doctor = request.form["DocCodigo"]
        fecha = request.form["CitFecha"]
        hora = request.form["CitHora"]
        estado = request.form["CitEstado"]
        motivo = request.form["CitMotivo"]
        observaciones = request.form["CitObservaciones"]

        if estado != "Cancelada":
            disponible, mensaje = doctor_schedule_message(conn, doctor, fecha, hora)
            if not disponible:
                pacientes, doctores = get_pacientes_doctores(conn)
                conn.close()
                flash(mensaje, "danger")
                return render_template(
                    "citas/agregar.html",
                    pacientes=pacientes,
                    doctores=doctores,
                    estados_cita=["Programada", "Confirmada", "Completada", "Cancelada"],
                )

        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO citas (
                PacCodigo,
                DocCodigo,
                CitFecha,
                CitHora,
                CitEstado,
                CitMotivo,
                CitObservaciones
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (paciente, doctor, fecha, hora, estado, motivo, observaciones),
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash("Cita registrada correctamente.", "success")
        return redirect(url_for("citas_index"))

    pacientes, doctores = get_pacientes_doctores(conn)
    conn.close()
    return render_template(
        "citas/agregar.html",
        pacientes=pacientes,
        doctores=doctores,
        estados_cita=["Programada", "Confirmada", "Completada", "Cancelada"],
    )


@app.route("/citas/editar/<string:codigo>", methods=["GET", "POST"])
@login_required
@admin_required
def citas_editar(codigo):
    conn = get_db_connection()

    if request.method == "GET":
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                CitCodigo,
                PacCodigo,
                DocCodigo,
                DATE_FORMAT(CitFecha, '%%Y-%%m-%%d'),
                TIME_FORMAT(CitHora, '%%H:%%i'),
                CitEstado,
                CitMotivo,
                IFNULL(CitObservaciones, '')
            FROM citas
            WHERE CitCodigo = %s
            """,
            (codigo,),
        )
        cita = cursor.fetchone()
        cursor.close()
        pacientes, doctores = get_pacientes_doctores(conn)
        conn.close()
        return render_template(
            "citas/editar.html",
            cita=cita,
            pacientes=pacientes,
            doctores=doctores,
            estados_cita=["Programada", "Confirmada", "Completada", "Cancelada"],
        )

    paciente = request.form["PacCodigo"]
    doctor = request.form["DocCodigo"]
    fecha = request.form["CitFecha"]
    hora = request.form["CitHora"]
    estado = request.form["CitEstado"]
    motivo = request.form["CitMotivo"]
    observaciones = request.form["CitObservaciones"]

    if estado != "Cancelada":
        disponible, mensaje = doctor_schedule_message(conn, doctor, fecha, hora, codigo)
        if not disponible:
            pacientes, doctores = get_pacientes_doctores(conn)
            conn.close()
            flash(mensaje, "danger")
            cita = (codigo, paciente, doctor, fecha, hora, estado, motivo, observaciones)
            return render_template(
                "citas/editar.html",
                cita=cita,
                pacientes=pacientes,
                doctores=doctores,
                estados_cita=["Programada", "Confirmada", "Completada", "Cancelada"],
            )

    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE citas
        SET
            PacCodigo = %s,
            DocCodigo = %s,
            CitFecha = %s,
            CitHora = %s,
            CitEstado = %s,
            CitMotivo = %s,
            CitObservaciones = %s
        WHERE CitCodigo = %s
        """,
        (paciente, doctor, fecha, hora, estado, motivo, observaciones, codigo),
    )
    conn.commit()
    cursor.close()
    conn.close()
    flash("Cita actualizada.", "success")
    return redirect(url_for("citas_index"))


@app.route("/citas/eliminar/<string:codigo>", methods=["GET", "POST"])
@login_required
@admin_required
def citas_eliminar(codigo):
    if request.method == "GET":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                c.CitCodigo,
                c.CitFecha,
                c.CitHora,
                c.CitEstado,
                c.CitMotivo,
                CONCAT(p.PacNombre, ' ', p.PacApellido) AS PacienteNombre,
                CONCAT(d.DocNombre, ' ', d.DocApellido) AS DoctorNombre
            FROM citas c
            INNER JOIN pacientes p ON c.PacCodigo = p.PacCodigo
            INNER JOIN doctores d ON c.DocCodigo = d.DocCodigo
            WHERE c.CitCodigo = %s
            """,
            (codigo,),
        )
        cita = cursor.fetchone()
        cursor.close()
        conn.close()
        return render_template("citas/eliminar.html", cita=cita)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM citas WHERE CitCodigo = %s", (codigo,))
    conn.commit()
    cursor.close()
    conn.close()
    flash("Cita eliminada.", "info")
    return redirect(url_for("citas_index"))


# ==========================================
# MODULO: HORARIOS MEDICOS
# ==========================================
@app.route("/horarios/")
@login_required
@admin_required
def horarios_index():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
            h.HorCodigo,
            h.HorDiaSemana,
            h.HorHoraInicio,
            h.HorHoraFin,
            h.HorActivo,
            CONCAT(d.DocNombre, ' ', d.DocApellido) AS DoctorNombre,
            d.DocEspecialidad
        FROM horarios_medicos h
        INNER JOIN doctores d ON h.DocCodigo = d.DocCodigo
        ORDER BY d.DocNombre, h.HorDiaSemana, h.HorHoraInicio
        """
    )
    horarios = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("horarios/index.html", horarios=horarios)


@app.route("/horarios/agregar", methods=["GET", "POST"])
@login_required
@admin_required
def horarios_agregar():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT DocCodigo, DocNombre, DocApellido, DocEspecialidad
        FROM doctores
        ORDER BY DocNombre, DocApellido
        """
    )
    doctores = cursor.fetchall()
    cursor.close()

    if request.method == "POST":
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO horarios_medicos (
                DocCodigo,
                HorDiaSemana,
                HorHoraInicio,
                HorHoraFin,
                HorActivo
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                request.form["DocCodigo"],
                request.form["HorDiaSemana"].lower(),
                request.form["HorHoraInicio"],
                request.form["HorHoraFin"],
                1,
            ),
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash("Horario medico registrado.", "success")
        return redirect(url_for("horarios_index"))

    conn.close()
    return render_template("horarios/agregar.html", doctores=doctores, dias=DIAS_SEMANA)


@app.route("/horarios/eliminar/<string:codigo>", methods=["GET", "POST"])
@login_required
@admin_required
def horarios_eliminar(codigo):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
            h.HorCodigo,
            h.HorDiaSemana,
            h.HorHoraInicio,
            h.HorHoraFin,
            CONCAT(d.DocNombre, ' ', d.DocApellido) AS DoctorNombre
        FROM horarios_medicos h
        INNER JOIN doctores d ON h.DocCodigo = d.DocCodigo
        WHERE h.HorCodigo = %s
        """,
        (codigo,),
    )
    horario = cursor.fetchone()

    if request.method == "POST":
        cursor.execute("DELETE FROM horarios_medicos WHERE HorCodigo = %s", (codigo,))
        conn.commit()
        cursor.close()
        conn.close()
        flash("Horario eliminado.", "info")
        return redirect(url_for("horarios_index"))

    cursor.close()
    conn.close()
    return render_template("horarios/eliminar.html", horario=horario)


# ==========================================
# MODULO: HISTORIAL CLINICO
# ==========================================
@app.route("/historial/<string:codigo>", methods=["GET", "POST"])
@login_required
def historial_editar(codigo):
    if current_user.rol not in ("admin", "doctor"):
        flash("No tienes permiso para gestionar historiales clinicos.", "danger")
        return redirect(url_for(dashboard_endpoint_for_role(current_user.rol)))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT
            c.CitCodigo,
            c.DocCodigo,
            c.CitFecha,
            c.CitHora,
            c.CitMotivo,
            CONCAT(p.PacNombre, ' ', p.PacApellido) AS PacienteNombre,
            CONCAT(d.DocNombre, ' ', d.DocApellido) AS DoctorNombre,
            d.DocEspecialidad
        FROM citas c
        INNER JOIN pacientes p ON c.PacCodigo = p.PacCodigo
        INNER JOIN doctores d ON c.DocCodigo = d.DocCodigo
        WHERE c.CitCodigo = %s
    """
    params = [codigo]
    if current_user.rol == "doctor":
        query += " AND c.DocCodigo = %s"
        params.append(current_user.doc_codigo)

    cursor.execute(query, tuple(params))
    cita = cursor.fetchone()

    if not cita:
        cursor.close()
        conn.close()
        flash("La cita no existe o no tienes acceso para editar su historial.", "danger")
        return redirect(url_for("doctor_agenda" if current_user.rol == "doctor" else "citas_index"))

    cursor.execute(
        """
        SELECT
            HcCodigo,
            HcDiagnostico,
            HcTratamiento,
            HcObservaciones
        FROM historial_clinico
        WHERE CitCodigo = %s
        """,
        (codigo,),
    )
    historial = cursor.fetchone()

    if request.method == "POST":
        diagnostico = request.form["HcDiagnostico"]
        tratamiento = request.form["HcTratamiento"]
        observaciones = request.form["HcObservaciones"]

        if historial:
            cursor.execute(
                """
                UPDATE historial_clinico
                SET
                    HcDiagnostico = %s,
                    HcTratamiento = %s,
                    HcObservaciones = %s
                WHERE CitCodigo = %s
                """,
                (diagnostico, tratamiento, observaciones, codigo),
            )
        else:
            cursor.execute(
                """
                INSERT INTO historial_clinico (
                    CitCodigo,
                    HcDiagnostico,
                    HcTratamiento,
                    HcObservaciones
                ) VALUES (%s, %s, %s, %s)
                """,
                (codigo, diagnostico, tratamiento, observaciones),
            )
        conn.commit()
        cursor.close()
        conn.close()
        flash("Historial clinico guardado.", "success")
        return redirect(url_for("doctor_agenda" if current_user.rol == "doctor" else "citas_index"))

    cursor.close()
    conn.close()
    return render_template("historial/editar.html", cita=cita, historial=historial)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
