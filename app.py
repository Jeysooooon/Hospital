import os
from flask import Flask, render_template, request, redirect, url_for
import mysql.connector
from mysql.connector import Error


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

DB_HOST = os.environ.get('MYSQLHOST', 'localhost')
DB_USER = os.environ.get('MYSQLUSER', 'root')
DB_PASSWORD = os.environ.get('MYSQLPASSWORD', '')
DB_NAME = os.environ.get('MYSQLDATABASE') or os.environ.get('MYSQL_DATABASE') or os.environ.get('DB_NAME')
DB_PORT = os.environ.get('MYSQLPORT', 3306)

SYSTEM_DATABASES = {"information_schema", "mysql", "performance_schema", "sys"}
DATABASE_CANDIDATES = ["hospital", "railway"]


class DatabaseConfigError(RuntimeError):
    pass


def discover_database_name():
    try:
        temp_conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT,
            auth_plugin='mysql_native_password'
        )
        cursor = temp_conn.cursor()
        cursor.execute("SHOW DATABASES")
        databases = [row[0] for row in cursor.fetchall() if row[0] not in SYSTEM_DATABASES]
        cursor.close()
        temp_conn.close()

        for candidate in DATABASE_CANDIDATES:
            if candidate in databases:
                return candidate

        if len(databases) == 1:
            return databases[0]
    except Error:
        return None

    return None

def get_db_connection():
    database_name = DB_NAME or discover_database_name()

    if not database_name:
        raise DatabaseConfigError(
            "No se pudo determinar la base de datos. "
            "Configura MYSQLDATABASE en tu entorno o en tu archivo .env."
        )

    try:
        return mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=database_name,
            port=DB_PORT,
            auth_plugin='mysql_native_password'
        )
    except Error as exc:
        raise DatabaseConfigError(
            f"No se pudo conectar a la base de datos '{database_name}'. "
            f"Detalle: {exc}"
        ) from exc


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
    programadas = sum(1 for cita in lista_citas if cita[3] == "Programada")
    confirmadas = sum(1 for cita in lista_citas if cita[3] == "Confirmada")
    return {
        "total": total,
        "programadas": programadas,
        "confirmadas": confirmadas,
    }

@app.route("/")
def index():
    return render_template('index.html')


@app.errorhandler(DatabaseConfigError)
def handle_database_config_error(error):
    return render_template("error_db.html", error_message=str(error)), 500

# ==========================================
# CRUD 1: ESPECIALIDAD
# ==========================================
@app.route("/especialidad/")
def especialidad_index():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM especialidad")
    datos = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('especialidad/index.html', lista_especialidades=datos)

@app.route("/especialidad/agregar", methods=["GET", "POST"])
def especialidad_agregar():
    if request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        nombre = request.form['EspNombre']
        descripcion = request.form['EspDescripcion']
        cursor.execute("INSERT INTO especialidad (EspNombre, EspDescripcion) VALUES (%s, %s)", (nombre, descripcion))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('especialidad_index'))
    return render_template('especialidad/agregar.html')

@app.route("/especialidad/editar/<string:codigo>", methods=["GET", "POST"])
def especialidad_editar(codigo):
    if request.method == 'GET':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM especialidad WHERE EspCodigo = %s", (codigo,))
        especialidad = cursor.fetchone()
        cursor.close()
        conn.close()
        return render_template('especialidad/editar.html', especialidad=especialidad)
    elif request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        nombre = request.form['EspNombre']
        descripcion = request.form['EspDescripcion']
        cursor.execute("UPDATE especialidad SET EspNombre=%s, EspDescripcion=%s WHERE EspCodigo=%s", (nombre, descripcion, codigo))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('especialidad_index'))

@app.route("/especialidad/eliminar/<string:codigo>", methods=["GET", "POST"])
def especialidad_eliminar(codigo):
    if request.method == 'GET':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM especialidad WHERE EspCodigo = %s", (codigo,))
        especialidad = cursor.fetchone()
        cursor.close()
        conn.close()
        return render_template('especialidad/eliminar.html', especialidad=especialidad)
    elif request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM especialidad WHERE EspCodigo=%s", (codigo,))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('especialidad_index'))

# ==========================================
# CRUD 2: DOCTORES
# ==========================================
@app.route("/doctores/")
def doctores_index():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM doctores")
    datos = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('doctores/index.html', lista_doctores=datos)

@app.route("/doctores/agregar", methods=["GET", "POST"])
def doctores_agregar():
    if request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        nombre = request.form['DocNombre']
        apellido = request.form['DocApellido']
        especialidad = request.form['DocEspecialidad']
        telefono = request.form['DocTelefono']
        correo = request.form['DocCorreo']
        cursor.execute("INSERT INTO doctores (DocNombre, DocApellido, DocEspecialidad, DocTelefono, DocCorreo) VALUES (%s, %s, %s, %s, %s)", 
                       (nombre, apellido, especialidad, telefono, correo))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('doctores_index'))
    return render_template('doctores/agregar.html')

@app.route("/doctores/editar/<string:codigo>", methods=["GET", "POST"])
def doctores_editar(codigo):
    if request.method == 'GET':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM doctores WHERE DocCodigo = %s", (codigo,))
        doctor = cursor.fetchone()
        cursor.close()
        conn.close()
        return render_template('doctores/editar.html', doctor=doctor)
    elif request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        nombre = request.form['DocNombre']
        apellido = request.form['DocApellido']
        especialidad = request.form['DocEspecialidad']
        telefono = request.form['DocTelefono']
        correo = request.form['DocCorreo']
        cursor.execute("UPDATE doctores SET DocNombre=%s, DocApellido=%s, DocEspecialidad=%s, DocTelefono=%s, DocCorreo=%s WHERE DocCodigo=%s", 
                       (nombre, apellido, especialidad, telefono, correo, codigo))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('doctores_index'))

@app.route("/doctores/eliminar/<string:codigo>", methods=["GET", "POST"])
def doctores_eliminar(codigo):
    if request.method == 'GET':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM doctores WHERE DocCodigo = %s", (codigo,))
        doctor = cursor.fetchone()
        cursor.close()
        conn.close()
        return render_template('doctores/eliminar.html', doctor=doctor)
    elif request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM doctores WHERE DocCodigo=%s", (codigo,))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('doctores_index'))

# ==========================================
# CRUD 3: PACIENTES
# ==========================================
@app.route("/pacientes/")
def pacientes_index():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pacientes")
    datos = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('pacientes/index.html', lista_pacientes=datos)

@app.route("/pacientes/agregar", methods=["GET", "POST"])
def pacientes_agregar():
    if request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        nombre = request.form['PacNombre']
        apellido = request.form['PacApellido']
        dni = request.form['PacDNI']
        telefono = request.form['PacTelefono']
        direccion = request.form['PacDireccion']
        cursor.execute("INSERT INTO pacientes (PacNombre, PacApellido, PacDNI, PacTelefono, PacDireccion) VALUES (%s, %s, %s, %s, %s)", 
                       (nombre, apellido, dni, telefono, direccion))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('pacientes_index'))
    return render_template('pacientes/agregar.html')

@app.route("/pacientes/editar/<string:codigo>", methods=["GET", "POST"])
def pacientes_editar(codigo):
    if request.method == 'GET':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pacientes WHERE PacCodigo = %s", (codigo,))
        paciente = cursor.fetchone()
        cursor.close()
        conn.close()
        return render_template('pacientes/editar.html', paciente=paciente)
    elif request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        nombre = request.form['PacNombre']
        apellido = request.form['PacApellido']
        dni = request.form['PacDNI']
        telefono = request.form['PacTelefono']
        direccion = request.form['PacDireccion']
        cursor.execute("UPDATE pacientes SET PacNombre=%s, PacApellido=%s, PacDNI=%s, PacTelefono=%s, PacDireccion=%s WHERE PacCodigo=%s", 
                       (nombre, apellido, dni, telefono, direccion, codigo))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('pacientes_index'))

@app.route("/pacientes/eliminar/<string:codigo>", methods=["GET", "POST"])
def pacientes_eliminar(codigo):
    if request.method == 'GET':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pacientes WHERE PacCodigo = %s", (codigo,))
        paciente = cursor.fetchone()
        cursor.close()
        conn.close()
        return render_template('pacientes/eliminar.html', paciente=paciente)
    elif request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pacientes WHERE PacCodigo=%s", (codigo,))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('pacientes_index'))


# ==========================================
# CRUD 4: CITAS
# ==========================================
@app.route("/citas/")
def citas_index():
    conn = get_db_connection()
    ensure_citas_table(conn)
    cursor = conn.cursor()
    cursor.execute(
        """
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
            d.DocEspecialidad
        FROM citas c
        INNER JOIN pacientes p ON c.PacCodigo = p.PacCodigo
        INNER JOIN doctores d ON c.DocCodigo = d.DocCodigo
        ORDER BY c.CitFecha ASC, c.CitHora ASC
        """
    )
    datos = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template(
        'citas/index.html',
        lista_citas=datos,
        resumen=get_citas_resumen(datos),
    )


@app.route("/citas/agregar", methods=["GET", "POST"])
def citas_agregar():
    conn = get_db_connection()
    ensure_citas_table(conn)

    if request.method == 'POST':
        cursor = conn.cursor()
        paciente = request.form['PacCodigo']
        doctor = request.form['DocCodigo']
        fecha = request.form['CitFecha']
        hora = request.form['CitHora']
        estado = request.form['CitEstado']
        motivo = request.form['CitMotivo']
        observaciones = request.form['CitObservaciones']
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
        return redirect(url_for('citas_index'))

    pacientes, doctores = get_pacientes_doctores(conn)
    conn.close()
    return render_template(
        'citas/agregar.html',
        pacientes=pacientes,
        doctores=doctores,
        estados_cita=["Programada", "Confirmada", "Completada", "Cancelada"],
    )


@app.route("/citas/editar/<string:codigo>", methods=["GET", "POST"])
def citas_editar(codigo):
    conn = get_db_connection()
    ensure_citas_table(conn)

    if request.method == 'GET':
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
            'citas/editar.html',
            cita=cita,
            pacientes=pacientes,
            doctores=doctores,
            estados_cita=["Programada", "Confirmada", "Completada", "Cancelada"],
        )

    cursor = conn.cursor()
    paciente = request.form['PacCodigo']
    doctor = request.form['DocCodigo']
    fecha = request.form['CitFecha']
    hora = request.form['CitHora']
    estado = request.form['CitEstado']
    motivo = request.form['CitMotivo']
    observaciones = request.form['CitObservaciones']
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
    return redirect(url_for('citas_index'))


@app.route("/citas/eliminar/<string:codigo>", methods=["GET", "POST"])
def citas_eliminar(codigo):
    conn = get_db_connection()
    ensure_citas_table(conn)

    if request.method == 'GET':
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
        return render_template('citas/eliminar.html', cita=cita)

    cursor = conn.cursor()
    cursor.execute("DELETE FROM citas WHERE CitCodigo = %s", (codigo,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('citas_index'))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False) 
