# REVIEW.md

## Starter Code Review — `app/main.py`

The following confirmed defect was identified and fixed during implementation and testing.

| # | Where (function) | What was wrong | How to reproduce | How it was fixed |
|---|---|---|---|---|
| 1 | `punch_in` endpoint | For an overnight shift, an early-morning punch-in could be assigned to the current calendar date instead of the date on which the shift started. | Configure a shift from 22:00 to 06:00 and test a punch-in at 02:00 on 2026-10-15. The expected attendance date is 2026-10-14. | Adjusted the attendance date back by one day when the shift crosses midnight and the punch-in occurs before the shift end. The date calculation was verified with a focused test. |

## Items Reviewed and Not Considered Defects

1. **Duplicate requests:** Duplicate employee creation and duplicate attendance requests returned HTTP 409 in the cases tested. These responses were expected conflict handling.
2. **Regularization validation:** Invalid status and unchanged-field requests returned HTTP 422 in the cases tested. These responses were expected validation behavior.
3. **Missing attendance record:** Regularization of a nonexistent attendance record returned HTTP 404 in the case tested. This was expected behavior.
4. **Attendance-list query performance:** The tested execution plan used an index scan rather than a collection scan.
5. **Analytics and edge cases:** Additional cases require comparison with the assignment specification and targeted verification before they can be classified as defects or confirmed correct.

## Validation Performed

The FastAPI application was started successfully, and the Swagger UI was accessible. Manual API tests returned successful responses for the health check, attendance listing, employee monthly analytics, department summary, late leaderboard, and department trend. Validation and conflict responses were also checked.

MongoDB execution plans were inspected for the attendance-list, employee-monthly, department-summary, late-leaderboard, and department-trend explain operations. The tested plans returned successfully, and the inspected queries used indexes rather than collection scans in the cases checked.

The application passed Python syntax compilation using:

`python -m py_compile app\main.py`

This review records the confirmed defect and the validation performed. It does not claim that every possible defect or edge case has been identified or tested.
