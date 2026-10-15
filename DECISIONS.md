# DECISIONS.md

## 1. Indexes

Indexes improve query speed. I use a unique index on employee code, a compound index on attendance employee code and date, a date and employee-code index for analytics, and an index on employee joining date. These indexes support lookups, filtering, sorting, and reporting. They should be created automatically at application startup.

## 2. Simultaneous punch-ins

A unique compound index on employee code and attendance date prevents duplicate attendance records. When two identical punch-in requests arrive simultaneously, one should succeed with HTTP 201 and the other should return HTTP 409 Conflict.

## 3. Leaderboard ties

Employees with equal total late minutes share the same rank. For example, ranks can be 1, 2, 2, 4. Tied employees are ordered by employee code, and the requested limit is applied after ranking.

## 4. Employees without attendance logs

Department headcount includes employees who joined on or before the reporting period's end date, even if they have no attendance records. Employees who joined after that date are excluded.

## 5. Scaling to 100× data

I would measure query performance, review execution plans, optimize indexes and aggregation pipelines, and benchmark with larger datasets. If needed, I would add caching or precomputed analytics while keeping the original attendance records as the source of truth.