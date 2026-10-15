\# HROne Employee Attendance \& Analytics API



A REST API built with \*\*FastAPI\*\* and \*\*MongoDB\*\* for employee management, attendance tracking, attendance regularization, and workforce analytics.



\## Features



\- Employee creation and listing

\- Attendance punch-in and punch-out

\- Attendance records with pagination

\- Attendance regularization with audit history

\- Monthly employee attendance analytics

\- Department attendance summaries

\- Late-arrival leaderboard

\- Daily department attendance trends

\- Database indexes and query execution statistics



\## Tech Stack



\- Python

\- FastAPI

\- MongoDB

\- PyMongo

\- Pydantic



\## Setup



1\. Install Python 3.12 or a compatible version and MongoDB 6.0 or newer.

2\. Install dependencies:



&#x20;  ```bash

&#x20;  pip install -r requirements.txt

&#x20;  ```



3\. Configure `MONGO\_URI` and `MONGO\_DB` in a local `.env` file. Do not commit this file or share database credentials.

4\. Start the API:



&#x20;  ```bash

&#x20;  python -m uvicorn app.main:app --reload

&#x20;  ```



5\. Open the interactive API documentation at `http://127.0.0.1:8000/docs`.



\## Project Structure



\- `app/main.py` — API implementation

\- `requirements.txt` — Python dependencies

\- `DATA\_MODEL.md` — Database model documentation

\- `openapi.yaml` — API contract

\- `REVIEW.md` — Assessment review notes

\- `DECISIONS.md` — Design decisions

\- `sample\_data/` — Sample dataset

\- `sample\_seed.py` — Sample data loader



\## Assessment



Developed as part of the HROne Software Engineer hiring assessment for an Employee Attendance \& Analytics API.

