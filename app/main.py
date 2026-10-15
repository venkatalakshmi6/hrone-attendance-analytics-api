"""
Employee Attendance & Analytics API - STARTER

Run:  uvicorn app.main:app --port 8000
Env:  MONGO_URI, MONGO_DB (a local .env is loaded for convenience)

This file was written quickly by a colleague who has left the company. The happy path
works, but nobody has reviewed it. Read PROBLEM_STATEMENT.docx for what is expected of you,
openapi.yaml for the contract and DATA_MODEL.md for what is stored in MongoDB.
"""


import os
import calendar
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, StrictInt, Field, ConfigDict, field_validator
from pymongo import MongoClient
from bson.json_util import dumps, loads
from pymongo.errors import DuplicateKeyError


load_dotenv()

client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
db = client[os.getenv("MONGO_DB", "attendance_db")]
# Create database indexes automatically
db.employees.create_index("emp_code", unique=True)
db.employees.create_index("joined_on")
db.attendance_logs.create_index(
    [("emp_code", 1), ("date", 1)],
    unique=True,
)
db.attendance_logs.create_index([("date", -1), ("emp_code", 1)])

IST = timezone(timedelta(hours=5, minutes=30))

app = FastAPI(title="Employee Attendance & Analytics API", version="2.0.0")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def compute_late_minutes(
    punch_in: datetime,
    shift_start: str,
    shift_end: str,
) -> int:
    if punch_in.tzinfo is None:
        punch_in = punch_in.replace(tzinfo=IST)
    else:
        punch_in = punch_in.astimezone(IST)

    h, m = map(int, shift_start.split(":"))

    start = punch_in.replace(
        hour=h,
        minute=m,
        second=0,
        microsecond=0,
    )

    # For an overnight shift, early-morning punches
    # belong to the shift that started the previous day.
    if (
        shift_end <= shift_start
        and punch_in.strftime("%H:%M") < shift_end
    ):
        start -= timedelta(days=1)

    elapsed_seconds = (punch_in - start).total_seconds()

    if elapsed_seconds > 10 * 60:
        return max(0, int(elapsed_seconds // 60))

    return 0




from decimal import Decimal, ROUND_HALF_UP

def compute_work_hours(punch_in: datetime, punch_out: datetime) -> float:
    seconds = Decimal(str((punch_out - punch_in).total_seconds()))
    hours = seconds / Decimal("3600")
    return float(hours.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))




def compute_overtime(
    punch_out: datetime,
    shift_end: str,
    date_str: str,
    shift_start: str = "09:30",
) -> int:
    h, m = map(int, shift_end.split(":"))
    end = datetime.fromisoformat(date_str).replace(
        hour=h,
        minute=m,
        second=0,
        microsecond=0,
        tzinfo=IST,
    )

    # For an overnight shift, the shift ends the following day.
    if shift_end <= shift_start:
        end += timedelta(days=1)

    minutes = int((punch_out - end).total_seconds() // 60)

    # Overtime counts only when it reaches 30 whole minutes.
    if minutes >= 30:
        return minutes

    return 0



# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #

from pydantic import Field

class EmployeeIn(BaseModel):
    emp_code: str = Field(pattern=r"^EMP\d{4,6}$")
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    department: str = Field(min_length=1, max_length=50)
    shift_start: str = Field(
        default="09:30",
        pattern=r"^([01]\d|2[0-3]):[0-5]\d$",
    )
    shift_end: str = Field(
        default="18:30",
        pattern=r"^([01]\d|2[0-3]):[0-5]\d$",
    )
    joined_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    @field_validator("joined_on")
    @classmethod
    def validate_joined_on(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise ValueError(
                "joined_on must be a valid date in YYYY-MM-DD format"
            )
        return value




class PunchInIn(BaseModel):
    emp_code: str
    punched_at: Optional[StrictInt] = None
    status: str = "PRESENT"


class PunchOutIn(BaseModel):
    emp_code: str
    punched_at: Optional[StrictInt] = None



class RegularizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Optional[str] = None
    punch_in: Optional[StrictInt] = None
    punch_out: Optional[StrictInt] = None
    reason: str = Field(min_length=5, max_length=200)
    regularized_by: str = Field(min_length=1, max_length=50)


# --------------------------------------------------------------------------- #
# Endpoints provided
# --------------------------------------------------------------------------- #

@app.get("/health")
def health():
    try:
        db.command("ping")
        return {"status": "ok"}
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="MongoDB is unavailable",
        )



@app.post("/employees", status_code=201)
def create_employee(body: EmployeeIn):
    if body.shift_start == body.shift_end:
        raise HTTPException(
            status_code=422,
            detail="shift_start and shift_end must differ",
        )

    doc = body.model_dump()
    doc["created_at"] = datetime.now(IST)

    try:
        db.employees.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="emp_code already exists",
        )


    doc.pop("_id", None)

    if doc.get("created_at") is not None:
        doc["created_at"] = int(
            doc["created_at"].timestamp() * 1000
        )

    return doc


@app.get("/employees")
def list_employees(
    department: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    if page < 1:
        raise HTTPException(422, "page must be at least 1")

    if page_size < 1 or page_size > 100:
        raise HTTPException(
            422,
            "page_size must be between 1 and 100",
        )

    q = {}

    if department is not None:
        q["department"] = department

    skip = (page - 1) * page_size

    total = db.employees.count_documents(q)

    items = list(
        db.employees.find(q, {"_id": 0})
        .sort("emp_code", 1)
        .skip(skip)
        .limit(page_size)
    )
    for item in items:
        if item.get("created_at") is not None:
            item["created_at"] = int(
                item["created_at"].timestamp() * 1000
            )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }



@app.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInIn):
    # Validate attendance status
    allowed_statuses = {"PRESENT", "WFH", "ON_DUTY"}

    if body.status not in allowed_statuses:
        raise HTTPException(
            status_code=422,
            detail="Invalid attendance status",
        )
    # Validate timestamp
    if body.punched_at is not None:
        if not 100_000_000_000 <= body.punched_at <= 4_102_444_800_000:
            raise HTTPException(
                status_code=422,
                detail="punched_at must be valid epoch milliseconds",
            )

    # Check whether the employee exists
    emp = db.employees.find_one({"emp_code": body.emp_code})

    if emp is None:
        raise HTTPException(
            status_code=404,
            detail="Employee not found",
        )

    # Convert the supplied epoch milliseconds to IST.
    # If no timestamp is supplied, use the current time.
    if body.punched_at is not None:
        ts = datetime.fromtimestamp(
            body.punched_at / 1000,
            tz=timezone.utc,
        ).astimezone(IST)
    else:
        ts = datetime.now(timezone.utc).astimezone(IST)

    # Truncate to whole seconds
    ts = ts.replace(microsecond=0)

    # Determine the attendance date in IST
    attendance_date = ts.date()

    # For overnight shifts, early-morning punches belong to
    # the shift that started on the previous calendar day.
    shift_start = emp["shift_start"]
    shift_end = emp["shift_end"]

    if (
        shift_end <= shift_start
        and ts.strftime("%H:%M") < shift_end
    ):
        attendance_date -= timedelta(days=1)

    date_str = attendance_date.isoformat()


    doc = {
        "emp_code": body.emp_code,
        "date": date_str,
        "status": body.status,
        "punch_in": ts,
        "punch_out": None,
        "work_hours": None,
        "late_minutes": compute_late_minutes(
        ts, shift_start, shift_end
        ),
        "overtime_minutes": 0,
        "half_day": False,
        "history": [],
    }

    try:
        db.attendance_logs.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="already punched in for this date",
        )

    # Prepare the response without MongoDB's internal _id
    response = {
        key: value
        for key, value in doc.items()
        if key != "_id"
    }

    # Convert punch_in to epoch milliseconds
    if response["punch_in"] is not None:
        response["punch_in"] = int(
            response["punch_in"].timestamp() * 1000
        )

    return response

@app.post("/attendance/punch-out")
def punch_out(body: PunchOutIn):
    # 1. Validate the supplied timestamp.
    if body.punched_at is not None:
        if not 100_000_000_000 <= body.punched_at <= 4_102_444_800_000:
            raise HTTPException(
                status_code=422,
                detail="punched_at must be valid epoch milliseconds",
            )

    # 2. Check whether the employee exists.
    emp = db.employees.find_one({"emp_code": body.emp_code})

    if emp is None:
        raise HTTPException(
            status_code=404,
            detail="Employee not found",
        )

    # 3. Get the punch-out time and remove fractional seconds.
    if body.punched_at is not None:
        punch_out_ist = datetime.fromtimestamp(
            body.punched_at / 1000,
            tz=timezone.utc,
        ).astimezone(IST)
    else:
        punch_out_ist = datetime.now(IST)

    punch_out_ist = punch_out_ist.replace(microsecond=0)

    # MongoDB stores timestamps in UTC.
    punch_out_utc = punch_out_ist.astimezone(timezone.utc)
    punch_out_db = punch_out_utc.replace(tzinfo=None)

    # 4. Find the latest attendance record that started
    # at or before the punch-out time.
    record = db.attendance_logs.find_one(
        {
            "emp_code": body.emp_code,
            "punch_in": {
                "$ne": None,
                "$lte": punch_out_db,
            },
        },
        sort=[("punch_in", -1)],
    )

    if record is None:
        raise HTTPException(
            status_code=404,
            detail="No punch-in found",
        )

    # 5. Prevent a second punch-out.
    if record.get("punch_out") is not None:
        raise HTTPException(
            status_code=409,
            detail="Already punched out",
        )

    # PyMongo normally returns naive datetimes in UTC.
    punch_in_utc = record["punch_in"].replace(
        tzinfo=timezone.utc
    )

    # 6. The punch-out must be after punch-in and
    # no more than 24 hours later.
    elapsed_seconds = (
        punch_out_utc - punch_in_utc
    ).total_seconds()

    if elapsed_seconds <= 0 or elapsed_seconds > 24 * 60 * 60:
        raise HTTPException(
            status_code=422,
            detail="Punch-out must be after punch-in and within 24 hours",
        )

    # 7. Calculate the total work hours.
    work_hours = compute_work_hours(
        punch_in_utc,
        punch_out_utc,
    )

    # 8. Calculate overtime using the employee's shift.
    overtime_minutes = compute_overtime(
        punch_out_ist,
        emp["shift_end"],
        record["date"],
        emp["shift_start"],
    )

    # 9. A half-day means rounded work hours below 4.50.
    half_day = work_hours < 4.50

    # 10. Update only if another request has not already
    # punched out this attendance record.
    result = db.attendance_logs.update_one(
        {
            "_id": record["_id"],
            "punch_out": None,
        },
        {
            "$set": {
                "punch_out": punch_out_db,
                "work_hours": work_hours,
                "overtime_minutes": overtime_minutes,
                "half_day": half_day,
            }
        },
    )

    if result.modified_count != 1:
        raise HTTPException(
            status_code=409,
            detail="Already punched out",
        )

    # 11. Read the updated record and format timestamps
    # as epoch milliseconds for the API response.
    updated = db.attendance_logs.find_one(
        {"_id": record["_id"]},
        {"_id": 0},
    )

    for field in ("punch_in", "punch_out"):
        value = updated.get(field)

        if isinstance(value, datetime):
            updated[field] = int(
                value.replace(tzinfo=timezone.utc).timestamp()
                * 1000
            )

    updated.setdefault("history", [])
    updated.setdefault("half_day", False)

    return updated

@app.patch("/attendance/{emp_code}/{date}")
def regularize_attendance(
    emp_code: str,
    date: str,
    body: RegularizeRequest,
):
    # Step 1: Validate the date format.
    try:
        attendance_date = datetime.strptime(date, "%Y-%m-%d").date()

        # Reject dates that are not exactly YYYY-MM-DD.
        if attendance_date.isoformat() != date:
            raise ValueError("Invalid date format")

    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="date must be in YYYY-MM-DD format",
        )

    # Step 2: Check whether the employee exists.
    emp = db.employees.find_one({"emp_code": emp_code})

    if emp is None:
        raise HTTPException(
            status_code=404,
            detail="Employee not found",
        )

    # Step 3: Find the attendance record for that employee and date.
    record = db.attendance_logs.find_one(
        {
            "emp_code": emp_code,
            "date": date,
        }
    )

    if record is None:
        raise HTTPException(
            status_code=404,
            detail="Attendance record not found",
        )

    # Step 4: Validate the requested status.
    allowed_statuses = {
        "PRESENT",
        "WFH",
        "ON_DUTY",
        "ABSENT",
        "LEAVE",
    }

    if "status" in body.model_fields_set:
        if body.status not in allowed_statuses:
            raise HTTPException(
                status_code=422,
                detail="Invalid attendance status",
            )

    # Step 5: Validate supplied timestamps.
    for field in ("punch_in", "punch_out"):
        if field in body.model_fields_set:
            timestamp = getattr(body, field)

            if timestamp is not None:
                if not 100_000_000_000 <= timestamp <= 4_102_444_800_000:
                    raise HTTPException(
                        status_code=422,
                        detail=f"{field} must be valid epoch milliseconds",
                    )

    # Step 6: Prepare the final values.
    final_status = (
        body.status
        if "status" in body.model_fields_set
        else record["status"]
    )

    final_punch_in = (
        body.punch_in
        if "punch_in" in body.model_fields_set
        else record.get("punch_in")
    )

    final_punch_out = (
        body.punch_out
        if "punch_out" in body.model_fields_set
        else record.get("punch_out")
    )

    # Step 7: Handle ABSENT and LEAVE statuses.
    if final_status in {"ABSENT", "LEAVE"}:
        if (
            "punch_in" in body.model_fields_set
            or "punch_out" in body.model_fields_set
        ):
            raise HTTPException(
                status_code=422,
                detail="ABSENT and LEAVE cannot include punch times",
            )

        final_punch_in = None
        final_punch_out = None

    # Step 8: Presence statuses require a punch-in time.
    elif final_punch_in is None:
        raise HTTPException(
            status_code=422,
            detail="Presence status requires punch_in",
        )

    # Step 9: Convert epoch milliseconds into IST datetimes.
    def to_ist_datetime(value):
        if value is None:
            return None

        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(
                value / 1000,
                tz=timezone.utc,
            ).astimezone(IST)

        # MongoDB returns stored datetimes as naive UTC values.
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)

        return value.astimezone(IST)

    final_punch_in_dt = to_ist_datetime(final_punch_in)
    final_punch_out_dt = to_ist_datetime(final_punch_out)

    # Step 10: Validate punch-in date.
    if final_punch_in_dt is not None:
        if final_punch_in_dt.date() != attendance_date:
            raise HTTPException(
                status_code=422,
                detail="punch_in must be on the attendance date",
            )

    # Step 11: Validate punch-out time.
    if final_punch_out_dt is not None:
        if final_punch_in_dt is None:
            raise HTTPException(
                status_code=422,
                detail="punch_out requires punch_in",
            )

        elapsed_seconds = (
            final_punch_out_dt - final_punch_in_dt
        ).total_seconds()

        if elapsed_seconds <= 0 or elapsed_seconds > 24 * 60 * 60:
            raise HTTPException(
                status_code=422,
                detail="Punch-out must be after punch-in and within 24 hours",
            )

    # Step 12: Calculate the derived attendance fields.
    if final_status in {"ABSENT", "LEAVE"}:
        final_late_minutes = 0
        final_work_hours = None
        final_overtime_minutes = 0
        final_half_day = False

    else:
        final_late_minutes = compute_late_minutes(
            final_punch_in_dt,
            emp["shift_start"],
            emp["shift_end"],
        )

        if final_punch_out_dt is not None:
            final_work_hours = compute_work_hours(
                final_punch_in_dt,
                final_punch_out_dt,
            )

            final_overtime_minutes = compute_overtime(
                final_punch_out_dt,
                emp["shift_end"],
                date,
                emp["shift_start"],
            )

            final_half_day = final_work_hours < 4.50

        else:
            final_work_hours = None
            final_overtime_minutes = 0
            final_half_day = False

    # Step 13: Prepare the values that may change.
    def stored_datetime(value):
        if value is None:
            return None

        return value.astimezone(timezone.utc).replace(tzinfo=None)

    final_punch_in_db = stored_datetime(final_punch_in_dt)
    final_punch_out_db = stored_datetime(final_punch_out_dt)

    old_values = {
        "status": record.get("status"),
        "punch_in": record.get("punch_in"),
        "punch_out": record.get("punch_out"),
        "work_hours": record.get("work_hours"),
        "late_minutes": record.get("late_minutes", 0),
        "overtime_minutes": record.get("overtime_minutes", 0),
        "half_day": record.get("half_day", False),
    }

    new_values = {
        "status": final_status,
        "punch_in": final_punch_in_db,
        "punch_out": final_punch_out_db,
        "work_hours": final_work_hours,
        "late_minutes": final_late_minutes,
        "overtime_minutes": final_overtime_minutes,
        "half_day": final_half_day,
    }

   
    # Step 14: Find the fields that actually changed.
    changes = {}

    for field in new_values:
        old_value = old_values[field]
        new_value = new_values[field]

        # Convert datetime values to epoch milliseconds for history.
        if field in {"punch_in", "punch_out"}:
            old_history_value = (
                int(old_value.replace(tzinfo=timezone.utc).timestamp() * 1000)
                if isinstance(old_value, datetime)
                else None
            )
            new_history_value = (
                int(new_value.replace(tzinfo=timezone.utc).timestamp() * 1000)
                if isinstance(new_value, datetime)
                else None
            )
        else:
            old_history_value = old_value
            new_history_value = new_value

        if old_history_value != new_history_value:
            changes[field] = {
                "from": old_history_value,
                "to": new_history_value,
            }

    # Reject requests that do not change any attendance fields.
    if not changes:
        raise HTTPException(
            status_code=422,
            detail="The request does not change any attendance fields",
        )



    # Step 15: Create the history entry.
    history_entry = {
        "at": datetime.now(timezone.utc).replace(microsecond=0),
        "by": body.regularized_by,
        "reason": body.reason,
        "changes": changes,
    }


    # Step 16: Prepare the MongoDB update.
    update_filter = {
        "_id": record["_id"],
    }

    # Check whether the history has changed.
    if "history" in record:
        update_filter["history"] = record["history"]
    else:
        update_filter["history"] = {"$exists": False}

    # Step 17: Prepare the attendance fields to save.
    update_fields = {
        "status": new_values["status"],
        "punch_in": new_values["punch_in"],
        "punch_out": new_values["punch_out"],
        "work_hours": new_values["work_hours"],
        "late_minutes": new_values["late_minutes"],
        "overtime_minutes": new_values["overtime_minutes"],
        "half_day": new_values["half_day"],
    }

    # Step 18: Save attendance fields and history together.
    result = db.attendance_logs.update_one(
        update_filter,
        {
            "$set": update_fields,
            "$push": {"history": history_entry},
        },
    )

    # Step 19: Check whether the update succeeded.
    if result.modified_count != 1:
        raise HTTPException(
            status_code=409,
            detail="Attendance record changed concurrently; please retry",
        )

    # Step 20: Fetch the updated attendance record.
    updated = db.attendance_logs.find_one(
        {"_id": record["_id"]},
        {"_id": 0},
    )

    if updated is None:
        raise HTTPException(
            status_code=404,
            detail="Attendance record not found",
        )

    # Step 21: Convert punch timestamps to epoch milliseconds.
    for field in ("punch_in", "punch_out"):
        value = updated.get(field)

        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)

            updated[field] = int(value.timestamp() * 1000)

    # Step 22: Convert history timestamps to epoch milliseconds.
    for entry in updated.get("history", []):
        value = entry.get("at")

        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)

            entry["at"] = int(value.timestamp() * 1000)
        # Step 23: Return the updated attendance record.
    return updated



@app.get("/attendance")
def list_attendance(
    emp_code: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    # Validate pagination
    if page < 1:
        raise HTTPException(
            status_code=422,
            detail="page must be at least 1",
        )

    if page_size < 1 or page_size > 100:
        raise HTTPException(
            status_code=422,
            detail="page_size must be between 1 and 100",
        )

    # Validate date formats
    for date_value in (date_from, date_to):
        if date_value is not None:
            try:
                parsed_date = datetime.strptime(date_value, "%Y-%m-%d")
                if parsed_date.strftime("%Y-%m-%d") != date_value:
                    raise ValueError
            except ValueError:
                raise HTTPException(
                    status_code=422,
                    detail="Dates must use YYYY-MM-DD format",
                )

    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=422,
            detail="date_from must not be after date_to",
        )

    # Validate attendance status
    allowed_statuses = {
        "PRESENT", "WFH", "ON_DUTY", "ABSENT", "LEAVE"
    }

    if status is not None and status not in allowed_statuses:
        raise HTTPException(
            status_code=422,
            detail="Invalid attendance status",
        )

    # Build MongoDB filters
    query = {}

    if emp_code:
        query["emp_code"] = emp_code

    if date_from or date_to:
        query["date"] = {}

        if date_from:
            query["date"]["$gte"] = date_from

        if date_to:
            query["date"]["$lte"] = date_to

    if status:
        query["status"] = status

    total = db.attendance_logs.count_documents(query)

    skip = (page - 1) * page_size

    items = list(
        db.attendance_logs.find(query, {"_id": 0})
        .sort([("date", -1), ("emp_code", 1)])
        .skip(skip)
        .limit(page_size)
    )

    # Convert datetime values to epoch milliseconds.
    # MongoDB BSON datetimes are stored in UTC.
    def to_epoch_millis(value):
        if value is None:
            return None

        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            else:
                value = value.astimezone(timezone.utc)

            return int(value.timestamp() * 1000)

        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value)

                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                else:
                    parsed = parsed.astimezone(timezone.utc)

                return int(parsed.timestamp() * 1000)
            except ValueError:
                return value

        # Already an epoch-millisecond number.
        return value

    # Format each attendance record for the API response.
    for item in items:
        # Convert top-level punch timestamps.
        for field in ("punch_in", "punch_out"):
            item[field] = to_epoch_millis(item.get(field))

        item.setdefault("half_day", False)
        item.setdefault("history", [])

        # Convert timestamps inside each history entry.
        for entry in item["history"]:
            entry["at"] = to_epoch_millis(entry.get("at"))

            changes = entry.get("changes", {})

            # Punch timestamps in history must also be epoch milliseconds.
            for field in ("punch_in", "punch_out"):
                if field in changes:
                    for side in ("from", "to"):
                        if side in changes[field]:
                            changes[field][side] = to_epoch_millis(
                                changes[field][side]
                            )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }

@app.get("/analytics/employees/{emp_code}/monthly")
def employee_monthly(
    emp_code: str,
    month: str = Query(
        ...,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Calendar month, YYYY-MM",
    ),
):
    # 1. Check whether the employee exists.
    employee = db.employees.find_one({"emp_code": emp_code})

    if employee is None:
        raise HTTPException(
            status_code=404,
            detail="Employee not found",
        )

    # 2. Get the first and last date of the requested month.
    year, month_number = map(int, month.split("-"))

    first_day = date(year, month_number, 1)
    last_day = date(
        year,
        month_number,
        calendar.monthrange(year, month_number)[1],
    )


    # 3. Calculate working days using MongoDB aggregation.
    working_days_pipeline = [
        {
            "$match": {
                "emp_code": emp_code,
            }
        },
        {
            "$addFields": {
                "_joined_date": {
                    "$dateFromString": {
                        "dateString": "$joined_on",
                        "format": "%Y-%m-%d",
                    }
                },
                "_first_day": {
                    "$dateFromString": {
                        "dateString": first_day.isoformat(),
                        "format": "%Y-%m-%d",
                    }
                },
                "_last_day": {
                    "$dateFromString": {
                        "dateString": last_day.isoformat(),
                        "format": "%Y-%m-%d",
                    }
                },
            }
        },
        {
            "$addFields": {
                "_start_date": {
                    "$cond": [
                        {"$gt": ["$_joined_date", "$_first_day"]},
                        "$_joined_date",
                        "$_first_day",
                    ]
                }
            }
        },
        {
            "$addFields": {
                "working_days": {
                    "$cond": [
                        {"$gt": ["$_start_date", "$_last_day"]},
                        0,
                        {
                            "$size": {
                                "$filter": {
                                    "input": {
                                        "$map": {
                                            "input": {
                                                "$range": [
                                                    0,
                                                    {
                                                        "$add": [
                                                            {
                                                                "$dateDiff": {
                                                                    "startDate": "$_start_date",
                                                                    "endDate": "$_last_day",
                                                                    "unit": "day",
                                                                }
                                                            },
                                                            1,
                                                        ]
                                                    },
                                                ]
                                            },
                                            "as": "offset",
                                            "in": {
                                                "$dateAdd": {
                                                    "startDate": "$_start_date",
                                                    "unit": "day",
                                                    "amount": "$$offset",
                                                }
                                            },
                                        }
                                    },
                                    "as": "day",
                                    "cond": {
                                        "$in": [
                                            {"$dayOfWeek": "$$day"},
                                            [2, 3, 4, 5, 6],
                                        ]
                                    },
                                }
                            }
                        },
                    ]
                }
            }
        },
        {
            "$project": {
                "_id": 0,
                "working_days": 1,
            }
        },
    ]

    working_days_result = list(
        db.employees.aggregate(working_days_pipeline)
    )

    working_days = (
        working_days_result[0]["working_days"]
        if working_days_result
        else 0
    )


    # 4. Use MongoDB aggregation to calculate attendance totals.
    pipeline = [
        {
            "$match": {
                "emp_code": emp_code,
                "date": {
                    "$gte": first_day.isoformat(),
                    "$lte": last_day.isoformat(),
                },
            }
        },
        {
            "$addFields": {
                "_parsed_date": {
                    "$dateFromString": {
                        "dateString": "$date",
                        "format": "%Y-%m-%d",
                    }
                }
            }
        },
        {
            "$addFields": {
                "_is_weekday": {
                    "$in": [
                        {"$dayOfWeek": "$_parsed_date"},
                        [2, 3, 4, 5, 6],
                    ]
                }
            }
        },
        {
            "$group": {
                "_id": None,
                "present_days": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    "$_is_weekday",
                                    {
                                        "$in": [
                                            "$status",
                                            ["PRESENT", "WFH", "ON_DUTY"],
                                        ]
                                    },
                                ]
                            },
                            {
                                "$cond": [
                                    {"$eq": ["$half_day", True]},
                                    0.5,
                                    1,
                                ]
                            },
                            0,
                        ]
                    }
                },
                "leave_days": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$status", "LEAVE"]},
                            1,
                            0,
                        ]
                    }
                },
                "late_count": {
                    "$sum": {
                        "$cond": [
                            {"$gt": ["$late_minutes", 0]},
                            1,
                            0,
                        ]
                    }
                },
                "total_late_minutes": {
                    "$sum": {"$ifNull": ["$late_minutes", 0]}
                },
                "total_overtime_minutes": {
                    "$sum": {"$ifNull": ["$overtime_minutes", 0]}
                },
            }
        },
    ]

    results = list(db.attendance_logs.aggregate(pipeline))

    # 5. If there are no records, attendance totals are zero.
    totals = results[0] if results else {
        "present_days": 0,
        "leave_days": 0,
        "late_count": 0,
        "total_late_minutes": 0,
        "total_overtime_minutes": 0,
    }

    present_days = float(totals["present_days"])

    # 6. Calculate attendance percentage using half-up rounding.
    if working_days == 0:
        attendance_pct = None
    else:
        percentage = (
            Decimal(str(present_days))
            / Decimal(working_days)
            * Decimal("100")
        )

        attendance_pct = float(
            percentage.quantize(
                Decimal("0.0001"),
                rounding=ROUND_HALF_UP,
            )
        )

    # 7. Return the response defined in openapi.yaml.
    return {
        "emp_code": emp_code,
        "month": month,
        "working_days": working_days,
        "present_days": present_days,
        "leave_days": int(totals["leave_days"]),
        "late_count": int(totals["late_count"]),
        "total_late_minutes": int(totals["total_late_minutes"]),
        "total_overtime_minutes": int(
            totals["total_overtime_minutes"]
        ),
        "attendance_pct": attendance_pct,
    }

@app.get("/analytics/departments/summary")
def department_summary(
    month: str = Query(
        ...,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Calendar month, YYYY-MM",
    ),
    department: Optional[str] = None,
):
    # Find the requested month's first and last dates.
    year, month_number = map(int, month.split("-"))
    first_day = date(year, month_number, 1)
    last_day = date(
        year,
        month_number,
        calendar.monthrange(year, month_number)[1],
    )

    first_date = first_day.isoformat()
    last_date = last_day.isoformat()

    # Start with employees who joined on or before the month's end.
    employee_match = {
        "joined_on": {"$lte": last_date}
    }

    # Apply the optional exact department filter.
    if department is not None:
        employee_match["department"] = department

    pipeline = [
        {
            "$match": employee_match
        },
        {
            "$lookup": {
                "from": "attendance_logs",
                "let": {
                    "employee_code": "$emp_code"
                },
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {
                                        "$eq": [
                                            "$emp_code",
                                            "$$employee_code",
                                        ]
                                    },
                                    {
                                        "$gte": [
                                            "$date",
                                            first_date,
                                        ]
                                    },
                                    {
                                        "$lte": [
                                            "$date",
                                            last_date,
                                        ]
                                    },
                                ]
                            }
                        }
                    },
                    {
                        "$addFields": {
                            "_parsed_date": {
                                "$dateFromString": {
                                    "dateString": "$date",
                                    "format": "%Y-%m-%d",
                                }
                            }
                        }
                    },
                    {
                        "$addFields": {
                            "_is_weekday": {
                                "$in": [
                                    {"$dayOfWeek": "$_parsed_date"},
                                    [2, 3, 4, 5, 6],
                                ]
                            }
                        }
                    },
                ],
                "as": "logs",
            }
        },
        {
            "$unwind": {
                "path": "$logs",
                "preserveNullAndEmptyArrays": True,
            }
        },
        {
            "$set": {
                "_present_day": {
                    "$cond": [
                        {
                            "$and": [
                                {
                                    "$eq": [
                                        "$logs._is_weekday",
                                        True,
                                    ]
                                },
                                {
                                    "$in": [
                                        "$logs.status",
                                        ["PRESENT", "WFH", "ON_DUTY"],
                                    ]
                                },
                            ]
                        },
                        {
                            "$cond": [
                                {
                                    "$eq": [
                                        "$logs.half_day",
                                        True,
                                    ]
                                },
                                0.5,
                                1,
                            ]
                        },
                        0,
                    ]
                },
                "_work_hours_sum": {
                    "$cond": [
                        {
                            "$and": [
                                {
                                    "$in": [
                                        "$logs.status",
                                        ["PRESENT", "WFH", "ON_DUTY"],
                                    ]
                                },
                                {
                                    "$ne": [
                                        "$logs.work_hours",
                                        None,
                                    ]
                                },
                            ]
                        },
                        "$logs.work_hours",
                        0,
                    ]
                },
                "_work_hours_count": {
                    "$cond": [
                        {
                            "$and": [
                                {
                                    "$in": [
                                        "$logs.status",
                                        ["PRESENT", "WFH", "ON_DUTY"],
                                    ]
                                },
                                {
                                    "$ne": [
                                        "$logs.work_hours",
                                        None,
                                    ]
                                },
                            ]
                        },
                        1,
                        0,
                    ]
                },
                "_late_count": {
                    "$cond": [
                        {"$gt": ["$logs.late_minutes", 0]},
                        1,
                        0,
                    ]
                },
                "_late_minutes": {
                    "$cond": [
                        {"$gt": ["$logs.late_minutes", 0]},
                        "$logs.late_minutes",
                        0,
                    ]
                },
                "_leave_count": {
                    "$cond": [
                        {"$eq": ["$logs.status", "LEAVE"]},
                        1,
                        0,
                    ]
                },
                "_on_duty_count": {
                    "$cond": [
                        {"$eq": ["$logs.status", "ON_DUTY"]},
                        1,
                        0,
                    ]
                },
            }
        },
        # First group by employee so each employee counts once.
        {
            "$group": {
                "_id": {
                    "department": "$department",
                    "emp_code": "$emp_code",
                },
                "present_days": {"$sum": "$_present_day"},
                "work_hours_sum": {"$sum": "$_work_hours_sum"},
                "work_hours_count": {"$sum": "$_work_hours_count"},
                "late_count": {"$sum": "$_late_count"},
                "total_late_minutes": {"$sum": "$_late_minutes"},
                "leave_count": {"$sum": "$_leave_count"},
                "on_duty_count": {"$sum": "$_on_duty_count"},
            }
        },
        # Then combine all employees in each department.
        {
            "$group": {
                "_id": "$_id.department",
                "headcount": {"$sum": 1},
                "present_days": {"$sum": "$present_days"},
                "work_hours_sum": {"$sum": "$work_hours_sum"},
                "work_hours_count": {"$sum": "$work_hours_count"},
                "late_count": {"$sum": "$late_count"},
                "total_late_minutes": {"$sum": "$total_late_minutes"},
                "leave_count": {"$sum": "$leave_count"},
                "on_duty_count": {"$sum": "$on_duty_count"},
            }
        },
        {
            "$sort": {"_id": 1}
        },
        {
            "$project": {
                "_id": 0,
                "department": "$_id",
                "headcount": 1,
                "present_days": 1,
                "work_hours_sum": 1,
                "work_hours_count": 1,
                "late_count": 1,
                "total_late_minutes": 1,
                "leave_count": 1,
                "on_duty_count": 1,
            }
        },
    ]

    results = list(db.employees.aggregate(pipeline))

    # Format average work hours using half-up rounding.
    items = []

    for result in results:
        hours_count = result["work_hours_count"]

        if hours_count == 0:
            avg_work_hours = None
        else:
            average = (
                Decimal(str(result["work_hours_sum"]))
                / Decimal(hours_count)
            )
            avg_work_hours = float(
                average.quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
            )

        items.append({
            "department": result["department"],
            "headcount": int(result["headcount"]),
            "present_days": float(result["present_days"]),
            "avg_work_hours": avg_work_hours,
            "late_count": int(result["late_count"]),
            "total_late_minutes": int(
                result["total_late_minutes"]
            ),
            "leave_count": int(result["leave_count"]),
            "on_duty_count": int(result["on_duty_count"]),
        })

    return {
        "month": month,
        "items": items,
    }

@app.get("/analytics/leaderboard/late")
def late_leaderboard(
    month: str = Query(
        ...,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Calendar month, YYYY-MM",
    ),
    limit: int = Query(10, ge=1, le=50),
    department: Optional[str] = None,
):
    # Find the first and last dates of the requested month.
    year, month_number = map(int, month.split("-"))

    first_day = date(year, month_number, 1)
    last_day = date(
        year,
        month_number,
        calendar.monthrange(year, month_number)[1],
    )

    first_date = first_day.isoformat()
    last_date = last_day.isoformat()

    # Aggregate late minutes for each employee.
    pipeline = [
        {
            "$match": {
                "date": {
                    "$gte": first_date,
                    "$lte": last_date,
                }
            }
        },
        {
            "$group": {
                "_id": "$emp_code",
                "total_late_minutes": {
                    "$sum": {"$ifNull": ["$late_minutes", 0]}
                },
                "late_count": {
                    "$sum": {
                        "$cond": [
                            {"$gt": ["$late_minutes", 0]},
                            1,
                            0,
                        ]
                    }
                },
            }
        },
        {
            "$match": {
                "total_late_minutes": {"$gt": 0}
            }
        },
        # Join employee details; unknown employees are excluded.
        {
            "$lookup": {
                "from": "employees",
                "localField": "_id",
                "foreignField": "emp_code",
                "as": "employee",
            }
        },
        {"$unwind": "$employee"},
    ]

    # If requested, filter by department before ranking.
    if department is not None:
        pipeline.append({
            "$match": {
                "employee.department": department
            }
        })

    pipeline.extend([
        {
            "$project": {
                "_id": 0,
                "emp_code": "$_id",
                "name": "$employee.name",
                "department": "$employee.department",
                "total_late_minutes": 1,
                "late_count": 1,
            }
        },
        {
            "$sort": {
                "total_late_minutes": -1,
                "emp_code": 1,
            }
        },
    ])

    results = list(db.attendance_logs.aggregate(pipeline))

    # Apply standard competition ranking:
    # tied totals share a rank, and the next rank is skipped.
    ranked_items = []
    previous_total = None
    current_rank = 0

    for position, item in enumerate(results, start=1):
        total = item["total_late_minutes"]

        if total != previous_total:
            current_rank = position
            previous_total = total

        item["rank"] = current_rank
        ranked_items.append(item)

    # Apply limit after ranking so ties at the cutoff are included.
    ranked_items = [
        item for item in ranked_items
        if item["rank"] <= limit
    ]

    return {
        "month": month,
        "items": ranked_items,
    }

@app.get("/analytics/departments/{department}/trend")
def department_trend(
    department: str,
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
):
    # Validate the requested date range.
    if to_date < from_date:
        raise HTTPException(
            status_code=422,
            detail="'to' must be on or after 'from'",
        )

    number_of_days = (to_date - from_date).days + 1

    if number_of_days > 92:
        raise HTTPException(
            status_code=422,
            detail="The requested date range cannot exceed 92 days",
        )

    first_date = from_date.isoformat()
    last_date = to_date.isoformat()

    # Check that this department exists.
    department_exists = db.employees.find_one(
        {"department": department},
        {"_id": 1},
    )

    if department_exists is None:
        raise HTTPException(
            status_code=404,
            detail="Department not found",
        )

    # One row per attendance date, with employee counts and
    # employee join dates calculated by MongoDB.

    pipeline = [
        {
            "$match": {
                "department": department,
                "joined_on": {"$lte": last_date},
            }
        },
        {
            "$lookup": {
                "from": "attendance_logs",
                "let": {"employee_code": "$emp_code"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$emp_code", "$$employee_code"]},
                                    {"$gte": ["$date", first_date]},
                                    {"$lte": ["$date", last_date]},
                                ]
                            }
                        }
                    },
                    {
                        "$addFields": {
                            "_parsed_date": {
                                "$dateFromString": {
                                    "dateString": "$date",
                                    "format": "%Y-%m-%d",
                                }
                            }
                        }
                    },
                    {
                        "$group": {
                            "_id": "$_parsed_date",
                            "present_count": {
                                "$sum": {
                                    "$cond": [
                                        {
                                            "$in": [
                                                "$status",
                                                ["PRESENT", "WFH", "ON_DUTY"],
                                            ]
                                        },
                                        {
                                            "$cond": [
                                                {"$eq": ["$half_day", True]},
                                                0.5,
                                                1,
                                            ]
                                        },
                                        0,
                                    ]
                                }
                            },
                            "late_count": {
                                "$sum": {
                                    "$cond": [
                                        {"$gt": ["$late_minutes", 0]},
                                        1,
                                        0,
                                    ]
                                }
                            },
                        }
                    },
                ],
                "as": "daily_logs",
            }
        },
        {
            "$unwind": {
                "path": "$daily_logs",
                "preserveNullAndEmptyArrays": True,
            }
        },
        {
            "$group": {
                "_id": "$daily_logs._id",
                "present_count": {
                    "$sum": {"$ifNull": ["$daily_logs.present_count", 0]}
                },
                "late_count": {
                    "$sum": {"$ifNull": ["$daily_logs.late_count", 0]}
                },
            }
        },
        {
            "$match": {"_id": {"$ne": None}}
        },
        {
            "$project": {
                "_id": 0,
                "date": "$_id",
                "present_count": 1,
                "late_count": 1,
            }
        },
        {
            "$unionWith": {
                "coll": "employees",
                "pipeline": [
                    {"$match": {"department": department}},
                    {"$limit": 1},
                    {
                        "$project": {
                            "_id": 0,
                            "date": {
                                "$literal": datetime.combine(
                                    from_date, datetime.min.time()
                                )
                            },
                            "present_count": {"$literal": 0},
                            "late_count": {"$literal": 0},
                        }
                    },
                ],
            }
        },
        {
            "$group": {
                "_id": "$date",
                "present_count": {"$sum": "$present_count"},
                "late_count": {"$sum": "$late_count"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "date": "$_id",
                "present_count": 1,
                "late_count": 1,
            }
        },
        {"$sort": {"date": 1}},
        {
            "$densify": {
                "field": "date",
                "range": {
                    "step": 1,
                    "unit": "day",
                    "bounds": [
                        datetime.combine(from_date, datetime.min.time()),
                        datetime.combine(
                            to_date + timedelta(days=1),
                            datetime.min.time(),
                        ),
                    ],
                },
            }
        },
        {
            "$set": {
                "is_working_day": {
                    "$in": [{"$dayOfWeek": "$date"}, [2, 3, 4, 5, 6]]
                },
                "present_count": {"$ifNull": ["$present_count", 0]},
                "late_count": {"$ifNull": ["$late_count", 0]},
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "let": {
                    "trend_date": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$date",
                        }
                    }
                },
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$department", department]},
                                    {"$lte": ["$joined_on", "$$trend_date"]},
                                ]
                            }
                        }
                    },
                    {"$count": "count"},
                ],
                "as": "headcount_data",
            }
        },
        {
            "$set": {
                "headcount": {
                    "$ifNull": [
                        {"$arrayElemAt": ["$headcount_data.count", 0]},
                        0,
                    ]
                }
            }
        },
        {"$unset": "headcount_data"},
        {
            "$set": {
                "attendance_rate": {
                    "$cond": [
                        {
                            "$and": [
                                "$is_working_day",
                                {"$gt": ["$headcount", 0]},
                            ]
                        },
                        {
                            "$round": [
                                {"$divide": ["$present_count", "$headcount"]},
                                4,
                            ]
                        },
                        None,
                    ]
                }
            }
        },
        {
            "$setWindowFields": {
                "sortBy": {"date": 1},
                "output": {
                    "moving_avg_7d": {
                        "$avg": "$attendance_rate",
                        "window": {"documents": [-6, 0]},
                    }
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "date": {
                    "$dateToString": {
                        "format": "%Y-%m-%d",
                        "date": "$date",
                    }
                },
                "is_working_day": 1,
                "headcount": 1,
                "present_count": 1,
                "late_count": 1,
                "attendance_rate": 1,
                "moving_avg_7d": {
                    "$cond": [
                        {"$eq": ["$moving_avg_7d", None]},
                        None,
                        {"$round": ["$moving_avg_7d", 4]},
                    ]
                },
            }
        },
        {"$sort": {"date": 1}},
    ]


    items = list(db.employees.aggregate(pipeline))

    return {
        "department": department,
        "items": items,
    }

@app.get("/admin/explain/{endpoint}")
def admin_explain(
    endpoint: str,
    emp_code: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    month: Optional[str] = None,
    department: Optional[str] = None,
    limit: int = 10,
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    ):
    """
    Explain the MongoDB query or aggregation used by an API endpoint.

    Supported endpoint names:
    attendance_list, employee_monthly, department_summary,
    late_leaderboard, department_trend
    """

    if endpoint == "attendance_list":
        query = {}

        if emp_code:
            query["emp_code"] = emp_code

        if date_from or date_to:
            query["date"] = {}

            if date_from:
                query["date"]["$gte"] = date_from

            if date_to:
                query["date"]["$lte"] = date_to

        if status:
            query["status"] = status

        explanation = db.command(
            "explain",
            {
                "find": "attendance_logs",
                "filter": query,
                "sort": {"date": -1, "emp_code": 1},
                "skip": max(0, (page - 1) * page_size),
                "limit": page_size,
            },
            verbosity="executionStats",
        )

    elif endpoint == "employee_monthly":
        if not emp_code or not month:
            raise HTTPException(
                status_code=422,
                detail="employee_monthly requires emp_code and month",
            )

        try:
            year, month_number = map(int, month.split("-"))
            first_day = date(year, month_number, 1)
            last_day = date(
                year,
                month_number,
                calendar.monthrange(year, month_number)[1],
            )
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=422,
                detail="month must use YYYY-MM format",
            )

        pipeline = [
            {
                "$match": {
                    "emp_code": emp_code,
                    "date": {
                        "$gte": first_day.isoformat(),
                        "$lte": last_day.isoformat(),
                    },
                }
            },
            {
                "$addFields": {
                    "_parsed_date": {
                        "$dateFromString": {
                            "dateString": "$date",
                            "format": "%Y-%m-%d",
                        }
                    }
                }
            },
            {
                "$addFields": {
                    "_is_weekday": {
                        "$in": [
                            {"$dayOfWeek": "$_parsed_date"},
                            [2, 3, 4, 5, 6],
                        ]
                    }
                }
            },
            {
                "$group": {
                    "_id": None,
                    "present_days": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        "$_is_weekday",
                                        {
                                            "$in": [
                                                "$status",
                                                [
                                                    "PRESENT",
                                                    "WFH",
                                                    "ON_DUTY",
                                                ],
                                            ]
                                        },
                                    ]
                                },
                                {
                                    "$cond": [
                                        {"$eq": ["$half_day", True]},
                                        0.5,
                                        1,
                                    ]
                                },
                                0,
                            ]
                        }
                    },
                    "leave_days": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$status", "LEAVE"]},
                                1,
                                0,
                            ]
                        }
                    },
                    "late_count": {
                        "$sum": {
                            "$cond": [
                                {"$gt": ["$late_minutes", 0]},
                                1,
                                0,
                            ]
                        }
                    },
                    "total_late_minutes": {
                        "$sum": {"$ifNull": ["$late_minutes", 0]}
                    },
                    "total_overtime_minutes": {
                        "$sum": {"$ifNull": ["$overtime_minutes", 0]}
                    },
                }
            },
        ]

        explanation = db.command(
            "explain",
            {
                "aggregate": "attendance_logs",
                "pipeline": pipeline,
                "cursor": {},
            },
            verbosity="executionStats",
        )

    elif endpoint == "department_summary":
        if not month:
            raise HTTPException(
                status_code=422,
                detail="department_summary requires month",
            )

        try:
            year, month_number = map(int, month.split("-"))
            first_day = date(year, month_number, 1)
            last_day = date(
                year,
                month_number,
                calendar.monthrange(year, month_number)[1],
            )
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=422,
                detail="month must use YYYY-MM format",
            )

        employee_match = {"joined_on": {"$lte": last_day.isoformat()}}

        if department is not None:
            employee_match["department"] = department

        pipeline = [
            {"$match": employee_match},
            {
                "$lookup": {
                    "from": "attendance_logs",
                    "let": {"employee_code": "$emp_code"},
                    "pipeline": [
                        {
                            "$match": {
                                "$expr": {
                                    "$and": [
                                        {
                                            "$eq": [
                                                "$emp_code",
                                                "$$employee_code",
                                            ]
                                        },
                                        {
                                            "$gte": [
                                                "$date",
                                                first_day.isoformat(),
                                            ]
                                        },
                                        {
                                            "$lte": [
                                                "$date",
                                                last_day.isoformat(),
                                            ]
                                        },
                                    ]
                                }
                            }
                        }
                    ],
                    "as": "logs",
                }
            },
            {"$unwind": {
                "path": "$logs",
                "preserveNullAndEmptyArrays": True,
            }},
            {
                "$group": {
                    "_id": {
                        "department": "$department",
                        "emp_code": "$emp_code",
                    },

                    "present_days": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {
                                            "$in": [
                                                "$logs.status",
                                                [
                                                    "PRESENT",
                                                    "WFH",
                                                    "ON_DUTY",
                                                ],
                                            ]
                                        },
                                        {
                                            "$in": [
                                                {
                                                    "$dayOfWeek": {
                                                        "$dateFromString": {
                                                            "dateString": "$logs.date",
                                                            "format": "%Y-%m-%d",
                                                        }
                                                    }
                                                },
                                                [2, 3, 4, 5, 6],
                                            ]
                                        },
                                    ]
                                },
                                {
                                    "$cond": [
                                        {"$eq": ["$logs.half_day", True]},
                                        0.5,
                                        1,
                                    ]
                                },
                                0,
                            ]
                        }
                    },

                    "late_count": {
                        "$sum": {
                            "$cond": [
                                {"$gt": ["$logs.late_minutes", 0]},
                                1,
                                0,
                            ]
                        }
                    },
                    "total_late_minutes": {
                        "$sum": {"$ifNull": ["$logs.late_minutes", 0]}
                    },
                    "leave_count": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$logs.status", "LEAVE"]},
                                1,
                                0,
                            ]
                        }
                    },
                    "on_duty_count": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$logs.status", "ON_DUTY"]},
                                1,
                                0,
                            ]
                        }
                    },
                    "work_hours_sum": {
                        "$sum": {"$ifNull": ["$logs.work_hours", 0]}
                    },
                    "work_hours_count": {
                        "$sum": {
                            "$cond": [
                                {"$ne": ["$logs.work_hours", None]},
                                1,
                                0,
                            ]
                        }
                    },
                }
            },
            {
                "$group": {
                    "_id": "$_id.department",
                    "headcount": {"$sum": 1},
                    "present_days": {"$sum": "$present_days"},
                    "late_count": {"$sum": "$late_count"},
                    "total_late_minutes": {"$sum": "$total_late_minutes"},
                    "leave_count": {"$sum": "$leave_count"},
                    "on_duty_count": {"$sum": "$on_duty_count"},
                    "work_hours_sum": {"$sum": "$work_hours_sum"},
                    "work_hours_count": {"$sum": "$work_hours_count"},
                }
            },
            {"$sort": {"_id": 1}},
        ]

        explanation = db.command(
            "explain",
            {
                "aggregate": "employees",
                "pipeline": pipeline,
                "cursor": {},
            },
            verbosity="executionStats",
        )

    elif endpoint == "late_leaderboard":
        if not month:
            raise HTTPException(
                status_code=422,
                detail="late_leaderboard requires month",
            )

        try:
            year, month_number = map(int, month.split("-"))
            first_day = date(year, month_number, 1)
            last_day = date(
                year,
                month_number,
                calendar.monthrange(year, month_number)[1],
            )
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=422,
                detail="month must use YYYY-MM format",
            )

        pipeline = [
            {
                "$match": {
                    "date": {
                        "$gte": first_day.isoformat(),
                        "$lte": last_day.isoformat(),
                    }
                }
            },
            {
                "$group": {
                    "_id": "$emp_code",
                    "total_late_minutes": {
                        "$sum": {"$ifNull": ["$late_minutes", 0]}
                    },
                    "late_count": {
                        "$sum": {
                            "$cond": [
                                {"$gt": ["$late_minutes", 0]},
                                1,
                                0,
                            ]
                        }
                    },
                }
            },
            {"$match": {"total_late_minutes": {"$gt": 0}}},
            {
                "$lookup": {
                    "from": "employees",
                    "localField": "_id",
                    "foreignField": "emp_code",
                    "as": "employee",
                }
            },
            {"$unwind": "$employee"},
        ]

        if department is not None:
            pipeline.append(
                {"$match": {"employee.department": department}}
            )

        pipeline.extend([
            {
                "$project": {
                    "_id": 0,
                    "emp_code": "$_id",
                    "name": "$employee.name",
                    "department": "$employee.department",
                    "total_late_minutes": 1,
                    "late_count": 1,
                }
            },
            {
                "$sort": {
                    "total_late_minutes": -1,
                    "emp_code": 1,
                }
            },
            {"$limit": limit},
        ])

        explanation = db.command(
            "explain",
            {
                "aggregate": "attendance_logs",
                "pipeline": pipeline,
                "cursor": {},
            },
            verbosity="executionStats",
        )

    elif endpoint == "department_trend":
        if (
            department is None
            or from_date is None
            or to_date is None
        ):
            raise HTTPException(
                status_code=422,
                detail="department_trend requires department, from, and to",
            )

        if to_date < from_date:
            raise HTTPException(
                status_code=422,
                detail="'to' must be on or after 'from'",
            )

        if (to_date - from_date).days + 1 > 92:
            raise HTTPException(
                status_code=422,
                detail="The requested date range cannot exceed 92 days",
            )

        first_date = from_date.isoformat()
        last_date = to_date.isoformat()

        pipeline = [
            {
                "$match": {
                    "department": department,
                    "joined_on": {"$lte": last_date},
                }
            },
            {
                "$lookup": {
                    "from": "attendance_logs",
                    "let": {"employee_code": "$emp_code"},
                    "pipeline": [
                        {
                            "$match": {
                                "$expr": {
                                    "$and": [
                                        {
                                            "$eq": [
                                                "$emp_code",
                                                "$$employee_code",
                                            ]
                                        },
                                        {"$gte": ["$date", first_date]},
                                        {"$lte": ["$date", last_date]},
                                    ]
                                }
                            }
                        }
                    ],
                    "as": "daily_logs",
                }
            },
        ]

        explanation = db.command(
            "explain",
            {
                "aggregate": "employees",
                "pipeline": pipeline,
                "cursor": {},
            },
            verbosity="executionStats",
        )

    else:
        raise HTTPException(
            status_code=404,
            detail=(
                "Unknown endpoint. Use 'attendance_list', "
                "'employee_monthly', 'department_summary', "
                "'late_leaderboard', or 'department_trend'."
            ),
        )



    return Response(
    content=dumps({
        "endpoint": endpoint,
        "collection": {
            "attendance_list": "attendance_logs",
            "employee_monthly": "attendance_logs",
            "department_summary": "employees",
            "late_leaderboard": "attendance_logs",
            "department_trend": "employees",
        }[endpoint],
        "explain": explanation,
    }),
    media_type="application/json",
)







# --------------------------------------------------------------------------- #
# TODO - the rest of the contract (see openapi.yaml):
#   POST  /attendance/punch-out
#   PATCH /attendance/{emp_code}/{date}
#   GET   /analytics/employees/{emp_code}/monthly
#   GET   /analytics/departments/summary
#   GET   /analytics/leaderboard/late
#   GET   /analytics/departments/{department}/trend
#   GET   /admin/explain/{endpoint}
# --------------------------------------------------------------------------- #
