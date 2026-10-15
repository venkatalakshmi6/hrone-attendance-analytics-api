# REVIEW.md

## Starter Code Review — `app/main.py`

The following table documents the defects identified during implementation and testing. Function names are used instead of line numbers because line numbers may change as the code is edited.

| # | Where (function / line) | What is wrong | How you'd notice it (test, input, or symptom) | How you fixed it |
|---|---|---|---|---|
| 1 | `punch_out` endpoint | The punch-out workflow was incomplete and did not fully process an employee's attendance record. | Call `POST /attendance/punch-out` for an employee who has punched in and inspect the response and saved record. | Implemented the punch-out workflow and calculated work hours, overtime, and half-day status. Tested successful punch-out and duplicate requests. |
| 2 | `regularize_attendance` endpoint | Attendance regularization needed proper handling of requested changes, validation, and history preservation. | Call `PATCH /attendance/{emp_code}/{date}` with a valid change, an invalid status, unchanged fields, and a nonexistent record. | Implemented field updates and preserved history. Verified successful updates, HTTP 422 for invalid or unchanged requests, and HTTP 404 for a missing record. |
| 3 | `compute_late_minutes` helper | Late-minute calculation required boundary validation to avoid incorrect results around the shift start and grace period. | Test times such as `09:40:00`, `09:40:01`, and `09:41:00` against the configured shift rules. | Corrected and tested the calculation at the grace-period boundary. The tested results were 0, 10, and 11 minutes respectively. |
| 4 | Department summary aggregation / `present_days` calculation | The weekday condition needed to use the correct MongoDB `$dayOfWeek` values for Monday through Friday. | Test attendance on weekdays and weekends and compare the department summary with the expected counts. | Corrected the weekday condition to use MongoDB values `[2, 3, 4, 5, 6]` for Monday through Friday. |
| 5 | Department summary aggregation / half-day calculation | Half-day attendance needed to be counted consistently rather than treating every attendance record as a full present day. | Test records with different work-hour values and compare the aggregated `present_days` with the expected totals. | Corrected the nested conditional calculation so half-day attendance contributes appropriately to the aggregation. |

## Items reviewed and not considered defects

1. **Duplicate employee and attendance requests:** Duplicate employee creation and duplicate punch-in/punch-out requests returned HTTP 409 in testing. These were expected conflict responses, not defects.
2. **Invalid attendance regularization:** An invalid status and a request that made no changes returned HTTP 422. These were expected validation responses.
3. **Missing attendance record:** A regularization request for a nonexistent record returned HTTP 404, which was expected behavior.
4. **Query performance:** Explain-plan checks for attendance listing, employee monthly analytics, and department summary used indexes for the tested queries rather than collection scans. No collection-scan issue was observed in those tested plans.
5. **Weekend trend rows:** The department trend returned weekend rows with no attendance rate where appropriate. This was not treated as a defect because weekends are non-working days.

## Validation performed

I manually tested the API using FastAPI Swagger UI. Tests included successful requests, duplicate requests, invalid inputs, missing records, monthly employee analytics, department summaries, late-arrival leaderboard results, department trends, and query execution plans.

The results documented above describe the cases tested during development. Additional automated tests and broader edge-case testing would further strengthen confidence in the implementation.
