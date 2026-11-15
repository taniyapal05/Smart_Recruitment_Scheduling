import os
import uuid

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from psycopg2 import errors

app = Flask(__name__)

# Change this text before presenting/deploying the project.
app.secret_key = "change-this-secret-key"
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB
ALLOWED_FILES = {"pdf", "docx"}


def get_db():
    """Open a connection to PostgreSQL. Change only the password below."""
    return psycopg2.connect(
        host="localhost",
        port="5432",
        user="postgres",
        password="system",
        database="smart_recruitment_basic",
    )


def logged_in():
    return "user_id" in session


def allowed_file(filename):
    """Return True only for PDF or DOCX files."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_FILES


def calculate_match_score(job, candidate):
    """Create a transparent, job-related score for HR review only.

    Skills match: 60 points
    Experience match: 30 points
    Resume uploaded: 10 points
    """
    required_skills = {skill.strip().lower() for skill in job["required_skills"].split(",") if skill.strip()}
    candidate_skills = {skill.strip().lower() for skill in (candidate["skills"] or "").split(",") if skill.strip()}

    matched_skills = required_skills.intersection(candidate_skills)
    skills_score = round((len(matched_skills) / len(required_skills)) * 60) if required_skills else 0

    minimum_experience = job["minimum_experience"] or 0
    candidate_experience = candidate["experience_years"] or 0
    if minimum_experience == 0:
        experience_score = 30
    else:
        experience_score = round(min(candidate_experience / minimum_experience, 1) * 30)

    resume_score = 10
    total_score = skills_score + experience_score + resume_score
    details = (
        f"Skills: {len(matched_skills)}/{len(required_skills)} ({skills_score}/60); "
        f"Experience: {candidate_experience}/{minimum_experience} years ({experience_score}/30); "
        f"Resume: {resume_score}/10"
    )
    return total_score, details


def user_is_available(user_id, start_time, end_time):
    """Check whether a user's added free-time slot covers the interview time."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        """SELECT id FROM availability
           WHERE user_id = %s AND start_time <= %s AND end_time >= %s""",
        (user_id, start_time, end_time),
    )
    result = cursor.fetchone()
    cursor.close()
    db.close()
    return result is not None

@app.route("/")
def home():
    db = get_db()
    cursor = db.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT jobs.*, users.name AS hr_name FROM jobs JOIN users ON jobs.posted_by = users.id ORDER BY jobs.id DESC")
    jobs = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template("home.html", jobs=jobs)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        role = request.form["role"]
        skills = request.form.get("skills", "") if role == "Candidate" else ""
        try:
            experience_years = max(0, int(request.form.get("experience_years", 0))) if role == "Candidate" else 0
        except ValueError:
            flash("Experience must be a whole number.")
            return render_template("register.html")

        db = get_db()
        cursor = db.cursor()
        try:
            cursor.execute(
                """INSERT INTO users (name, email, password, role, skills, experience_years)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (name, email, generate_password_hash(password), role, skills, experience_years),
            )
            db.commit()
            flash("Registration successful. Please log in.")
            return redirect(url_for("login"))
        except psycopg2.Error:
            flash("This email is already registered.")
        finally:
            cursor.close()
            db.close()
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        db = get_db()
        cursor = db.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM users WHERE email = %s", (request.form["email"],))
        user = cursor.fetchone()
        cursor.close()
        db.close()
        if user and check_password_hash(user["password"], request.form["password"]):
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            return redirect(url_for("home"))
        flash("Incorrect email or password.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/add-job", methods=["GET", "POST"])
def add_job():
    if not logged_in() or session["role"] != "HR":
        flash("Only HR can post jobs.")
        return redirect(url_for("home"))
    if request.method == "POST":
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """INSERT INTO jobs
               (title, description, department, deadline, posted_by, required_skills, minimum_experience)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (request.form["title"], request.form["description"], request.form["department"],
             request.form["deadline"], session["user_id"], request.form.get("required_skills", ""),
             int(request.form.get("minimum_experience", 0) or 0)),
        )
        db.commit()
        cursor.close()
        db.close()
        flash("Job posted successfully.")
        return redirect(url_for("home"))
    return render_template("add_job.html")


@app.route("/apply/<int:job_id>", methods=["POST"])
def apply(job_id):
    if not logged_in() or session["role"] != "Candidate":
        flash("Only candidates can apply for jobs.")
        return redirect(url_for("home"))
    resume = request.files.get("resume")
    if not resume or not allowed_file(resume.filename):
        flash("Please upload a PDF or DOCX resume.")
        return redirect(url_for("home"))

    # uuid gives every file a unique name, so one resume cannot overwrite another.
    extension = secure_filename(resume.filename).rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{extension}"
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    resume_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    resume.save(resume_path)

    db = get_db()
    cursor = db.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("SELECT required_skills, minimum_experience FROM jobs WHERE id = %s", (job_id,))
        job = cursor.fetchone()
        cursor.execute("SELECT skills, experience_years FROM users WHERE id = %s", (session["user_id"],))
        candidate = cursor.fetchone()
        if not job or not candidate:
            flash("Job or candidate profile was not found.")
            return redirect(url_for("home"))

        match_score, match_details = calculate_match_score(job, candidate)
        cursor.execute(
            """INSERT INTO applications
               (job_id, candidate_id, resume_path, match_score, match_details)
               VALUES (%s, %s, %s, %s, %s)""",
            (job_id, session["user_id"], resume_path, match_score, match_details),
        )
        db.commit()
        flash("Application submitted. HR will review the job-match evidence.")
    except psycopg2.Error:
        flash("You have already applied for this job.")
    finally:
        cursor.close()
        db.close()
    return redirect(url_for("home"))
@app.route("/applications/<int:job_id>")
def applications(job_id):
    if not logged_in() or session["role"] != "HR":
        return redirect(url_for("home"))
    db = get_db()
    cursor = db.cursor(cursor_factory=RealDictCursor)
    cursor.execute(
        """SELECT applications.*, users.name, users.email
           FROM applications JOIN users ON applications.candidate_id = users.id
           WHERE applications.job_id = %s""", (job_id,)
    )
    rows = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template("applications.html", applications=rows, job_id=job_id)


@app.route("/application/<int:application_id>/<status>")
def change_status(application_id, status):
    if not logged_in() or session["role"] != "HR" or status not in ("Shortlisted", "Rejected"):
        return redirect(url_for("home"))
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE applications SET status = %s WHERE id = %s", (status, application_id))
    db.commit()
    cursor.close()
    db.close()
    flash(f"Candidate {status.lower()} by HR.")
    return redirect(request.referrer or url_for("home"))


@app.route("/availability", methods=["GET", "POST"])
def availability():
    if not logged_in():
        return redirect(url_for("login"))
    if request.method == "POST":
        start_time = request.form["start_time"]
        end_time = request.form["end_time"]
        if end_time <= start_time:
            flash("End time must be later than start time.")
        else:
            db = get_db()
            cursor = db.cursor()
            cursor.execute("INSERT INTO availability (user_id, start_time, end_time) VALUES (%s, %s, %s)",
                           (session["user_id"], start_time, end_time))
            db.commit()
            cursor.close()
            db.close()
            flash("Availability slot added.")
    db = get_db()
    cursor = db.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM availability WHERE user_id = %s ORDER BY start_time", (session["user_id"],))
    slots = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template("availability.html", slots=slots)


@app.route("/schedule/<int:application_id>", methods=["GET", "POST"])
def schedule(application_id):
    if not logged_in() or session["role"] != "HR":
        return redirect(url_for("home"))
    db = get_db()
    cursor = db.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM applications WHERE id = %s AND status = 'Shortlisted'", (application_id,))
    application = cursor.fetchone()
    if not application:
        cursor.close(); db.close()
        flash("Only shortlisted candidates can be scheduled.")
        return redirect(url_for("home"))

    if request.method == "POST":
        interviewer_id = request.form["interviewer_id"]
        start_time = request.form["start_time"]
        end_time = request.form["end_time"]

        # This is the important OS/DBMS check: both people must be free and not already booked.
        cursor.execute(
            """SELECT id FROM interviews WHERE status = 'Scheduled'
               AND (candidate_id = %s OR interviewer_id = %s)
               AND start_time < %s AND end_time > %s""",
            (application["candidate_id"], interviewer_id, end_time, start_time),
        )
        conflict = cursor.fetchone()
        if conflict or not user_is_available(application["candidate_id"], start_time, end_time) or not user_is_available(interviewer_id, start_time, end_time):
            flash("Cannot schedule: candidate/interviewer is unavailable or already booked.")
        else:
            try:
                cursor.execute(
                    """INSERT INTO interviews
                    (application_id, candidate_id, interviewer_id,
                        start_time, end_time)
                    VALUES (%s, %s, %s, %s, %s)""",
                    (
                        application_id,
                        application["candidate_id"],
                        interviewer_id,
                        start_time,
                        end_time,
                    ),
                )

                db.commit()
                flash("Interview scheduled successfully.")

            except errors.ExclusionViolation:
                db.rollback()
                flash(
                    "Booking conflict: this candidate or interviewer "
                    "already has an overlapping interview."
                )

            finally:
                cursor.close()
                db.close()

            return redirect(url_for("home"))


    cursor.execute("SELECT id, name FROM users WHERE role = 'Interviewer'")
    interviewers = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template("schedule.html", application=application, interviewers=interviewers)


if __name__ == "__main__":
    app.run(debug=True)
