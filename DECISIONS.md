# DECISIONS.md

## 1. Indexes
I created a unique index on `employees.emp_code` to prevent duplicate employee codes, and an index on `employees.joined_on` to support department analytics. A unique compound index on `attendance_logs.emp_code` and `date` prevents duplicate attendance records for the same employee and date. The compound index on `date` descending and `emp_code` supports attendance listing by date. I would consider a department index if department-filtered queries became a bottleneck, after checking execution statistics.

## 2. Punch-in race
Two identical requests may both check the employee, but the unique attendance index allows only one insert for that employee and date. The other insert raises `DuplicateKeyError`, which the API converts to HTTP 409 Conflict.

## 3. Leaderboard ties
Employees with equal total late minutes share the same standard competition rank. The limit is applied after ranking, so employees tied at the cutoff are included. Employee code provides deterministic ordering.

## 4. Department headcount
The summary starts from employees and uses `$lookup` with `preserveNullAndEmptyArrays` during `$unwind`. Therefore, employees without attendance logs remain in the aggregation and count toward headcount.

## 5. Scaling
For 100 times more data, I would benchmark realistic workloads, inspect query plans, and add or adjust indexes based on evidence. I would also test concurrent requests and monitor aggregation latency and database resource usage.