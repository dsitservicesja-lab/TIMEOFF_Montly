import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, flash, g, redirect, render_template, request, session, url_for

MONTHLY_ALLOCATION_HOURS = 4.0


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-key"),
        DATABASE=str(Path(app.instance_path) / "timeoff.db"),
    )

    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
        return g.db

    def close_db(_exc=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def init_db():
        db = get_db()
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS branches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                supervisor_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL CHECK (role IN ('admin', 'supervisor', 'employee')),
                branch_id INTEGER,
                FOREIGN KEY (branch_id) REFERENCES branches (id)
            );

            CREATE TABLE IF NOT EXISTS timeoff_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                branch_id INTEGER NOT NULL,
                request_date TEXT NOT NULL,
                month_key TEXT NOT NULL,
                hours REAL NOT NULL,
                reason TEXT,
                status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'declined')),
                decision_by INTEGER,
                decision_note TEXT,
                created_at TEXT NOT NULL,
                decided_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (branch_id) REFERENCES branches (id),
                FOREIGN KEY (decision_by) REFERENCES users (id)
            );

            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
            """
        )
        db.commit()

    def seed_demo_data():
        db = get_db()
        row = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()
        if row["c"] > 0:
            return

        db.execute("INSERT INTO branches (name) VALUES (?)", ("North",))
        db.execute("INSERT INTO branches (name) VALUES (?)", ("South",))

        north = db.execute("SELECT id FROM branches WHERE name = ?", ("North",)).fetchone()["id"]
        south = db.execute("SELECT id FROM branches WHERE name = ?", ("South",)).fetchone()["id"]

        db.execute("INSERT INTO users (username, role) VALUES (?, ?)", ("admin", "admin"))
        db.execute(
            "INSERT INTO users (username, role, branch_id) VALUES (?, ?, ?)",
            ("sup_north", "supervisor", north),
        )
        db.execute(
            "INSERT INTO users (username, role, branch_id) VALUES (?, ?, ?)",
            ("sup_south", "supervisor", south),
        )
        db.execute(
            "INSERT INTO users (username, role, branch_id) VALUES (?, ?, ?)",
            ("alice", "employee", north),
        )
        db.execute(
            "INSERT INTO users (username, role, branch_id) VALUES (?, ?, ?)",
            ("bob", "employee", south),
        )

        sup_north = db.execute("SELECT id FROM users WHERE username = ?", ("sup_north",)).fetchone()["id"]
        sup_south = db.execute("SELECT id FROM users WHERE username = ?", ("sup_south",)).fetchone()["id"]
        db.execute("UPDATE branches SET supervisor_id = ? WHERE id = ?", (sup_north, north))
        db.execute("UPDATE branches SET supervisor_id = ? WHERE id = ?", (sup_south, south))
        db.commit()

    def current_user():
        uid = session.get("user_id")
        if not uid:
            return None
        return get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()

    def require_login():
        if not current_user():
            return redirect(url_for("login"))
        return None

    def month_key_for(date_text):
        return datetime.strptime(date_text, "%Y-%m-%d").strftime("%Y-%m")

    def branch_supervisor(branch_id):
        return get_db().execute(
            """
            SELECT u.* FROM branches b
            JOIN users u ON u.id = b.supervisor_id
            WHERE b.id = ?
            """,
            (branch_id,),
        ).fetchone()

    def create_notification(user_id, message):
        get_db().execute(
            "INSERT INTO notifications (user_id, message, created_at) VALUES (?, ?, ?)",
            (user_id, message, datetime.now(timezone.utc).isoformat()),
        )
        get_db().commit()

    @app.before_request
    def before_request_setup():
        init_db()
        seed_demo_data()

    app.teardown_appcontext(close_db)

    @app.route("/")
    def index():
        user = current_user()
        if not user:
            return redirect(url_for("login"))
        return redirect(url_for("dashboard"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        db = get_db()
        users = db.execute("SELECT * FROM users ORDER BY username").fetchall()
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if not user:
                flash("Invalid user selected.")
                return render_template("login.html", users=users)
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))
        return render_template("login.html", users=users)

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/dashboard")
    def dashboard():
        login_redirect = require_login()
        if login_redirect:
            return login_redirect

        user = current_user()
        db = get_db()
        month_filter = request.args.get("month") or datetime.now(timezone.utc).strftime("%Y-%m")
        own_requests = db.execute(
            """
            SELECT r.*, u.username, b.name AS branch_name, d.username AS decision_username
            FROM timeoff_requests r
            JOIN users u ON u.id = r.user_id
            JOIN branches b ON b.id = r.branch_id
            LEFT JOIN users d ON d.id = r.decision_by
            WHERE r.user_id = ?
            ORDER BY r.created_at DESC
            """,
            (user["id"],),
        ).fetchall()

        month_usage = db.execute(
            """
            SELECT COALESCE(SUM(hours), 0) AS used_hours
            FROM timeoff_requests
            WHERE user_id = ? AND month_key = ? AND status IN ('pending', 'approved')
            """,
            (user["id"], month_filter),
        ).fetchone()["used_hours"]

        pending_for_supervisor = []
        if user["role"] == "supervisor":
            pending_for_supervisor = db.execute(
                """
                SELECT r.*, u.username
                FROM timeoff_requests r
                JOIN users u ON u.id = r.user_id
                WHERE r.branch_id = ? AND r.status = 'pending'
                ORDER BY r.created_at ASC
                """,
                (user["branch_id"],),
            ).fetchall()

        all_requests = []
        if user["role"] == "admin":
            all_requests = db.execute(
                """
                SELECT r.*, u.username, b.name AS branch_name
                FROM timeoff_requests r
                JOIN users u ON u.id = r.user_id
                JOIN branches b ON b.id = r.branch_id
                ORDER BY r.created_at DESC
                """
            ).fetchall()

        notifications = db.execute(
            """
            SELECT * FROM notifications
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (user["id"],),
        ).fetchall()

        return render_template(
            "dashboard.html",
            user=user,
            own_requests=own_requests,
            month_filter=month_filter,
            monthly_allocation=MONTHLY_ALLOCATION_HOURS,
            month_usage=month_usage,
            pending_for_supervisor=pending_for_supervisor,
            all_requests=all_requests,
            notifications=notifications,
        )

    @app.route("/request-timeoff", methods=["POST"])
    def request_timeoff():
        login_redirect = require_login()
        if login_redirect:
            return login_redirect

        user = current_user()
        if user["role"] not in ("employee", "supervisor"):
            flash("Only branch users can submit requests.")
            return redirect(url_for("dashboard"))

        date_text = request.form.get("request_date", "").strip()
        hours_text = request.form.get("hours", "0").strip()
        reason = request.form.get("reason", "").strip()

        try:
            hours = float(hours_text)
        except ValueError:
            flash("Hours must be a valid number.")
            return redirect(url_for("dashboard"))

        if hours <= 0:
            flash("Hours must be greater than zero.")
            return redirect(url_for("dashboard"))
        if hours > MONTHLY_ALLOCATION_HOURS:
            flash("A single request cannot exceed monthly allocation.")
            return redirect(url_for("dashboard"))

        try:
            month_key = month_key_for(date_text)
        except ValueError:
            flash("Invalid date.")
            return redirect(url_for("dashboard"))

        db = get_db()
        used_hours = db.execute(
            """
            SELECT COALESCE(SUM(hours), 0) AS used_hours
            FROM timeoff_requests
            WHERE user_id = ? AND month_key = ? AND status IN ('pending', 'approved')
            """,
            (user["id"], month_key),
        ).fetchone()["used_hours"]

        if used_hours + hours > MONTHLY_ALLOCATION_HOURS:
            flash(f"Monthly limit exceeded. Already used {used_hours}h in {month_key}.")
            return redirect(url_for("dashboard", month=month_key))

        db.execute(
            """
            INSERT INTO timeoff_requests
            (user_id, branch_id, request_date, month_key, hours, reason, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                user["id"],
                user["branch_id"],
                date_text,
                month_key,
                hours,
                reason,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        db.commit()

        sup = branch_supervisor(user["branch_id"])
        if sup:
            create_notification(
                sup["id"],
                f"New time-off request from {user['username']} for {hours}h on {date_text}.",
            )
        flash("Time-off request submitted.")
        return redirect(url_for("dashboard", month=month_key))

    @app.route("/supervisor/decide/<int:request_id>", methods=["POST"])
    def supervisor_decide(request_id):
        login_redirect = require_login()
        if login_redirect:
            return login_redirect

        user = current_user()
        if user["role"] != "supervisor":
            flash("Supervisor access required.")
            return redirect(url_for("dashboard"))

        decision = request.form.get("decision", "").strip()
        note = request.form.get("note", "").strip()
        if decision not in ("approved", "declined"):
            flash("Invalid decision.")
            return redirect(url_for("dashboard"))

        db = get_db()
        req = db.execute(
            "SELECT * FROM timeoff_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        if not req or req["branch_id"] != user["branch_id"] or req["status"] != "pending":
            flash("Request not available for decision.")
            return redirect(url_for("dashboard"))

        db.execute(
            """
            UPDATE timeoff_requests
            SET status = ?, decision_by = ?, decision_note = ?, decided_at = ?
            WHERE id = ?
            """,
            (decision, user["id"], note, datetime.now(timezone.utc).isoformat(), request_id),
        )
        db.commit()

        create_notification(
            req["user_id"],
            f"Your request on {req['request_date']} was {decision} by {user['username']}.",
        )
        flash(f"Request {decision}.")
        return redirect(url_for("dashboard"))

    @app.route("/reports")
    def reports():
        login_redirect = require_login()
        if login_redirect:
            return login_redirect

        user = current_user()
        if user["role"] not in ("admin", "supervisor"):
            flash("Access denied.")
            return redirect(url_for("dashboard"))

        month_filter = request.args.get("month") or datetime.now(timezone.utc).strftime("%Y-%m")
        db = get_db()
        report_rows = db.execute(
            """
            SELECT u.username, b.name AS branch_name,
                   COALESCE(SUM(CASE WHEN r.status = 'approved' THEN r.hours ELSE 0 END), 0) AS approved_hours,
                   COALESCE(SUM(CASE WHEN r.status = 'pending' THEN r.hours ELSE 0 END), 0) AS pending_hours,
                   COALESCE(SUM(CASE WHEN r.status = 'declined' THEN r.hours ELSE 0 END), 0) AS declined_hours
            FROM users u
            LEFT JOIN branches b ON b.id = u.branch_id
            LEFT JOIN timeoff_requests r ON r.user_id = u.id AND r.month_key = ?
            WHERE u.role IN ('employee', 'supervisor')
            GROUP BY u.id, u.username, b.name
            ORDER BY b.name, u.username
            """,
            (month_filter,),
        ).fetchall()
        return render_template("reports.html", user=user, month_filter=month_filter, report_rows=report_rows)

    @app.route("/admin")
    def admin():
        login_redirect = require_login()
        if login_redirect:
            return login_redirect

        user = current_user()
        if user["role"] != "admin":
            flash("Admin access required.")
            return redirect(url_for("dashboard"))

        db = get_db()
        branches = db.execute(
            """
            SELECT b.id, b.name, u.username AS supervisor_name
            FROM branches b
            LEFT JOIN users u ON u.id = b.supervisor_id
            ORDER BY b.name
            """
        ).fetchall()
        users = db.execute(
            """
            SELECT u.username, u.role, b.name AS branch_name
            FROM users u
            LEFT JOIN branches b ON b.id = u.branch_id
            ORDER BY u.role, u.username
            """
        ).fetchall()
        return render_template("admin.html", user=user, branches=branches, users=users)

    @app.route("/notifications/mark-read", methods=["POST"])
    def mark_notifications_read():
        login_redirect = require_login()
        if login_redirect:
            return login_redirect
        user = current_user()
        get_db().execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user["id"],))
        get_db().commit()
        return redirect(url_for("dashboard"))

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
