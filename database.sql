-- PostgreSQL setup
-- First create a database named smart_recruitment_basic in pgAdmin.
-- Then connect to that database and run the SQL below.

CREATE TYPE user_role AS ENUM ('Candidate', 'HR', 'Interviewer');
CREATE TYPE application_status AS ENUM ('Pending', 'Shortlisted', 'Rejected');
CREATE TYPE interview_status AS ENUM ('Scheduled', 'Completed', 'Cancelled');

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    role user_role NOT NULL,
    skills TEXT NOT NULL DEFAULT '',
    experience_years INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE jobs (
    id SERIAL PRIMARY KEY,
    title VARCHAR(150) NOT NULL,
    description TEXT NOT NULL,
    department VARCHAR(100) NOT NULL,
    deadline DATE NOT NULL,
    posted_by INTEGER NOT NULL,
    required_skills TEXT NOT NULL DEFAULT '',
    minimum_experience INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (posted_by) REFERENCES users(id)
);

CREATE TABLE applications (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL,
    candidate_id INTEGER NOT NULL,
    resume_path VARCHAR(255) NOT NULL,
    status application_status DEFAULT 'Pending',
    match_score INTEGER NOT NULL DEFAULT 0,
    match_details TEXT NOT NULL DEFAULT '',
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (job_id, candidate_id),
    FOREIGN KEY (job_id) REFERENCES jobs(id),
    FOREIGN KEY (candidate_id) REFERENCES users(id)
);

CREATE TABLE availability (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE interviews (
    id SERIAL PRIMARY KEY,
    application_id INTEGER NOT NULL UNIQUE,
    candidate_id INTEGER NOT NULL,
    interviewer_id INTEGER NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    status interview_status DEFAULT 'Scheduled',
    FOREIGN KEY (application_id) REFERENCES applications(id),
    FOREIGN KEY (candidate_id) REFERENCES users(id),
    FOREIGN KEY (interviewer_id) REFERENCES users(id)
);

CREATE TABLE feedback (
    id SERIAL PRIMARY KEY,
    interview_id INTEGER NOT NULL,
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    comments TEXT,
    FOREIGN KEY (interview_id) REFERENCES interviews(id)
);

-- Run these lines too if you created the tables before adding score features.
ALTER TABLE users ADD COLUMN IF NOT EXISTS skills TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS experience_years INTEGER NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS required_skills TEXT NOT NULL DEFAULT '';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS minimum_experience INTEGER NOT NULL DEFAULT 0;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS match_score INTEGER NOT NULL DEFAULT 0;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS match_details TEXT NOT NULL DEFAULT '';
