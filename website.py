from flask import Flask, render_template, request, redirect, session
import psycopg2
import os
from datetime import datetime, timedelta

app = Flask(__name__)

# =========================================================
# FLASK SECRET KEY
# =========================================================

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "employee_management_secret_key"
)

# =========================================================
# POSTGRESQL DATABASE
# =========================================================

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is not set.")
    return psycopg2.connect(DATABASE_URL)


# =========================================================
# DATABASE SETUP
# =========================================================

def create_tables():

    conn = get_db_connection()
    cur = conn.cursor()

    # -----------------------------------------------------
    # EMPLOYEE TABLE
    # -----------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS employee (
            id SERIAL PRIMARY KEY,
            employee_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            email TEXT,
            department TEXT,
            mobile TEXT
        )
    """)

    # -----------------------------------------------------
    # ATTENDANCE TABLE
    # -----------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id SERIAL PRIMARY KEY,
            employee_id TEXT NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL,
            check_in TEXT,
            check_out TEXT,
            attendance_type TEXT
        )
    """)

    # -----------------------------------------------------
    # LEAVE REQUEST TABLE
    # -----------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS leave_request (
            id SERIAL PRIMARY KEY,
            employee_id TEXT NOT NULL,
            leave_date TEXT NOT NULL,
            reason TEXT,
            status TEXT DEFAULT 'Pending'
        )
    """)

    # -----------------------------------------------------
    # ADD MISSING ATTENDANCE COLUMNS
    # -----------------------------------------------------

    cur.execute("""
        ALTER TABLE attendance
        ADD COLUMN IF NOT EXISTS check_in TEXT
    """)

    cur.execute("""
        ALTER TABLE attendance
        ADD COLUMN IF NOT EXISTS check_out TEXT
    """)

    cur.execute("""
        ALTER TABLE attendance
        ADD COLUMN IF NOT EXISTS attendance_type TEXT
    """)

    conn.commit()

    cur.close()
    conn.close()


# Create database tables
create_tables()


# =========================================================
# HELPER FUNCTION
# CALCULATE WORKING HOURS
# =========================================================

def calculate_working_hours(check_in, check_out):

    if not check_in or not check_out:
        return "-"

    try:

        in_time = datetime.strptime(
            check_in,
            "%I:%M %p"
        )

        out_time = datetime.strptime(
            check_out,
            "%I:%M %p"
        )

        if out_time < in_time:
            out_time += timedelta(days=1)

        difference = out_time - in_time

        total_seconds = int(
            difference.total_seconds()
        )

        hours = total_seconds // 3600

        minutes = (
            total_seconds % 3600
        ) // 60

        return f"{hours:02d}:{minutes:02d}"

    except (ValueError, TypeError):

        return "-"


# =========================================================
# HOME PAGE
# =========================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# =========================================================
# SITEMAP
# =========================================================

@app.route("/sitemap.xml")
def sitemap():

    xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">

    <url>
        <loc>https://employee-attendance-management-system-1-temn.onrender.com/</loc>
    </url>

    <url>
        <loc>https://employee-attendance-management-system-1-temn.onrender.com/login</loc>
    </url>

    <url>
        <loc>https://employee-attendance-management-system-1-temn.onrender.com/employee_login</loc>
    </url>

</urlset>
"""

    return xml, 200, {
        "Content-Type": "application/xml"
    }


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"].strip()
        password = request.form["password"].strip()

        if username == "admin" and password == "1234":

            session["admin"] = True

            return redirect("/dashboard")

        return """
        <h2 style='color:red;text-align:center;'>
            Invalid Username or Password
        </h2>

        <center>
            <a href='/login'>Try Again</a>
        </center>
        """

    return render_template(
        "login.html"
    )


# =========================================================
# EMPLOYEE LOGIN
# =========================================================

@app.route(
    "/employee_login",
    methods=["GET", "POST"]
)
def employee_login():

    if request.method == "POST":

        employee_id = request.form[
            "username"
        ].strip()

        password = request.form[
            "password"
        ].strip()

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                employee_id,
                name
            FROM employee
            WHERE employee_id=%s
        """, (
            employee_id,
        ))

        employee = cur.fetchone()

        cur.close()
        conn.close()

        # Employee password = 1234

        if employee and password == "1234":

            session["employee"] = employee[0]

            return redirect(
                "/employee_dashboard"
            )

        return """
        <h2 style='color:red;text-align:center;'>
            Invalid Employee ID or Password
        </h2>

        <center>
            <a href='/employee_login'>Try Again</a>
        </center>
        """

    return render_template(
        "employee_login.html"
    )


# =========================================================
# EMPLOYEE DASHBOARD
# =========================================================

@app.route("/employee_dashboard")
def employee_dashboard():

    employee_id = session.get("employee")

    if not employee_id:

        return redirect(
            "/employee_login"
        )

    total_days = 0
    present = 0
    absent = 0

    pending_leave = 0
    approved_leave = 0
    rejected_leave = 0

    percentage = 0

    attendance = []
    leave_history = []

    employee_name = "Employee"
    employee_department = ""
    employee_email = ""
    employee_mobile = ""

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    today_attendance = None
    today_working_hours = "-"

    message = request.args.get(
        "message",
        ""
    )

    conn = get_db_connection()
    cur = conn.cursor()

    # -----------------------------------------------------
    # EMPLOYEE DETAILS
    # -----------------------------------------------------

    cur.execute("""
        SELECT
            employee_id,
            name,
            email,
            department,
            mobile
        FROM employee
        WHERE employee_id=%s
    """, (
        employee_id,
    ))

    employee = cur.fetchone()

    if employee:

        employee_id = employee[0]
        employee_name = employee[1]
        employee_email = employee[2]
        employee_department = employee[3]
        employee_mobile = employee[4]

    # -----------------------------------------------------
    # TOTAL ATTENDANCE
    # -----------------------------------------------------

    cur.execute("""
        SELECT COUNT(*)
        FROM attendance
        WHERE employee_id=%s
    """, (
        employee_id,
    ))

    total_days = cur.fetchone()[0]

    # -----------------------------------------------------
    # PRESENT
    # -----------------------------------------------------

    cur.execute("""
        SELECT COUNT(*)
        FROM attendance
        WHERE employee_id=%s
        AND status='Present'
    """, (
        employee_id,
    ))

    present = cur.fetchone()[0]

    # -----------------------------------------------------
    # ABSENT
    # -----------------------------------------------------

    cur.execute("""
        SELECT COUNT(*)
        FROM attendance
        WHERE employee_id=%s
        AND status='Absent'
    """, (
        employee_id,
    ))

    absent = cur.fetchone()[0]

    # -----------------------------------------------------
    # PENDING LEAVE
    # -----------------------------------------------------

    cur.execute("""
        SELECT COUNT(*)
        FROM leave_request
        WHERE employee_id=%s
        AND status='Pending'
    """, (
        employee_id,
    ))

    pending_leave = cur.fetchone()[0]

    # -----------------------------------------------------
    # APPROVED LEAVE
    # -----------------------------------------------------

    cur.execute("""
        SELECT COUNT(*)
        FROM leave_request
        WHERE employee_id=%s
        AND status='Approved'
    """, (
        employee_id,
    ))

    approved_leave = cur.fetchone()[0]

    # -----------------------------------------------------
    # REJECTED LEAVE
    # -----------------------------------------------------

    cur.execute("""
        SELECT COUNT(*)
        FROM leave_request
        WHERE employee_id=%s
        AND status='Rejected'
    """, (
        employee_id,
    ))

    rejected_leave = cur.fetchone()[0]

    # -----------------------------------------------------
    # TODAY ATTENDANCE
    # -----------------------------------------------------

    cur.execute("""
        SELECT
            id,
            date,
            status,
            check_in,
            check_out,
            attendance_type
        FROM attendance
        WHERE employee_id=%s
        AND date=%s
        ORDER BY id DESC
        LIMIT 1
    """, (
        employee_id,
        today
    ))

    today_attendance = cur.fetchone()

    if today_attendance:

        today_working_hours = calculate_working_hours(
            today_attendance[3],
            today_attendance[4]
        )

    # -----------------------------------------------------
    # ATTENDANCE DETAILS
    # -----------------------------------------------------

    cur.execute("""
        SELECT
            date,
            status,
            check_in,
            check_out,
            attendance_type
        FROM attendance
        WHERE employee_id=%s
        ORDER BY date DESC, id DESC
    """, (
        employee_id,
    ))

    raw_attendance = cur.fetchall()

    for record in raw_attendance:

        record_date = record[0]
        status = record[1]
        check_in = record[2]
        check_out = record[3]
        attendance_type = record[4]

        working_hours = calculate_working_hours(
            check_in,
            check_out
        )

        attendance.append(
            (
                record_date,
                status,
                check_in,
                check_out,
                attendance_type,
                working_hours
            )
        )

    # -----------------------------------------------------
    # LEAVE HISTORY
    # -----------------------------------------------------

    cur.execute("""
        SELECT
            leave_date,
            reason,
            status
        FROM leave_request
        WHERE employee_id=%s
        ORDER BY leave_date DESC
    """, (
        employee_id,
    ))

    leave_history = cur.fetchall()

    # -----------------------------------------------------
    # ATTENDANCE PERCENTAGE
    # -----------------------------------------------------

    if total_days > 0:

        percentage = round(
            (present / total_days) * 100,
            2
        )

    cur.close()
    conn.close()

    return render_template(
        "employee_dashboard.html",

        employee_id=employee_id,
        employee_name=employee_name,
        employee_email=employee_email,
        employee_department=employee_department,
        employee_mobile=employee_mobile,

        total_days=total_days,
        present=present,
        absent=absent,

        pending_leave=pending_leave,
        approved_leave=approved_leave,
        rejected_leave=rejected_leave,

        percentage=percentage,

        attendance=attendance,
        leave_history=leave_history,

        today_attendance=today_attendance,
        today_working_hours=today_working_hours,

        today=today,
        message=message
    )


# =========================================================
# EMPLOYEE CHECK-IN
# =========================================================

@app.route(
    "/employee_check_in",
    methods=["POST"]
)
def employee_check_in():

    employee_id = session.get("employee")

    if not employee_id:

        return redirect(
            "/employee_login"
        )

    attendance_type = request.form.get(
        "attendance_type",
        ""
    ).strip()

    if attendance_type not in [
        "First Half",
        "Second Half"
    ]:

        return redirect(
            "/employee_dashboard"
            "?message=Please select First Half or Second Half."
        )

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    current_time = datetime.now().strftime(
        "%I:%M %p"
    )

    conn = get_db_connection()
    cur = conn.cursor()

    # -----------------------------------------------------
    # CHECK EXISTING ATTENDANCE
    # -----------------------------------------------------

    cur.execute("""
        SELECT
            id,
            check_in,
            check_out,
            attendance_type
        FROM attendance
        WHERE employee_id=%s
        AND date=%s
        ORDER BY id DESC
        LIMIT 1
    """, (
        employee_id,
        today
    ))

    existing = cur.fetchone()

    if existing:

        cur.close()
        conn.close()

        return redirect(
            "/employee_dashboard"
            "?message=You have already checked in today."
        )

    # -----------------------------------------------------
    # INSERT
    # -----------------------------------------------------

    cur.execute("""
        INSERT INTO attendance
        (
            employee_id,
            date,
            status,
            check_in,
            check_out,
            attendance_type
        )
        VALUES
        (
            %s,
            %s,
            'Present',
            %s,
            NULL,
            %s
        )
    """, (
        employee_id,
        today,
        current_time,
        attendance_type
    ))

    conn.commit()

    cur.close()
    conn.close()

    return redirect(
        "/employee_dashboard"
        "?message=Check-In successful."
    )


# =========================================================
# EMPLOYEE CHECK-OUT
# =========================================================

@app.route(
    "/employee_check_out",
    methods=["POST"]
)
def employee_check_out():

    employee_id = session.get("employee")

    if not employee_id:

        return redirect(
            "/employee_login"
        )

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    current_time = datetime.now().strftime(
        "%I:%M %p"
    )

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            check_in,
            check_out
        FROM attendance
        WHERE employee_id=%s
        AND date=%s
        ORDER BY id DESC
        LIMIT 1
    """, (
        employee_id,
        today
    ))

    record = cur.fetchone()

    if not record:

        cur.close()
        conn.close()

        return redirect(
            "/employee_dashboard"
            "?message=Please Check-In first."
        )

    attendance_id = record[0]
    check_out = record[2]

    if check_out:

        cur.close()
        conn.close()

        return redirect(
            "/employee_dashboard"
            "?message=You have already checked out today."
        )

    cur.execute("""
        UPDATE attendance
        SET check_out=%s
        WHERE id=%s
    """, (
        current_time,
        attendance_id
    ))

    conn.commit()

    cur.close()
    conn.close()

    return redirect(
        "/employee_dashboard"
        "?message=Check-Out successful."
    )


# =========================================================
# APPLY LEAVE
# =========================================================

@app.route(
    "/apply_leave",
    methods=["GET", "POST"]
)
def apply_leave():

    employee_id = session.get("employee")

    if not employee_id:

        return redirect(
            "/employee_login"
        )

    if request.method == "POST":

        leave_date = request.form[
            "leave_date"
        ].strip()

        reason = request.form[
            "reason"
        ].strip()

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO leave_request
            (
                employee_id,
                leave_date,
                reason,
                status
            )
            VALUES
            (
                %s,
                %s,
                %s,
                'Pending'
            )
        """, (
            employee_id,
            leave_date,
            reason
        ))

        conn.commit()

        cur.close()
        conn.close()

        return redirect(
            "/employee_dashboard"
            "?message=Leave application submitted."
        )

    return render_template(
        "apply_leave.html"
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if not session.get("admin"):

        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*)
        FROM employee
    """)

    total_employees = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*)
        FROM attendance
    """)

    total_attendance = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*)
        FROM attendance
        WHERE status='Present'
    """)

    present_count = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*)
        FROM attendance
        WHERE status='Absent'
    """)

    absent_count = cur.fetchone()[0]

    cur.close()
    conn.close()

    return render_template(
        "dashboard.html",
        total_employees=total_employees,
        total_attendance=total_attendance,
        present_count=present_count,
        absent_count=absent_count
    )


# =========================================================
# LEAVE REQUESTS - ADMIN
# =========================================================

@app.route("/leave_requests")
def leave_requests():

    if not session.get("admin"):

        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            leave_request.id,
            leave_request.employee_id,
            employee.name,
            leave_request.leave_date,
            leave_request.reason,
            leave_request.status
        FROM leave_request

        LEFT JOIN employee
        ON leave_request.employee_id =
           employee.employee_id

        ORDER BY leave_request.id DESC
    """)

    requests = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "leave_requests.html",
        requests=requests
    )


# =========================================================
# APPROVE LEAVE
# =========================================================

@app.route(
    "/approve_leave/<int:id>",
    methods=["POST"]
)
def approve_leave(id):

    if not session.get("admin"):

        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE leave_request
        SET status='Approved'
        WHERE id=%s
    """, (
        id,
    ))

    conn.commit()

    cur.close()
    conn.close()

    return redirect(
        "/leave_requests"
    )


# =========================================================
# REJECT LEAVE
# =========================================================

@app.route(
    "/reject_leave/<int:id>",
    methods=["POST"]
)
def reject_leave(id):

    if not session.get("admin"):

        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE leave_request
        SET status='Rejected'
        WHERE id=%s
    """, (
        id,
    ))

    conn.commit()

    cur.close()
    conn.close()

    return redirect(
        "/leave_requests"
    )


# =========================================================
# ADD EMPLOYEE
# =========================================================

@app.route(
    "/add_employee",
    methods=["GET", "POST"]
)
def add_employee():

    if not session.get("admin"):

        return redirect("/login")

    if request.method == "POST":

        employee_id = request.form[
            "employee_id"
        ].strip()

        name = request.form[
            "name"
        ].strip()

        email = request.form[
            "email"
        ].strip()

        department = request.form[
            "department"
        ].strip()

        mobile = request.form[
            "mobile"
        ].strip()

        conn = get_db_connection()
        cur = conn.cursor()

        try:

            cur.execute("""
                INSERT INTO employee
                (
                    employee_id,
                    name,
                    email,
                    department,
                    mobile
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
            """, (
                employee_id,
                name,
                email,
                department,
                mobile
            ))

            conn.commit()

        except psycopg2.IntegrityError:

            conn.rollback()

            cur.close()
            conn.close()

            return """
            <h2 style='color:red;text-align:center;'>
                Employee ID already exists.
            </h2>

            <center>
                <a href='/add_employee'>
                    Go Back
                </a>
            </center>
            """

        cur.close()
        conn.close()

        return redirect(
            "/view_employees"
        )

    return render_template(
        "add_employee.html"
    )


# =========================================================
# VIEW EMPLOYEES
# =========================================================

@app.route("/view_employees")
def view_employees():

    if not session.get("admin"):

        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            employee_id,
            name,
            email,
            department,
            mobile
        FROM employee
        ORDER BY id DESC
    """)

    employees = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "view_employees.html",
        employees=employees
    )


# =========================================================
# EDIT EMPLOYEE
# =========================================================

@app.route(
    "/edit_employee/<int:id>",
    methods=["GET", "POST"]
)
def edit_employee(id):

    if not session.get("admin"):

        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":

        employee_id = request.form[
            "employee_id"
        ].strip()

        name = request.form[
            "name"
        ].strip()

        email = request.form[
            "email"
        ].strip()

        department = request.form[
            "department"
        ].strip()

        mobile = request.form[
            "mobile"
        ].strip()

        try:

            cur.execute("""
                UPDATE employee
                SET
                    employee_id=%s,
                    name=%s,
                    email=%s,
                    department=%s,
                    mobile=%s
                WHERE id=%s
            """, (
                employee_id,
                name,
                email,
                department,
                mobile,
                id
            ))

            conn.commit()

        except psycopg2.IntegrityError:

            conn.rollback()

            cur.close()
            conn.close()

            return """
            <h2 style='color:red;text-align:center;'>
                Employee ID already exists.
            </h2>

            <center>
                <a href='/view_employees'>
                    Back to Employee List
                </a>
            </center>
            """

        cur.close()
        conn.close()

        return redirect(
            "/view_employees"
        )

    cur.execute("""
        SELECT
            id,
            employee_id,
            name,
            email,
            department,
            mobile
        FROM employee
        WHERE id=%s
    """, (
        id,
    ))

    employee = cur.fetchone()

    cur.close()
    conn.close()

    if not employee:

        return "Employee not found."

    return render_template(
        "edit_employee.html",
        employee=employee
    )


# =========================================================
# MARK ATTENDANCE - ADMIN
# =========================================================

@app.route(
    "/mark_attendance",
    methods=["GET", "POST"]
)
def mark_attendance():

    if not session.get("admin"):

        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":

        employee_id = request.form[
            "employee_id"
        ].strip()

        attendance_date = request.form[
            "date"
        ].strip()

        status = request.form[
            "status"
        ].strip()

        # -------------------------------------------------
        # CHECK DUPLICATE
        # -------------------------------------------------

        cur.execute("""
            SELECT id
            FROM attendance
            WHERE employee_id=%s
            AND date=%s
        """, (
            employee_id,
            attendance_date
        ))

        existing = cur.fetchone()

        if existing:

            cur.close()
            conn.close()

            return """
            <h2 style='color:red;text-align:center;'>
                Attendance for this employee and date already exists.
            </h2>

            <center>
                <a href='/mark_attendance'>
                    Back
                </a>
            </center>
            """

        # -------------------------------------------------
        # INSERT ATTENDANCE
        # -------------------------------------------------

        cur.execute("""
            INSERT INTO attendance
            (
                employee_id,
                date,
                status
            )
            VALUES
            (
                %s,
                %s,
                %s
            )
        """, (
            employee_id,
            attendance_date,
            status
        ))

        conn.commit()

        cur.close()
        conn.close()

        return redirect(
            "/attendance_report"
        )

    # -----------------------------------------------------
    # GET EMPLOYEES
    # -----------------------------------------------------

    cur.execute("""
        SELECT
            id,
            employee_id,
            name,
            email,
            department,
            mobile
        FROM employee
        ORDER BY name
    """)

    employees = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "mark_attendance.html",
        employees=employees
    )


# =========================================================
# ATTENDANCE REPORT
# =========================================================

@app.route("/attendance_report")
def attendance_report():

    if not session.get("admin"):

        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            employee_id,
            date,
            status,
            check_in,
            check_out,
            attendance_type
        FROM attendance
        ORDER BY date DESC, id DESC
    """)

    raw_attendance = cur.fetchall()

    attendance = []

    for record in raw_attendance:

        working_hours = calculate_working_hours(
            record[4],
            record[5]
        )

        attendance.append(
            (
                record[0],
                record[1],
                record[2],
                record[3],
                record[4],
                record[5],
                record[6],
                working_hours
            )
        )

    cur.close()
    conn.close()

    return render_template(
        "attendance_report.html",
        attendance=attendance
    )


# =========================================================
# EDIT ATTENDANCE
# =========================================================

@app.route(
    "/edit_attendance/<int:id>",
    methods=["GET", "POST"]
)
def edit_attendance(id):

    if not session.get("admin"):

        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor()

    # -----------------------------------------------------
    # UPDATE ATTENDANCE
    # -----------------------------------------------------

    if request.method == "POST":

        employee_id = request.form[
            "employee_id"
        ].strip()

        attendance_date = request.form[
            "date"
        ].strip()

        status = request.form[
            "status"
        ].strip()

        check_in = request.form.get(
            "check_in",
            ""
        ).strip()

        check_out = request.form.get(
            "check_out",
            ""
        ).strip()

        attendance_type = request.form.get(
            "attendance_type",
            ""
        ).strip()

        cur.execute("""
            UPDATE attendance
            SET
                employee_id=%s,
                date=%s,
                status=%s,
                check_in=%s,
                check_out=%s,
                attendance_type=%s
            WHERE id=%s
        """, (
            employee_id,
            attendance_date,
            status,
            check_in,
            check_out,
            attendance_type,
            id
        ))

        conn.commit()

        cur.close()
        conn.close()

        return redirect(
            "/attendance_report"
        )

    # -----------------------------------------------------
    # GET ATTENDANCE RECORD
    # -----------------------------------------------------

    cur.execute("""
        SELECT
            id,
            employee_id,
            date,
            status,
            check_in,
            check_out,
            attendance_type
        FROM attendance
        WHERE id=%s
    """, (
        id,
    ))

    attendance = cur.fetchone()

    # -----------------------------------------------------
    # GET EMPLOYEES
    # -----------------------------------------------------

    cur.execute("""
        SELECT
            employee_id,
            name
        FROM employee
        ORDER BY name
    """)

    employees = cur.fetchall()

    cur.close()
    conn.close()

    if not attendance:

        return "Attendance record not found."

    return render_template(
        "edit_attendance.html",
        attendance=attendance,
        employees=employees
    )


# =========================================================
# MONTHLY ATTENDANCE REPORT
# =========================================================

@app.route("/monthly_attendance_report")
def monthly_attendance_report():

    if not session.get("admin"):

        return redirect("/login")

    selected_month = request.args.get(
        "month",
        datetime.now().strftime("%Y-%m")
    )

    conn = get_db_connection()
    cur = conn.cursor()

    # -----------------------------------------------------
    # EMPLOYEE-WISE SUMMARY
    # -----------------------------------------------------

    cur.execute("""
        SELECT
            employee.employee_id,
            employee.name,
            employee.department,

            SUM(
                CASE
                    WHEN attendance.status='Present'
                    THEN 1
                    ELSE 0
                END
            ) AS present_days,

            SUM(
                CASE
                    WHEN attendance.status='Absent'
                    THEN 1
                    ELSE 0
                END
            ) AS absent_days,

            COUNT(attendance.id) AS total_days

        FROM employee

        LEFT JOIN attendance

        ON employee.employee_id =
           attendance.employee_id

        AND LEFT(attendance.date, 7) = %s

        GROUP BY
            employee.employee_id,
            employee.name,
            employee.department

        ORDER BY employee.employee_id

    """, (
        selected_month,
    ))

    raw_summary = cur.fetchall()

    summary = []

    for record in raw_summary:

        employee_id = record[0]
        name = record[1]
        department = record[2]

        present_days = record[3] or 0
        absent_days = record[4] or 0
        total_days = record[5] or 0

        if total_days > 0:

            percentage = round(
                (present_days / total_days) * 100,
                2
            )

        else:

            percentage = 0

        summary.append(
            (
                employee_id,
                name,
                department,
                present_days,
                absent_days,
                total_days,
                percentage
            )
        )

    # -----------------------------------------------------
    # MONTHLY DETAILS
    # -----------------------------------------------------

    cur.execute("""
        SELECT
            attendance.date,
            attendance.employee_id,
            employee.name,
            employee.department,
            attendance.status,
            attendance.check_in,
            attendance.check_out,
            attendance.attendance_type

        FROM attendance

        LEFT JOIN employee

        ON attendance.employee_id =
           employee.employee_id

        WHERE LEFT(attendance.date, 7) = %s

        ORDER BY
            attendance.date DESC,
            attendance.id DESC

    """, (
        selected_month,
    ))

    attendance = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "monthly_attendance_report.html",
        selected_month=selected_month,
        summary=summary,
        attendance=attendance
    )


# =========================================================
# SEARCH EMPLOYEE
# =========================================================

@app.route(
    "/search_employee",
    methods=["GET", "POST"]
)
def search_employee():

    if not session.get("admin"):

        return redirect("/login")

    employees = []

    if request.method == "POST":

        employee_id = request.form[
            "employee_id"
        ].strip()

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                id,
                employee_id,
                name,
                email,
                department,
                mobile
            FROM employee
            WHERE employee_id=%s
        """, (
            employee_id,
        ))

        employees = cur.fetchall()

        cur.close()
        conn.close()

    return render_template(
        "search_employee.html",
        employees=employees
    )


# =========================================================
# DELETE EMPLOYEE
# =========================================================

@app.route(
    "/delete_employee/<int:id>"
)
def delete_employee(id):

    if not session.get("admin"):

        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor()

    # -----------------------------------------------------
    # GET EMPLOYEE ID
    # -----------------------------------------------------

    cur.execute("""
        SELECT employee_id
        FROM employee
        WHERE id=%s
    """, (
        id,
    ))

    employee = cur.fetchone()

    if employee:

        employee_id = employee[0]

        # Delete attendance

        cur.execute("""
            DELETE FROM attendance
            WHERE employee_id=%s
        """, (
            employee_id,
        ))

        # Delete leave requests

        cur.execute("""
            DELETE FROM leave_request
            WHERE employee_id=%s
        """, (
            employee_id,
        ))

    # -----------------------------------------------------
    # DELETE EMPLOYEE
    # -----------------------------------------------------

    cur.execute("""
        DELETE FROM employee
        WHERE id=%s
    """, (
        id,
    ))

    conn.commit()

    cur.close()
    conn.close()

    return redirect(
        "/view_employees"
    )


# =========================================================
# ADMIN LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.pop(
        "admin",
        None
    )

    session.pop(
        "employee",
        None
    )

    return redirect(
        "/login"
    )


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),
        debug=False
    )
