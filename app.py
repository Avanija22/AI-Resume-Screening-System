from flask import Flask, render_template, request, redirect
import pdfplumber
import spacy
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import mysql.connector
import os
import re

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

# Load NLP model
nlp = spacy.load("en_core_web_sm")

# Database connection
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="avanija",
    database="resume_ats"
)
cursor = db.cursor()

# ---------- FUNCTIONS ----------

def extract_text(path):
    text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text
    return text.lower()


def calculate_match_and_skills(resume_text, job_desc):
    resume_text = resume_text.lower()
    job_desc = job_desc.lower()

    # ---- Similarity Score ----
    vectorizer = TfidfVectorizer(stop_words='english')
    vectors = vectorizer.fit_transform([resume_text, job_desc])
    similarity = cosine_similarity(vectors[0:1], vectors[1:2])
    score = round(similarity[0][0] * 100, 2)

    # ---- Skill Breakdown ----
    required_skills = [
        "python",
        "sql",
        "flask",
        "machine learning",
        "data analysis"
    ]

    matched_skills = []
    missing_skills = []

    for skill in required_skills:
        if re.search(r'\b' + skill + r'\b', resume_text):
            matched_skills.append(skill)
        else:
            missing_skills.append(skill)

    return score, matched_skills, missing_skills


# ---------- ROUTES ----------

@app.route('/')
def login_page():
    return render_template("login.html")


@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']

    cursor.execute(
        "SELECT * FROM recruiters WHERE username=%s AND password=%s",
        (username, password)
    )
    user = cursor.fetchone()

    if user:
        return redirect('/dashboard')
    return "Invalid Login"


@app.route('/dashboard')
def dashboard():
    cursor.execute("SELECT name, match_score FROM candidates ORDER BY match_score DESC")
    data = cursor.fetchall()

    names = [row[0] for row in data]
    scores = [float(row[1]) for row in data]

    return render_template("dashboard.html", names=names, scores=scores)


@app.route('/create_job', methods=['GET', 'POST'])
def create_job():
    if request.method == 'POST':
        title = request.form['title']
        desc = request.form['description']

        cursor.execute(
            "INSERT INTO jobs (title, description) VALUES (%s,%s)",
            (title, desc)
        )
        db.commit()
        return redirect('/upload')

    return render_template("create_job.html")


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    cursor.execute("SELECT * FROM jobs")
    jobs = cursor.fetchall()

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        job_id = request.form['job_id']
        file = request.files['resume']

        # Save file
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])

        path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(path)

        # Extract resume text
        resume_text = extract_text(path)

        # Get job description
        cursor.execute("SELECT description FROM jobs WHERE id=%s", (job_id,))
        job_desc = cursor.fetchone()[0]

        # Calculate score + skills
        score, matched_skills, missing_skills = calculate_match_and_skills(resume_text, job_desc)

        # ---- Threshold Logic ----
        status = "Shortlisted" if score > 60 else "Rejected"

        # Save to database
        cursor.execute(
            """INSERT INTO candidates 
               (name, email, resume_path, match_score, job_id, status) 
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (name, email, path, score, job_id, status)
        )
        db.commit()

        return render_template(
            "result.html",
            score=score,
            status=status,
            matched_skills=matched_skills,
            missing_skills=missing_skills
        )

    return render_template("upload.html", jobs=jobs)


if __name__ == '__main__':
    app.run(debug=True)