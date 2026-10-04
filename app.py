from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
from functools import wraps
from datetime import datetime

app = Flask(__name__)

app.secret_key = "smart_patient_secret_key"

DATABASE = "database.db"


# =========================================================
# SENSOR DATA
# =========================================================

latest_temperature = 0
latest_fsr = 0


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# =========================================================
# INITIALIZE DATABASE
# =========================================================

def init_db():

    conn = get_db()
    cursor = conn.cursor()

    # ---------------- USERS ----------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)

    # ---------------- PATIENTS ----------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            age INTEGER,
            gender TEXT,
            department TEXT,
            created_at TEXT
        )
    """)

    # ---------------- VISITS ----------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER,
            visit_number INTEGER,
            temperature REAL,
            pressure REAL,
            complaint TEXT,
            history TEXT,
            diagnosis TEXT,
            weight REAL,
            height REAL,
            vaccination TEXT,
            date TEXT,
            FOREIGN KEY(patient_id) REFERENCES patients(id)
        )
    """)

    # ---------------- DEFAULT USERS ----------------

    cursor.execute("""
        SELECT * FROM users WHERE username = ?
    """, ("admin",))

    if cursor.fetchone() is None:

        cursor.execute("""
            INSERT INTO users
            (username, password, role)
            VALUES (?, ?, ?)
        """, (
            "admin",
            "admin123",
            "Admin"
        ))

    cursor.execute("""
        SELECT * FROM users WHERE username = ?
    """, ("doctor",))

    if cursor.fetchone() is None:

        cursor.execute("""
            INSERT INTO users
            (username, password, role)
            VALUES (?, ?, ?)
        """, (
            "doctor",
            "doctor123",
            "Doctor"
        ))

    conn.commit()
    conn.close()


# =========================================================
# LOGIN REQUIRED
# =========================================================

def login_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):

        if "username" not in session:
            return redirect(url_for("login"))

        return f(*args, **kwargs)

    return decorated_function


# =========================================================
# HOME
# =========================================================

@app.route("/")
def index():

    if "username" in session:
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        conn = get_db()

        user = conn.execute("""
            SELECT * FROM users
            WHERE username = ?
            AND password = ?
        """, (
            username,
            password
        )).fetchone()

        conn.close()

        if user:

            session["username"] = user["username"]
            session["role"] = user["role"]

            return redirect(url_for("dashboard"))

        return render_template(
            "login.html",
            error="Invalid username or password"
        )

    return render_template("login.html")


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
@login_required
def dashboard():

    conn = get_db()

    patient_count = conn.execute("""
        SELECT COUNT(*) AS count
        FROM patients
    """).fetchone()["count"]

    visit_count = conn.execute("""
        SELECT COUNT(*) AS count
        FROM visits
    """).fetchone()["count"]

    conn.close()

    return render_template(
        "index.html",
        username=session.get("username"),
        role=session.get("role"),
        patient_count=patient_count,
        visit_count=visit_count
    )


# =========================================================
# REGISTER PATIENT
# =========================================================

@app.route("/register", methods=["GET", "POST"])
@login_required
def register():

    if request.method == "POST":

        name = request.form.get("name")
        age = request.form.get("age")
        gender = request.form.get("gender")
        department = request.form.get("department")

        conn = get_db()

        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO patients
            (name, age, gender, department, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            name,
            age,
            gender,
            department,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        patient_id = cursor.lastrowid

        conn.commit()
        conn.close()

        return redirect(
            url_for(
                "patient",
                patient_id=patient_id
            )
        )

    return render_template("register.html")


# =========================================================
# PATIENT PROFILE
# =========================================================

@app.route("/patient/<int:patient_id>")
@login_required
def patient(patient_id):

    conn = get_db()

    patient_data = conn.execute("""
        SELECT *
        FROM patients
        WHERE id = ?
    """, (
        patient_id,
    )).fetchone()

    visits = conn.execute("""
        SELECT *
        FROM visits
        WHERE patient_id = ?
        ORDER BY visit_number ASC
    """, (
        patient_id,
    )).fetchall()

    conn.close()

    if patient_data is None:
        return "Patient not found", 404

    return render_template(
        "patient.html",
        patient=patient_data,
        visits=visits,
        role=session.get("role")
    )


# =========================================================
# NEW VISIT
# =========================================================

@app.route("/visit/<int:patient_id>")
@login_required
def visit(patient_id):

    conn = get_db()

    patient_data = conn.execute("""
        SELECT *
        FROM patients
        WHERE id = ?
    """, (
        patient_id,
    )).fetchone()

    conn.close()

    if patient_data is None:
        return "Patient not found", 404

    department = patient_data["department"]

    if department == "General Medicine":

        return render_template(
            "general_form.html",
            patient=patient_data
        )

    elif department == "Pediatrics":

        return render_template(
            "pediatric_form.html",
            patient=patient_data
        )

    return "Invalid department", 400


# =========================================================
# SAVE GENERAL MEDICINE VISIT
# =========================================================

@app.route("/save_general", methods=["POST"])
@login_required
def save_general():

    patient_id = request.form.get("patient_id")

    temperature = request.form.get("temperature")
    pressure = request.form.get("pressure")

    complaint = request.form.get("complaint")
    history = request.form.get("history")
    diagnosis = request.form.get("diagnosis")

    conn = get_db()

    # Find next visit number

    result = conn.execute("""
        SELECT MAX(visit_number) AS max_visit
        FROM visits
        WHERE patient_id = ?
    """, (
        patient_id,
    )).fetchone()

    if result["max_visit"] is None:
        visit_number = 1
    else:
        visit_number = result["max_visit"] + 1

    conn.execute("""
        INSERT INTO visits
        (
            patient_id,
            visit_number,
            temperature,
            pressure,
            complaint,
            history,
            diagnosis,
            weight,
            height,
            vaccination,
            date
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        patient_id,
        visit_number,
        temperature if temperature else None,
        pressure if pressure else None,
        complaint,
        history,
        diagnosis,
        None,
        None,
        None,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

    return redirect(
        url_for(
            "patient",
            patient_id=patient_id
        )
    )


# =========================================================
# SAVE PEDIATRIC VISIT
# =========================================================

@app.route("/save_pediatric", methods=["POST"])
@login_required
def save_pediatric():

    patient_id = request.form.get("patient_id")

    temperature = request.form.get("temperature")
    pressure = request.form.get("pressure")

    complaint = request.form.get("complaint")
    history = request.form.get("history")
    diagnosis = request.form.get("diagnosis")

    weight = request.form.get("weight")
    height = request.form.get("height")
    vaccination = request.form.get("vaccination")

    conn = get_db()

    # Find next visit number

    result = conn.execute("""
        SELECT MAX(visit_number) AS max_visit
        FROM visits
        WHERE patient_id = ?
    """, (
        patient_id,
    )).fetchone()

    if result["max_visit"] is None:
        visit_number = 1
    else:
        visit_number = result["max_visit"] + 1

    conn.execute("""
        INSERT INTO visits
        (
            patient_id,
            visit_number,
            temperature,
            pressure,
            complaint,
            history,
            diagnosis,
            weight,
            height,
            vaccination,
            date
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        patient_id,
        visit_number,
        temperature if temperature else None,
        pressure if pressure else None,
        complaint,
        history,
        diagnosis,
        weight if weight else None,
        height if height else None,
        vaccination,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

    return redirect(
        url_for(
            "patient",
            patient_id=patient_id
        )
    )


# =========================================================
# PATIENT LIST
# =========================================================

@app.route("/patients")
@login_required
def patients():

    conn = get_db()

    patients_data = conn.execute("""
        SELECT
            p.*,

            (
                SELECT temperature
                FROM visits v
                WHERE v.patient_id = p.id
                ORDER BY v.id DESC
                LIMIT 1
            ) AS temperature,

            (
                SELECT pressure
                FROM visits v
                WHERE v.patient_id = p.id
                ORDER BY v.id DESC
                LIMIT 1
            ) AS pressure,

            (
                SELECT complaint
                FROM visits v
                WHERE v.patient_id = p.id
                ORDER BY v.id DESC
                LIMIT 1
            ) AS complaint,

            (
                SELECT diagnosis
                FROM visits v
                WHERE v.patient_id = p.id
                ORDER BY v.id DESC
                LIMIT 1
            ) AS diagnosis,

            (
                SELECT date
                FROM visits v
                WHERE v.patient_id = p.id
                ORDER BY v.id DESC
                LIMIT 1
            ) AS visit_date

        FROM patients p

        ORDER BY p.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "patients.html",
        patients=patients_data,
        role=session.get("role")
    )


# =========================================================
# DELETE PATIENT
# ADMIN ONLY
# =========================================================

@app.route("/delete_patient/<int:patient_id>", methods=["POST", "GET"])
@login_required
def delete_patient(patient_id):

    if session.get("role") != "Admin":
        return "Access Denied: Admin only", 403

    conn = get_db()

    # Delete visits first

    conn.execute("""
        DELETE FROM visits
        WHERE patient_id = ?
    """, (
        patient_id,
    ))

    # Delete patient

    conn.execute("""
        DELETE FROM patients
        WHERE id = ?
    """, (
        patient_id,
    ))

    conn.commit()
    conn.close()

    return redirect(
        url_for("patients")
    )


# =========================================================
# ESP32 SENSOR API
# =========================================================

@app.route("/api/sensor", methods=["POST"])
def receive_sensor():

    global latest_temperature
    global latest_fsr

    data = request.get_json(silent=True)

    if not data:

        return {
            "status": "error",
            "message": "No JSON data received"
        }, 400

    # Temperature

    if "temperature" in data:

        latest_temperature = data["temperature"]

    # FSR

    if "fsr" in data:

        latest_fsr = data["fsr"]

    print("======================================")
    print("ESP32 SENSOR DATA RECEIVED")
    print("Temperature:", latest_temperature, "°C")
    print("FSR Value:", latest_fsr)
    print("======================================")

    return {
        "status": "success",
        "temperature": latest_temperature,
        "fsr": latest_fsr
    }, 200


# =========================================================
# FSR API
# =========================================================

@app.route("/api/fsr", methods=["GET"])
def get_fsr():

    return {
        "fsr": latest_fsr
    }, 200


# =========================================================
# ALL SENSOR DATA API
# =========================================================

@app.route("/api/sensors", methods=["GET"])
def get_sensors():

    return {
        "temperature": latest_temperature,
        "fsr": latest_fsr
    }, 200


# =========================================================
# START APPLICATION
# =========================================================

if __name__ == "__main__":

    init_db()

    print()
    print("======================================")
    print(" SMART PATIENT CASE-TAKING SYSTEM")
    print("======================================")
    print("Server starting...")
    print("Laptop IP: http://10.208.171.46:8000")
    print("Sensor API:")
    print("POST /api/sensor")
    print("GET  /api/fsr")
    print("GET  /api/sensors")
    print("======================================")
    print()

    app.run(
        host="0.0.0.0",
        port=8000,
        debug=False
    )