import os
from flask import Flask, jsonify, render_template, request, redirect, url_for
import mysql.connector

app = Flask(__name__)

DB_HOST = os.environ.get('MYSQLHOST', 'localhost')
DB_USER = os.environ.get('MYSQLUSER', 'root')
DB_PASSWORD = os.environ.get('MYSQLPASSWORD', '')
DB_NAME = os.environ.get('MYSQLDATABASE', 'railway') 
DB_PORT = os.environ.get('MYSQLPORT', 3306)

def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        port=DB_PORT,
        auth_plugin='GhHcNmQnHwjzetZmqNCjJPHTBjjnJdIt'
    )

@app.route("/")
def index():
    return render_template('index.html')

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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False) 