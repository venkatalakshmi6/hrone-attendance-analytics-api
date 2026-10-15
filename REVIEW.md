# REVIEW.md

## Starter Code Review — `app/main.py`

The following confirmed issues were addressed and tested during implementation.

| # | Location | Issue | Reproduction / observed behavior | Fix and verification |
|---|---|---|---|---|
| 1 | `punch_in` endpoint | Overnight shifts require the attendance date to reflect the day the shift started. | For a 22:00–06:00 shift, a punch-in at 02:00 belongs to the previous attendance date. | Corrected the overnight date calculation and verified the date handling. |
| 2 | `regularize_attendance` endpoint | The unchanged-field validation response exposed unnecessary debugging information. | Send a PATCH request with the same status already stored. | Removed debug output and simplified the HTTP 422 response. Verified that unchanged requests return 422 and valid status changes return 200. |

## Additional Items Reviewed

1. **Duplicate requests:** Duplicate employee creation and duplicate attendance requests returned HTTP 409 in the cases tested.
2. **Regularization validation:** Invalid status and unchanged-field requests returned HTTP 422 in the cases tested.
3. **Missing attendance record:** Regularizing a nonexistent attendance record returned HTTP 404 in the case tested.
4. **Attendance-list query:** The tested execution plan used an index scan rather than a collection scan.
5. **Analytics endpoints:** Attendance listing, employee monthly analytics, department summary, late leaderboard, and department trend returned successful responses in the manual tests performed.
6. **MongoDB explain endpoints:** All five supported explain endpoints returned successful responses with the required parameters. The inspected plans used indexes in the cases checked. The department-trend explain pipeline still requires verification against the complete trend aggregation.

## Validation Performed

- Started the FastAPI application and accessed Swagger UI.
- Tested the health check, attendance listing, employee monthly analytics, department summary, late leaderboard, and department trend.
- Tested regularization for an unchanged status and for successful status changes.
- Checked MongoDB explain output for the supported analytics and attendance queries.
- Ran `python -m py_compile app\main.py` successfully.

## Limitations

This review records the issues addressed and the tests actually performed. It does not claim that every possible defect has been identified or that all edge cases and concurrency scenarios have been tested. Further review is needed to establish full coverage of the assessment requirements.