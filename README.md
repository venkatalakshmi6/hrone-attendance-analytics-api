# HROne Employee Attendance & Analytics API

A REST API built with **FastAPI** and **MongoDB** for employee management, attendance tracking, attendance regularization, and workforce analytics.

## Features

- Employee creation and listing
- Attendance punch-in and punch-out
- Attendance records with pagination
- Attendance regularization with audit history
- Monthly employee attendance analytics
- Department attendance summaries
- Late-arrival leaderboard
- Daily department attendance trends
- Database indexes and query execution statistics

## Tech Stack

- Python
- FastAPI
- MongoDB
- PyMongo
- Pydantic

## Setup

1. Install Python 3.12 or a compatible version and MongoDB 6.0 or newer.
2. Open a terminal in the project root and install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Configure `MONGO_URI` and `MONGO_DB` in a local `.env` file. Never commit `.env` or share database credentials.
4. Start the API:

   ```bash
   python -m uvicorn app.main:app --reload
   ```

5. Open Swagger UI at `http://127.0.0.1:8000/docs`.

## Project Structure

- `app/main.py` — API implementation
- `requirements.txt` — Python dependencies
- `REVIEW.md` — Assessment review notes
- `DECISIONS.md` — Design decisions
  

## Assessment

Developed as part of the HROne Software Engineer hiring assessment for an Employee Attendance & Analytics API.
