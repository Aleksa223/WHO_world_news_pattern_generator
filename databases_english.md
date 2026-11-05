# PLAN 5: DATABASES — Complete Backend Interview Preparation

---

# PART 1: SQL FUNDAMENTALS

---

## TOPIC 1: SELECT, WHERE, ORDER BY, LIMIT, OFFSET + Operators

### What Is SQL?

SQL (Structured Query Language) is a declarative language for working with relational databases. You tell the database **WHAT** you want, and it decides **HOW** to find it. You do not write an algorithm; you write a request.

A relational database stores data in **tables** (relations). Each table contains **columns** (attributes) and **rows** (records/tuples).

### SELECT — The Foundation of Everything

```sql
SELECT kolona1, kolona2
FROM tabela;
```

`SELECT *` returns all columns — **never use it in production code**. Reasons:
- It returns data you do not use (unnecessary I/O and network traffic).
- If someone adds a new column, your code may break.
- You cannot take advantage of a covering index (more on that later).

```sql
-- Example tables used throughout this course:
-- employees(id, name, department, salary, hire_date, manager_id)
-- departments(id, name, budget, location)
-- orders(id, customer_id, product_id, quantity, price, order_date)
-- customers(id, name, email, city, country, created_at)
-- products(id, name, category, price, stock)

SELECT name, salary
FROM employees;
```

### Aliases (AS)

```sql
SELECT name AS ime_zaposlenog, salary AS plata
FROM employees AS e;
```

`AS` is optional — you can also write `SELECT name ime_zaposlenog` — but **always use AS** for readability.

### WHERE — Filtering Rows

WHERE is logically evaluated **before** SELECT. The database first filters rows, then selects the columns.

```sql
SELECT name, salary
FROM employees
WHERE department = 'Engineering';
```

#### Comparison operators:

| Operator | Meaning |
|----------|----------|
| `=` | equal to |
| `!=` or `<>` | not equal to |
| `<`, `>` | less than, greater than |
| `<=`, `>=` | less than or equal to, greater than or equal to |

#### Logical operators:

```sql
-- AND: both conditions must be true
SELECT name FROM employees
WHERE department = 'Engineering' AND salary > 80000;

-- OR: at least one condition must be true
SELECT name FROM employees
WHERE department = 'Engineering' OR department = 'Marketing';

-- NOT: negation
SELECT name FROM employees
WHERE NOT department = 'Engineering';
```

**Precedence:** `NOT` > `AND` > `OR`. Always use parentheses to make the logic clear:

```sql
-- WITHOUT parentheses: what does this return?
SELECT name FROM employees
WHERE department = 'Engineering' OR department = 'Marketing' AND salary > 80000;

-- AND takes precedence, so this actually means:
-- department = 'Engineering' OR (department = 'Marketing' AND salary > 80000)

-- WITH parentheses: explicit grouping:
SELECT name FROM employees
WHERE (department = 'Engineering' OR department = 'Marketing') AND salary > 80000;
```

#### Special operators:

```sql
-- IN: instead of multiple OR conditions
SELECT name FROM employees
WHERE department IN ('Engineering', 'Marketing', 'Sales');

-- BETWEEN: inclusive range (includes both boundaries!)
SELECT name FROM employees
WHERE salary BETWEEN 50000 AND 80000;
-- Equivalent: salary >= 50000 AND salary <= 80000

-- LIKE - pattern matching
SELECT name FROM employees
WHERE name LIKE 'J%';      -- starts with J
-- % = any number of characters (including zero)
-- _ = exactly one character

SELECT name FROM employees
WHERE name LIKE '_o%';     -- second character is 'o'

-- ILIKE (PostgreSQL) - case-insensitive LIKE
SELECT name FROM employees
WHERE name ILIKE '%john%';  -- John, JOHN, john...

-- IS NULL / IS NOT NULL
SELECT name FROM employees
WHERE manager_id IS NULL;   -- employees without a manager (e.g., CEO)

-- IMPORTANT: NULL = NULL evaluates to UNKNOWN, not TRUE!
-- That is why we use IS NULL, not = NULL
```

#### NULL — A Special Value

NULL means **unknown** (not zero or an empty string). Any comparison with NULL returns **UNKNOWN** (neither TRUE nor FALSE):

```sql
-- This NEVER returns rows, even if NULL values exist:
SELECT * FROM employees WHERE manager_id = NULL;    -- WRONG!

-- Correct:
SELECT * FROM employees WHERE manager_id IS NULL;    -- CORRECT

-- NULL in arithmetic:
-- 5 + NULL = NULL
-- NULL > 10  = UNKNOWN
-- NULL = NULL = UNKNOWN
-- NULL != NULL = UNKNOWN
```

### ORDER BY — Sorting

```sql
-- ASC (ascending) is the default
SELECT name, salary FROM employees
ORDER BY salary DESC;

-- Sorting by multiple columns
SELECT name, department, salary FROM employees
ORDER BY department ASC, salary DESC;
-- Sort first by department (A–Z), then within each department by salary (highest first)

-- You can sort by a column position (not recommended; fragile):
SELECT name, salary FROM employees
ORDER BY 2 DESC;  -- sorts by the second selected column (salary)

-- NULLS FIRST / NULLS LAST (PostgreSQL)
SELECT name, manager_id FROM employees
ORDER BY manager_id NULLS LAST;
```

### LIMIT and OFFSET — Pagination

```sql
-- First 10 results
SELECT name, salary FROM employees
ORDER BY salary DESC
LIMIT 10;

-- Next 10 results (page 2)
SELECT name, salary FROM employees
ORDER BY salary DESC
LIMIT 10 OFFSET 10;

-- Page N (zero-indexed):
-- LIMIT page_size OFFSET page_size * page_number
```

**IMPORTANT for interviews:** OFFSET pagination is **slow for large offsets**! The database must walk through all rows up to the offset and discard them. With a million rows, `OFFSET 999990` means the database reads nearly a million rows just to return 10.

A better alternative is **keyset/cursor pagination**:

```sql
-- Instead of OFFSET, use WHERE with the last value from the previous page:
SELECT name, salary FROM employees
WHERE salary < 75000    -- last salary from the previous page
ORDER BY salary DESC
LIMIT 10;
```

### DISTINCT — Removing Duplicates

```sql
SELECT DISTINCT department FROM employees;

-- DISTINCT over several columns: the combination must be unique
SELECT DISTINCT department, city FROM employees;
```

### Logical SQL Query Execution Order

This is **critical for understanding SQL**. SQL is NOT logically evaluated in the order in which it is written!

```
As written:          Logical execution order:
1. SELECT            1. FROM         (source tables)
2. FROM              2. WHERE        (filter rows)
3. WHERE             3. GROUP BY     (group rows)
4. GROUP BY          4. HAVING       (filter groups)
5. HAVING            5. SELECT       (select expressions)
6. ORDER BY          6. DISTINCT     (remove duplicates)
7. LIMIT/OFFSET      7. ORDER BY     (sort)
                     8. LIMIT/OFFSET (restrict results)
```

That is why you cannot use a SELECT alias in WHERE:

```sql
-- ERROR: alias 'bonus' does not yet exist when WHERE is evaluated:
SELECT name, salary * 0.1 AS bonus
FROM employees
WHERE bonus > 5000;

-- CORRECT:
SELECT name, salary * 0.1 AS bonus
FROM employees
WHERE salary * 0.1 > 5000;
```

But you CAN use an alias in ORDER BY (because ORDER BY is evaluated after SELECT):

```sql
SELECT name, salary * 0.1 AS bonus
FROM employees
ORDER BY bonus DESC;  -- OK!
```

### Interview Questions — Topic 1

**Q1: Why should you avoid SELECT * in production code?**
A: Three reasons: (1) it returns unnecessary data, increasing I/O and network traffic; (2) a schema change (such as a new column) may break your code; and (3) the database may not be able to use a covering index and must access the table.

**Q2: What is the difference between NULL = NULL and NULL IS NULL?**
A: `NULL = NULL` returns UNKNOWN (not TRUE), because NULL means "unknown" and we cannot determine whether two unknown values are equal. `NULL IS NULL` returns TRUE. So always use IS NULL / IS NOT NULL to test for nulls.

**Q3: Explain the logical SQL query execution order.**
A: FROM → WHERE → GROUP BY → HAVING → SELECT → DISTINCT → ORDER BY → LIMIT/OFFSET. Therefore, a SELECT alias cannot be used in WHERE (which runs logically before SELECT), but can be used in ORDER BY.

**Q4: Why is OFFSET pagination slow on large datasets? What is the alternative?**
A: OFFSET N means the database must read and discard N rows before returning results. With OFFSET 1000000, it processes a million rows unnecessarily. Keyset/cursor pagination is an alternative: remember the last value and use WHERE instead of OFFSET, for example `WHERE id > last_id LIMIT 10`.

**Q5: What does `SELECT * FROM employees WHERE department != 'Engineering'` return if some rows have department = NULL?**
A: It does not return rows whose department is NULL! `NULL != 'Engineering'` is UNKNOWN, and WHERE keeps only rows for which the condition is TRUE. To include nulls: `WHERE department != 'Engineering' OR department IS NULL`.

---

## TOPIC 2: JOINs (INNER, LEFT, RIGHT, FULL, CROSS, SELF JOIN)

### What Is a JOIN?

A JOIN combines rows from two or more tables according to a condition (most often matching keys). It is central to the relational model: data is split into normalized tables and joined when needed.

### INNER JOIN

Returns only rows with **a match in both tables**.

```sql
SELECT e.name, d.name AS department_name
FROM employees e
INNER JOIN departments d ON e.department_id = d.id;
```

If an employee has no department_id (NULL), or the department_id does not exist in the departments table, that employee **will not appear in the result**.

```
employees:               departments:
id | name  | dept_id     id | name
1  | Ana   | 1           1  | Engineering
2  | Marko | 2           2  | Marketing
3  | Jovan | NULL        3  | Sales
4  | Petra | 99

INNER JOIN rezultat:
Ana   | Engineering
Marko | Marketing
-- Jovan has no dept_id (NULL): NOT INCLUDED
-- Petra has dept_id=99, which does not exist: NOT INCLUDED
-- Sales has no employees: NOT INCLUDED
```

### LEFT JOIN (LEFT OUTER JOIN)

Returns **all rows from the left table** plus matching rows from the right. Where there is no match, columns from the right side are NULL.

```sql
SELECT e.name, d.name AS department_name
FROM employees e
LEFT JOIN departments d ON e.department_id = d.id;
```

```
Rezultat:
Ana   | Engineering
Marko | Marketing
Jovan | NULL          -- no department, but this employee is retained
Petra | NULL          -- dept_id=99 does not exist, but this employee is retained
```

LEFT JOIN is **the most common JOIN in practice** — you want all records from the main table plus extra information where it exists.

### RIGHT JOIN (RIGHT OUTER JOIN)

Returns **all rows from the right table** plus matching rows from the left. Rarely used — you can reverse table order and use LEFT JOIN instead.

```sql
SELECT e.name, d.name AS department_name
FROM employees e
RIGHT JOIN departments d ON e.department_id = d.id;
```

```
Rezultat:
Ana   | Engineering
Marko | Marketing
NULL  | Sales          -- nobody works in Sales, but the department is retained
```

### FULL OUTER JOIN

Returns **all rows from both tables**. Where there is no match, the corresponding side contains NULLs.

```sql
SELECT e.name, d.name AS department_name
FROM employees e
FULL OUTER JOIN departments d ON e.department_id = d.id;
```

```
Rezultat:
Ana   | Engineering
Marko | Marketing
Jovan | NULL           -- employee without a department
Petra | NULL           -- employee referencing a nonexistent department
NULL  | Sales          -- department without employees
```

### CROSS JOIN

A Cartesian product: every row in the first table is paired with every row in the second. **There is no ON condition.**

```sql
SELECT e.name, d.name
FROM employees e
CROSS JOIN departments d;
```

If employees has 4 rows and departments has 3, the result contains **4 × 3 = 12 rows**.

Rarely used, but useful for:
- Generating every combination (e.g., all products × all months).
- Generating calendars.

```sql
-- Example: generate a row for each month of 2024 and each department
SELECT d.name, m.month
FROM departments d
CROSS JOIN generate_series(1, 12) AS m(month);
```

### SELF JOIN

A table is joined to itself. Used when a table has a hierarchical structure (e.g., employee–manager).

```sql
-- Find each employee and their manager's name
SELECT
    e.name AS employee,
    m.name AS manager
FROM employees e
LEFT JOIN employees m ON e.manager_id = m.id;
```

```
employees:
id | name  | manager_id
1  | CEO   | NULL
2  | VP    | 1
3  | Dev   | 2
4  | QA    | 2

Rezultat:
CEO  | NULL    -- the CEO has no manager
VP   | CEO
Dev  | VP
QA   | VP
```

### JOIN vs WHERE (Old-Style Syntax)

```sql
-- Old ANSI-89 style (DO NOT USE):
SELECT e.name, d.name
FROM employees e, departments d
WHERE e.department_id = d.id;

-- Modern ANSI-92 style (USE):
SELECT e.name, d.name
FROM employees e
INNER JOIN departments d ON e.department_id = d.id;
```

The old style is problematic because:
- It mixes JOIN logic with WHERE filtering.
- It is easy to forget a WHERE condition and accidentally produce a CROSS JOIN.
- It is harder to read with several tables.

### Multiple JOINs

```sql
SELECT
    o.id AS order_id,
    c.name AS customer,
    p.name AS product,
    o.quantity,
    o.price
FROM orders o
INNER JOIN customers c ON o.customer_id = c.id
INNER JOIN products p ON o.product_id = p.id
WHERE o.order_date >= '2024-01-01';
```

The order of JOINs in a SQL statement generally **does not determine the optimizer's execution order** (the query optimizer chooses a suitable plan). For readability, put the "main" table in FROM.

### ON vs USING

```sql
-- When a column has the same name in both tables, you can use USING:
SELECT e.name, d.name
FROM employees e
INNER JOIN departments d USING (department_id);

-- USING is shorter but requires the same column name on both sides
-- ON is more flexible: different column names and complex conditions
```

### Common JOIN Mistakes

**1. Missing ON condition:**
```sql
-- This is a CROSS JOIN, not an INNER JOIN!
SELECT * FROM employees e JOIN departments d;
-- Some databases raise an error; others may treat it as a cross join
```

**2. Duplicate rows:**
```sql
-- A 1:N relationship yields several rows for the same left-side record
-- For example, one customer with five orders repeats the customer data five times
SELECT c.name, o.id
FROM customers c
JOIN orders o ON c.id = o.customer_id;
-- If John has five orders, "John" appears five times
```

**3. NULL in a JOIN condition:**
```sql
-- If e.department_id is NULL, the ON condition is UNKNOWN
-- The row will NOT appear in the INNER JOIN result
-- Use LEFT JOIN to preserve such rows
```

### Interview Questions — Topic 2

**Q1: What is the difference between INNER JOIN and LEFT JOIN?**
A: INNER JOIN returns only rows that match in both tables. LEFT JOIN returns every row from the left table; if the right table has no match, its columns are NULL. LEFT JOIN is useful when you need all records from the main table, regardless of whether related data exists.

**Q2: How would you find all departments with no employees?**
A: LEFT JOIN departments to employees, then use WHERE to check for NULL:
```sql
SELECT d.name
FROM departments d
LEFT JOIN employees e ON d.id = e.department_id
WHERE e.id IS NULL;
```

**Q3: What is a SELF JOIN, and when do you use it?**
A: A self-join joins a table to itself. It is used for hierarchical data (e.g., an employees table where each employee has a manager_id pointing to another employee in the same table), or to compare rows within one table.

**Q4: Why can CROSS JOIN be dangerous?**
A: It generates a Cartesian product: every row from table A is paired with every row from table B. If both have 10,000 rows, the result has 100 million rows, potentially overwhelming the database. Always verify that you really need CROSS JOIN.

**Q5: If a JOIN query returns duplicate rows, what might be the cause?**
A: The most common reason is a one-to-many or many-to-many relationship. For example, if a customer has multiple orders, a JOIN produces one row per order and repeats the customer fields. The solution depends on your goal: GROUP BY for aggregation, DISTINCT if you only need unique values from the left table, or a subquery/CTE.

---

## TOPIC 3: GROUP BY, HAVING, Aggregate Functions

### Aggregate Functions

Functions that operate on **a set of rows** and return a single value:

| Function | Description | NULL handling |
|----------|------|---------------|
| `COUNT(*)` | counts all rows | counts rows containing NULLs too |
| `COUNT(kolona)` | counts non-NULL values | **skips NULL** |
| `SUM(kolona)` | sum | skips NULL |
| `AVG(kolona)` | average | skips NULL (!) |
| `MIN(kolona)` | minimum | skips NULL |
| `MAX(kolona)` | maximum | skips NULL |

```sql
SELECT
    COUNT(*) AS total_employees,
    COUNT(manager_id) AS employees_with_manager,
    AVG(salary) AS avg_salary,
    MIN(salary) AS min_salary,
    MAX(salary) AS max_salary,
    SUM(salary) AS total_payroll
FROM employees;
```

**AVG and NULL gotcha:**

```sql
-- Salary values: [100, 200, NULL, 300]
-- AVG(salary) = (100 + 200 + 300) / 3 = 200 (does NOT divide by 4!)
-- If you want NULL treated as zero:
AVG(COALESCE(salary, 0))  -- = (100 + 200 + 0 + 300) / 4 = 150
```

### GROUP BY

Groups rows with the same value in a column. Each group becomes one row in the result.

```sql
SELECT department, COUNT(*) AS num_employees, AVG(salary) AS avg_salary
FROM employees
GROUP BY department;
```

```
Rezultat:
department  | num_employees | avg_salary
Engineering | 15            | 95000
Marketing   | 8             | 72000
Sales       | 12            | 68000
```

**RULE:** Every selected column that is NOT aggregated must appear in GROUP BY (except where functional dependencies permit otherwise):

```sql
-- ERROR:
SELECT department, name, COUNT(*)
FROM employees
GROUP BY department;
-- 'name' is neither aggregated nor grouped; the database cannot determine which value to display

-- CORRECT:
SELECT department, COUNT(*)
FROM employees
GROUP BY department;
```

### Grouping by Multiple Columns

```sql
SELECT department, city, COUNT(*) AS cnt
FROM employees
GROUP BY department, city
ORDER BY department, cnt DESC;
```

```
department  | city      | cnt
Engineering | Belgrade  | 8
Engineering | Novi Sad  | 5
Engineering | Nis       | 2
Marketing   | Belgrade  | 6
Marketing   | Novi Sad  | 2
```

### HAVING — Filtering Groups

WHERE filters **rows** (before grouping). HAVING filters **groups** (after grouping).

```sql
-- Departments with more than 10 employees
SELECT department, COUNT(*) AS cnt
FROM employees
GROUP BY department
HAVING COUNT(*) > 10;

-- Departments with an average salary > 80000, excluding the CEO
SELECT department, AVG(salary) AS avg_sal
FROM employees
WHERE role != 'CEO'          -- filters rows BEFORE grouping
GROUP BY department
HAVING AVG(salary) > 80000   -- filters groups AFTER grouping
ORDER BY avg_sal DESC;
```

**IMPORTANT:** HAVING can reference aggregates or grouped columns. In standard SQL, SELECT aliases are not generally available to HAVING (MySQL allows them; PostgreSQL does not).

```sql
-- PostgreSQL: DOES NOT WORK:
SELECT department, COUNT(*) AS cnt
FROM employees
GROUP BY department
HAVING cnt > 10;             -- ERROR: 'cnt' is not available in HAVING

-- CORRECT:
HAVING COUNT(*) > 10;
```

### COUNT(*) vs COUNT(column) vs COUNT(DISTINCT column)

```sql
SELECT
    COUNT(*) AS svi_redovi,                    -- counts ALL rows
    COUNT(department) AS redovi_sa_dept,        -- counts rows where department is not NULL
    COUNT(DISTINCT department) AS razlicitih    -- counts unique non-NULL values
FROM employees;
```

### Practical Examples

```sql
-- Top three departments by total salary
SELECT department, SUM(salary) AS total_payroll
FROM employees
GROUP BY department
ORDER BY total_payroll DESC
LIMIT 3;

-- Monthly revenue by product category
SELECT
    p.category,
    DATE_TRUNC('month', o.order_date) AS month,
    SUM(o.quantity * o.price) AS revenue,
    COUNT(DISTINCT o.customer_id) AS unique_customers
FROM orders o
JOIN products p ON o.product_id = p.id
WHERE o.order_date >= '2024-01-01'
GROUP BY p.category, DATE_TRUNC('month', o.order_date)
ORDER BY month, revenue DESC;

-- Customers who placed more than five orders and spent over 1000 in total
SELECT
    c.name,
    COUNT(o.id) AS order_count,
    SUM(o.quantity * o.price) AS total_spent
FROM customers c
JOIN orders o ON c.id = o.customer_id
GROUP BY c.id, c.name
HAVING COUNT(o.id) > 5 AND SUM(o.quantity * o.price) > 1000
ORDER BY total_spent DESC;
```

### Interview Questions — Topic 3

**Q1: What is the difference between WHERE and HAVING?**
A: WHERE filters individual rows before grouping and cannot use aggregate functions. HAVING filters groups after grouping and can use aggregates. The logical order is FROM → WHERE → GROUP BY → HAVING.

**Q2: Why can AVG(salary) give unexpected results when NULL values exist?**
A: AVG excludes NULL rows from both the numerator and denominator. For [100, 200, NULL, 300], AVG = 600/3 = 200, not 600/4 = 150. If you want NULL treated as zero, use `AVG(COALESCE(salary, 0))`.

**Q3: What is the difference between COUNT(*), COUNT(column), and COUNT(DISTINCT column)?**
A: `COUNT(*)` counts all rows, including rows containing NULLs. `COUNT(column)` counts rows where the specified column is not NULL. `COUNT(DISTINCT column)` counts unique non-NULL values.

**Q4: Why must every SELECT column be grouped or aggregated?**
A: Grouping collapses several rows into one. If a column is not grouped or aggregated, the database generally cannot know which value to display for that group. An aggregate combines values into one (SUM, MAX, etc.). Some dialects permit ungrouped columns in specific circumstances, but relying on an arbitrary value is bad practice.

---

## TOPIC 4: Subqueries (Scalar, Correlated, EXISTS, IN)

### What Are Subqueries?

A subquery is **a query nested inside another query**. It can appear in WHERE, FROM, SELECT, or HAVING.

### Scalar Subquery

Returns **one value** (one row and one column). It can be used wherever a single value is expected.

```sql
-- Employees paid more than the average
SELECT name, salary
FROM employees
WHERE salary > (SELECT AVG(salary) FROM employees);

-- How much more than average each person earns
SELECT
    name,
    salary,
    salary - (SELECT AVG(salary) FROM employees) AS above_avg
FROM employees;
```

If a scalar subquery returns more than one row, the database raises an error!

### Subquery in FROM (Derived Table / Inline View)

A subquery in FROM produces **a derived table** you can query further:

```sql
-- Average salary by department; then find the department with the highest average
SELECT department, avg_salary
FROM (
    SELECT department, AVG(salary) AS avg_salary
    FROM employees
    GROUP BY department
) AS dept_avg
WHERE avg_salary = (SELECT MAX(avg_salary) FROM (
    SELECT AVG(salary) AS avg_salary
    FROM employees
    GROUP BY department
) AS sub);

-- A CTE (Topic 5) is a more readable alternative!
```

### Subquery with IN

```sql
-- Employees who work in departments located in Belgrade
SELECT name
FROM employees
WHERE department_id IN (
    SELECT id FROM departments WHERE location = 'Belgrade'
);

-- NOT IN: employees who are NOT in those departments
SELECT name
FROM employees
WHERE department_id NOT IN (
    SELECT id FROM departments WHERE location = 'Belgrade'
);
```

**NOT IN and NULL gotcha:**

```sql
-- If the subquery returns [1, 2, NULL]:
-- NOT IN (1, 2, NULL) produces no qualifying rows!
-- Because x != NULL is UNKNOWN, and an AND with UNKNOWN is not TRUE

-- Solution: remove NULLs from the subquery result
WHERE department_id NOT IN (
    SELECT id FROM departments WHERE location = 'Belgrade' AND id IS NOT NULL
);

-- Or use NOT EXISTS (often a better choice):
WHERE NOT EXISTS (
    SELECT 1 FROM departments d
    WHERE d.location = 'Belgrade' AND d.id = e.department_id
);
```

### Correlated Subquery

A subquery that **references the outer query**. Conceptually it is evaluated **for each row** of the outer query, which can be expensive (although an optimizer may rewrite it).

```sql
-- Employees earning above their own department's average
SELECT name, salary, department
FROM employees e
WHERE salary > (
    SELECT AVG(salary)
    FROM employees e2
    WHERE e2.department = e.department   -- references the outer query!
);
```

For each row in `employees e`, the subquery calculates that department's average. With 1,000 employees, this can conceptually mean 1,000 evaluations.

### EXISTS / NOT EXISTS

Checks whether a subquery returns **at least one row**. It only needs to establish TRUE/FALSE, not return the subquery's data.

```sql
-- Customers with at least one order
SELECT c.name
FROM customers c
WHERE EXISTS (
    SELECT 1 FROM orders o WHERE o.customer_id = c.id
);

-- Customers with NO orders
SELECT c.name
FROM customers c
WHERE NOT EXISTS (
    SELECT 1 FROM orders o WHERE o.customer_id = c.id
);
```

In EXISTS, the expression `SELECT 1` is conventional; the selected value does not matter, only whether a row exists. `SELECT *` or `SELECT 42` would work too.

### EXISTS vs IN — When to Use Each

```sql
-- IN: useful when comparing with a set returned by a subquery
-- EXISTS: useful when checking whether any matching row exists
-- EXISTS/NOT EXISTS can avoid the NULL trap of NOT IN

-- Modern query optimizers often make performance very similar
-- For NOT IN versus NOT EXISTS with nullable values, prefer NOT EXISTS
```

### Subquery in SELECT (Scalar Subquery in the SELECT List)

```sql
SELECT
    d.name,
    d.budget,
    (SELECT COUNT(*) FROM employees e WHERE e.department_id = d.id) AS emp_count,
    (SELECT AVG(salary) FROM employees e WHERE e.department_id = d.id) AS avg_salary
FROM departments d;
```

This is a correlated subquery in SELECT. It works, but can be **slower** than JOIN + GROUP BY:

```sql
-- Better alternative:
SELECT d.name, d.budget, COUNT(e.id) AS emp_count, AVG(e.salary) AS avg_salary
FROM departments d
LEFT JOIN employees e ON d.id = e.department_id
GROUP BY d.id, d.name, d.budget;
```

### Interview Questions — Topic 4

**Q1: What is a correlated subquery, and why might it be slow?**
A: A correlated subquery references columns from the outer query. It is conceptually evaluated for every outer row, which may be costly in the worst case. An alternative is a JOIN or CTE that the database optimizer may be able to optimize more effectively.

**Q2: Why is NOT IN dangerous if a subquery might return NULL?**
A: `x NOT IN (1, 2, NULL)` is equivalent to `x != 1 AND x != 2 AND x != NULL`. Since comparison with NULL yields UNKNOWN, this expression cannot be TRUE. The result may be empty. Use NOT EXISTS or filter NULLs out of the subquery.

**Q3: When would you use EXISTS instead of IN?**
A: (1) When NULLs make NOT IN problematic, NOT EXISTS is safer. (2) When checking for existence without needing data from the related table; an EXISTS plan may stop after the first match. (3) Modern optimizers often produce similar plans for IN and EXISTS, so examine the plan when performance matters.

---

## TOPIC 5: CTEs (WITH), Recursive CTEs

### What Is a CTE?

A CTE (Common Table Expression) is **a named temporary result set** available only for the duration of one query. It improves readability and breaks complex queries into manageable steps.

```sql
WITH department_stats AS (
    SELECT
        department_id,
        COUNT(*) AS emp_count,
        AVG(salary) AS avg_salary,
        MAX(salary) AS max_salary
    FROM employees
    GROUP BY department_id
)
SELECT d.name, ds.emp_count, ds.avg_salary, ds.max_salary
FROM departments d
JOIN department_stats ds ON d.id = ds.department_id
WHERE ds.emp_count > 5
ORDER BY ds.avg_salary DESC;
```

### Multiple CTEs

```sql
WITH
    active_customers AS (
        SELECT id, name, email
        FROM customers
        WHERE created_at >= '2024-01-01'
    ),
    customer_orders AS (
        SELECT
            customer_id,
            COUNT(*) AS order_count,
            SUM(quantity * price) AS total_spent
        FROM orders
        WHERE order_date >= '2024-01-01'
        GROUP BY customer_id
    )
SELECT
    ac.name,
    ac.email,
    COALESCE(co.order_count, 0) AS orders,
    COALESCE(co.total_spent, 0) AS spent
FROM active_customers ac
LEFT JOIN customer_orders co ON ac.id = co.customer_id
ORDER BY spent DESC;
```

Each subsequent CTE can reference an earlier one:

```sql
WITH
    step1 AS (SELECT ...),
    step2 AS (SELECT ... FROM step1 ...),   -- uses step1
    step3 AS (SELECT ... FROM step2 ...)    -- uses step2
SELECT * FROM step3;
```

### CTE vs Subquery

| Aspect | CTE | Subquery |
|--------|-----|----------|
| Readability | much better for complex queries | difficult to follow when deeply nested |
| Reuse | can be referenced multiple times in the same query | the subquery may need to be repeated |
| Recursion | supported | not supported directly |
| Performance | similar or different depending on inlining/materialization | depends on the query plan |
| Scope | exists only for the current query | exists only for the current query |

### Recursive CTE

Useful for hierarchical data (employee trees, categories, threaded comments).

Structure:

```sql
WITH RECURSIVE cte_name AS (
    -- 1. Base case (anchor): starting rows
    SELECT ... FROM tabela WHERE uslov

    UNION ALL    -- or UNION to remove duplicates

    -- 2. Recursive case: joins the CTE to itself
    SELECT ... FROM tabela
    JOIN cte_name ON ...   -- refers to itself!
)
SELECT * FROM cte_name;
```

#### Example: Employee Hierarchy

```sql
-- employees(id, name, manager_id)
-- CEO (manager_id = NULL) -> VP -> Director -> Manager -> Developer

WITH RECURSIVE org_tree AS (
    -- Base: CEO (has no manager)
    SELECT id, name, manager_id, 0 AS level, name AS path
    FROM employees
    WHERE manager_id IS NULL

    UNION ALL

    -- Recursive: employees whose managers are already in the hierarchy
    SELECT e.id, e.name, e.manager_id, ot.level + 1,
           ot.path || ' > ' || e.name
    FROM employees e
    JOIN org_tree ot ON e.manager_id = ot.id
)
SELECT level, path, name
FROM org_tree
ORDER BY path;
```

```
Rezultat:
level | path                          | name
0     | CEO                           | CEO
1     | CEO > VP Engineering          | VP Engineering
2     | CEO > VP Engineering > Dev1   | Dev1
2     | CEO > VP Engineering > Dev2   | Dev2
1     | CEO > VP Marketing            | VP Marketing
2     | CEO > VP Marketing > Mark1    | Mark1
```

#### Example: Generating a Number Series

```sql
-- Generate numbers from 1 to 10
WITH RECURSIVE numbers AS (
    SELECT 1 AS n             -- base case
    UNION ALL
    SELECT n + 1 FROM numbers WHERE n < 10   -- recursive case
)
SELECT n FROM numbers;
```

#### Example: Categories and Subcategories

```sql
-- categories(id, name, parent_id)
-- Electronics -> Phones -> Smartphones
--            -> Laptops -> Gaming Laptops

WITH RECURSIVE category_tree AS (
    SELECT id, name, parent_id, 0 AS depth, ARRAY[id] AS path
    FROM categories
    WHERE parent_id IS NULL

    UNION ALL

    SELECT c.id, c.name, c.parent_id, ct.depth + 1, ct.path || c.id
    FROM categories c
    JOIN category_tree ct ON c.parent_id = ct.id
)
SELECT depth, REPEAT('  ', depth) || name AS indented_name
FROM category_tree
ORDER BY path;
```

### Preventing Infinite Recursion

```sql
-- LIMIT on the output
WITH RECURSIVE ... AS (...)
SELECT * FROM cte LIMIT 1000;

-- Or an explicit maximum depth
WITH RECURSIVE org_tree AS (
    SELECT ..., 0 AS level FROM employees WHERE manager_id IS NULL
    UNION ALL
    SELECT ..., ot.level + 1
    FROM employees e JOIN org_tree ot ON ...
    WHERE ot.level < 50   -- maximum 50 levels
)
```

PostgreSQL also provides `statement_timeout`, which can terminate long-running queries.

### Interview Questions — Topic 5

**Q1: What is a CTE, and why would you use it instead of a subquery?**
A: A CTE is a named temporary result set defined with WITH. I use it because (1) it greatly improves readability for complex queries; (2) it can be referenced multiple times in one query; and (3) recursive CTEs can work with hierarchical data. Performance depends on the database and execution plan; a CTE may be inlined.

**Q2: Explain how a recursive CTE works.**
A: It has two parts: a base (anchor) query that returns the starting rows, and a recursive query that refers back to the CTE and generates additional rows. The database repeatedly evaluates the recursive step until no new rows are produced. Common uses include organizational charts, nested categories, and threaded comments.

**Q3: How would you prevent infinite recursion in a recursive CTE?**
A: (1) Add a condition such as `WHERE level < max_depth` in the recursive part; (2) detect or prevent cycles, for example by keeping a visited path; (3) use UNION (instead of UNION ALL) when deduplicating complete rows actually breaks the cycle; and (4) configure a database `statement_timeout` as a safeguard. A final LIMIT alone is not always sufficient.

---

# PART 2: ADVANCED SQL

---

## TOPIC 6: Window Functions

### What Are Window Functions?

Window functions operate over **a set of rows** (a window), but unlike GROUP BY, **do not collapse rows into one**. Each row stays in the result and receives a computed value based on its window.

```sql
-- GROUP BY: 5 departments → 5 rows
SELECT department, AVG(salary) FROM employees GROUP BY department;

-- Window function: 100 employees → 100 rows, each with its department average
SELECT name, department, salary,
       AVG(salary) OVER (PARTITION BY department) AS dept_avg
FROM employees;
```

### Syntax

```sql
function_name(args) OVER (
    [PARTITION BY columns]    -- divides rows into groups (optional)
    [ORDER BY columns]        -- orders rows within each group (optional)
    [ROWS/RANGE frame]       -- defines the window frame (optional)
)
```

### PARTITION BY

Divides rows into groups (partitions). The function is computed separately for each partition:

```sql
SELECT
    name,
    department,
    salary,
    AVG(salary) OVER (PARTITION BY department) AS dept_avg,
    MAX(salary) OVER (PARTITION BY department) AS dept_max,
    salary - AVG(salary) OVER (PARTITION BY department) AS diff_from_avg
FROM employees;
```

```
name  | department  | salary | dept_avg | dept_max | diff_from_avg
Ana   | Engineering | 95000  | 90000    | 120000   | 5000
Marko | Engineering | 85000  | 90000    | 120000   | -5000
Jovan | Engineering | 120000 | 90000    | 120000   | 30000
Petra | Marketing   | 70000  | 72500    | 75000    | -2500
Lena  | Marketing   | 75000  | 72500    | 75000    | 2500
```

Without PARTITION BY, the entire result is one window:

```sql
SELECT name, salary,
       AVG(salary) OVER () AS company_avg   -- company-wide average
FROM employees;
```

### Ranking Functions

#### ROW_NUMBER()

Assigns **a unique row number** to each row within a partition:

```sql
SELECT
    name, department, salary,
    ROW_NUMBER() OVER (PARTITION BY department ORDER BY salary DESC) AS rank_in_dept
FROM employees;
```

```
name  | department  | salary | rank_in_dept
Jovan | Engineering | 120000 | 1
Ana   | Engineering | 95000  | 2
Marko | Engineering | 85000  | 3
Lena  | Marketing   | 75000  | 1
Petra | Marketing   | 70000  | 2
```

**Classic interview pattern — "Top N per group":**

```sql
-- Top three highest-paid employees per department
WITH ranked AS (
    SELECT
        name, department, salary,
        ROW_NUMBER() OVER (PARTITION BY department ORDER BY salary DESC) AS rn
    FROM employees
)
SELECT name, department, salary
FROM ranked
WHERE rn <= 3;
```

#### RANK() vs DENSE_RANK()

The difference becomes visible when there are **ties**:

```sql
-- salary: 100, 100, 90, 80

-- ROW_NUMBER: 1, 2, 3, 4    (always unique; ties need a deterministic tiebreaker)
-- RANK:       1, 1, 3, 4    (skips ranks after ties)
-- DENSE_RANK: 1, 1, 2, 3    (does NOT skip ranks)
```

```sql
SELECT
    name, salary,
    ROW_NUMBER() OVER (ORDER BY salary DESC) AS row_num,
    RANK()       OVER (ORDER BY salary DESC) AS rank,
    DENSE_RANK() OVER (ORDER BY salary DESC) AS dense_rank
FROM employees;
```

### LAG() and LEAD()

Access the **previous** or **next** row:

```sql
-- LAG(column, offset, default): previous row
-- LEAD(column, offset, default): next row

SELECT
    order_date,
    revenue,
    LAG(revenue, 1, 0) OVER (ORDER BY order_date) AS prev_day_revenue,
    revenue - LAG(revenue, 1, 0) OVER (ORDER BY order_date) AS daily_change,
    LEAD(revenue, 1) OVER (ORDER BY order_date) AS next_day_revenue
FROM daily_revenue;
```

```
order_date | revenue | prev_day | daily_change | next_day
2024-01-01 | 1000    | 0        | 1000         | 1200
2024-01-02 | 1200    | 1000     | 200          | 800
2024-01-03 | 800     | 1200     | -400         | 1500
2024-01-04 | 1500    | 800      | 700          | NULL
```

**Classic interview exercise — "Month-over-month growth":**

```sql
WITH monthly AS (
    SELECT
        DATE_TRUNC('month', order_date) AS month,
        SUM(quantity * price) AS revenue
    FROM orders
    GROUP BY DATE_TRUNC('month', order_date)
)
SELECT
    month,
    revenue,
    LAG(revenue) OVER (ORDER BY month) AS prev_month,
    ROUND(
        (revenue - LAG(revenue) OVER (ORDER BY month))::numeric
        / LAG(revenue) OVER (ORDER BY month) * 100, 2
    ) AS growth_pct
FROM monthly;
```

### SUM/AVG OVER — Running and Moving Aggregates

```sql
-- Cumulative sum (running total)
SELECT
    order_date,
    revenue,
    SUM(revenue) OVER (ORDER BY order_date) AS running_total
FROM daily_revenue;

-- Moving average over the last seven days
SELECT
    order_date,
    revenue,
    AVG(revenue) OVER (
        ORDER BY order_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS avg_7_days
FROM daily_revenue;
```

### Window Frame (ROWS/RANGE)

```sql
-- ROWS BETWEEN start AND end
-- start/end may be:
--   UNBOUNDED PRECEDING  — from the start of the partition
--   N PRECEDING          — N preceding rows
--   CURRENT ROW          — the current row
--   N FOLLOWING          — N following rows
--   UNBOUNDED FOLLOWING  — through the end of the partition

-- Default when ORDER BY is specified:
-- RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW

-- Default when ORDER BY is NOT specified:
-- ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
```

### FIRST_VALUE, LAST_VALUE, NTH_VALUE

```sql
SELECT
    name, department, salary,
    FIRST_VALUE(name) OVER (
        PARTITION BY department ORDER BY salary DESC
    ) AS highest_paid_in_dept,
    LAST_VALUE(name) OVER (
        PARTITION BY department ORDER BY salary DESC
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS lowest_paid_in_dept
FROM employees;
```

**LAST_VALUE gotcha:** The default frame is often `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`, so LAST_VALUE returns the current row's peer group's last value, not necessarily the last value of the full partition! Explicitly use `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` if you need the entire partition.

### NTILE

Divides rows into N groups of approximately equal size:

```sql
-- Divide employees into four salary groups (quartiles)
SELECT
    name, salary,
    NTILE(4) OVER (ORDER BY salary) AS salary_quartile
FROM employees;
```

### Interview Questions — Topic 6

**Q1: What is the difference between ROW_NUMBER, RANK, and DENSE_RANK?**
A: For values [100, 100, 90]: ROW_NUMBER gives [1, 2, 3] — always unique, and ties have nondeterministic order without a tiebreaker. RANK gives [1, 1, 3] — equal values get the same rank and the next rank is skipped. DENSE_RANK gives [1, 1, 2] — equal values share a rank, with NO gaps. Use ROW_NUMBER for exactly N rows per group; RANK/DENSE_RANK when ties matter.

**Q2: How would you find the three highest-paid employees in each department?**
A: Use ROW_NUMBER with PARTITION BY and a CTE:
```sql
WITH ranked AS (
    SELECT name, department, salary,
           ROW_NUMBER() OVER (PARTITION BY department ORDER BY salary DESC) AS rn
    FROM employees
)
SELECT * FROM ranked WHERE rn <= 3;
```

**Q3: How would you calculate month-over-month growth?**
A: Use the LAG() window function to access the previous month, then compute the percentage change: `(current - previous) / previous * 100`.

**Q4: What is the difference between GROUP BY and a window function?**
A: GROUP BY summarizes each group in one row, losing row-level detail. A window function adds a calculated value to each row while retaining the original rows. It is like grouping without collapsing the rows.

---

## TOPIC 7: UNION, INTERSECT, EXCEPT + CASE WHEN

### Set Operations

Combine results from two or more SELECT queries. Rules:
- Both queries must return **the same number of columns**.
- Corresponding column types must be **compatible**.
- The output column names come from the **first** query.

#### UNION / UNION ALL

```sql
-- UNION: combines results and REMOVES duplicates
SELECT name, email FROM customers
UNION
SELECT name, email FROM leads;

-- UNION ALL: combines results and RETAINS duplicates (usually faster!)
SELECT name, email FROM customers
UNION ALL
SELECT name, email FROM leads;
```

**UNION ALL is faster** because it does not need sorting or hashing to remove duplicates. Use UNION ALL if duplicates cannot occur or are acceptable.

```sql
-- Common pattern: combine different types into one list
SELECT id, 'customer' AS type, name FROM customers
UNION ALL
SELECT id, 'employee' AS type, name FROM employees
UNION ALL
SELECT id, 'vendor' AS type, name FROM vendors
ORDER BY name;   -- ORDER BY applies to the combined result
```

#### INTERSECT

Returns rows appearing in **both** queries:

```sql
-- Emails appearing in both customers and leads
SELECT email FROM customers
INTERSECT
SELECT email FROM leads;
```

#### EXCEPT (MINUS in Oracle)

Returns rows from the first query that **do not appear** in the second:

```sql
-- Customers who are NOT leads
SELECT email FROM customers
EXCEPT
SELECT email FROM leads;

-- Leads who did NOT become customers
SELECT email FROM leads
EXCEPT
SELECT email FROM customers;
```

### CASE WHEN

SQL's equivalent of if/else. Can be used in SELECT, WHERE, ORDER BY, GROUP BY, etc.

```sql
-- Simple CASE
SELECT
    name,
    salary,
    CASE
        WHEN salary >= 100000 THEN 'Senior'
        WHEN salary >= 70000 THEN 'Mid'
        WHEN salary >= 40000 THEN 'Junior'
        ELSE 'Intern'
    END AS level
FROM employees;
```

CASE conditions are evaluated **from top to bottom** — the first matching branch wins. Put more specific conditions first (as with elif in Python).

#### CASE for Pivot/Crosstab

```sql
-- Convert rows into columns (pivot)
SELECT
    department,
    COUNT(*) AS total,
    COUNT(CASE WHEN salary >= 100000 THEN 1 END) AS senior_count,
    COUNT(CASE WHEN salary >= 70000 AND salary < 100000 THEN 1 END) AS mid_count,
    COUNT(CASE WHEN salary < 70000 THEN 1 END) AS junior_count
FROM employees
GROUP BY department;
```

```
department  | total | senior_count | mid_count | junior_count
Engineering | 15    | 5            | 7         | 3
Marketing   | 8     | 1            | 3         | 4
```

#### CASE in ORDER BY

```sql
-- Custom sort order
SELECT name, status
FROM tasks
ORDER BY
    CASE status
        WHEN 'critical' THEN 1
        WHEN 'high'     THEN 2
        WHEN 'medium'   THEN 3
        WHEN 'low'      THEN 4
        ELSE 5
    END;
```

#### CASE in UPDATE

```sql
UPDATE employees
SET salary = CASE
    WHEN department = 'Engineering' THEN salary * 1.10
    WHEN department = 'Marketing'   THEN salary * 1.05
    ELSE salary * 1.03
END;
```

### COALESCE, NULLIF, GREATEST, LEAST

```sql
-- COALESCE returns the first non-NULL value
SELECT COALESCE(nickname, name, 'Unknown') AS display_name
FROM employees;

-- NULLIF returns NULL when two values are equal (useful for division by zero)
SELECT revenue / NULLIF(cost, 0) AS margin   -- avoids division by zero
FROM products;

-- GREATEST / LEAST (PostgreSQL)
SELECT GREATEST(price1, price2, price3) AS max_price FROM products;
SELECT LEAST(deadline, estimated_date) AS earlier_date FROM tasks;
```

### Interview Questions — Topic 7

**Q1: What is the difference between UNION and UNION ALL?**
A: UNION removes duplicate rows (using sorting or hashing, which adds cost). UNION ALL retains every row, including duplicates, and is usually faster. I use UNION ALL when I know there are no duplicates or duplicates are wanted.

**Q2: How would you build a pivot table in SQL?**
A: Use CASE WHEN inside aggregate functions. For each output column, use something like `COUNT(CASE WHEN condition THEN 1 END)` or `SUM(CASE WHEN condition THEN value ELSE 0 END)`, with GROUP BY for the row categories.

**Q3: What does COALESCE do, and what is a common use case?**
A: COALESCE returns the first non-NULL value from its argument list. I use it for defaults (`COALESCE(nickname, name, 'Unknown')`), to handle NULLs in calculations (`SUM(COALESCE(quantity, 0))`), and for null-safe presentation.

---

## TOPIC 8: INSERT, UPDATE, DELETE, UPSERT (ON CONFLICT), RETURNING

### INSERT

```sql
-- One row
INSERT INTO employees (name, department, salary, hire_date)
VALUES ('Ana', 'Engineering', 85000, '2024-01-15');

-- Multiple rows at once (batch insert, much faster than individual inserts)
INSERT INTO employees (name, department, salary, hire_date)
VALUES
    ('Ana', 'Engineering', 85000, '2024-01-15'),
    ('Marko', 'Marketing', 72000, '2024-02-01'),
    ('Jovan', 'Sales', 68000, '2024-03-10');

-- INSERT from SELECT
INSERT INTO employee_archive (name, department, salary)
SELECT name, department, salary
FROM employees
WHERE hire_date < '2020-01-01';
```

### UPDATE

```sql
-- Basic update
UPDATE employees
SET salary = 90000
WHERE id = 42;

-- Update several columns
UPDATE employees
SET salary = salary * 1.1,
    department = 'Engineering',
    updated_at = NOW()
WHERE name = 'Ana';

-- UPDATE with a JOIN (PostgreSQL syntax)
UPDATE employees e
SET salary = salary * 1.1
FROM departments d
WHERE e.department_id = d.id AND d.name = 'Engineering';
```

**CAUTION:** `UPDATE employees SET salary = 90000;` without a WHERE clause updates **EVERY row**! Always double-check the WHERE clause.

### DELETE

```sql
-- Delete a specific row
DELETE FROM employees WHERE id = 42;

-- Delete rows matching a condition
DELETE FROM employees WHERE hire_date < '2010-01-01';

-- TRUNCATE: faster than DELETE for removing all rows
TRUNCATE TABLE temp_data;
-- TRUNCATE uses statement-level triggers, does not log individual row deletions, and can reset sequences
```

**DELETE vs TRUNCATE:**

| Aspect | DELETE | TRUNCATE |
|--------|--------|----------|
| Logging | individual row changes | more efficient bulk operation |
| WHERE | yes | no |
| Triggers | row-level DELETE triggers | TRUNCATE triggers, if defined |
| Rollback | yes | yes (in PostgreSQL) |
| Speed | can be slow on millions of rows | usually much faster |
| Sequences | not reset | can reset with RESTART IDENTITY |

### UPSERT — INSERT ... ON CONFLICT (PostgreSQL)

"Insert if missing; update if present" — an extremely useful pattern:

```sql
-- On an email conflict, update the row
INSERT INTO customers (email, name, city)
VALUES ('john@example.com', 'John', 'Belgrade')
ON CONFLICT (email)
DO UPDATE SET
    name = EXCLUDED.name,
    city = EXCLUDED.city,
    updated_at = NOW();

-- EXCLUDED references the proposed inserted row

-- ON CONFLICT DO NOTHING: ignore duplicates
INSERT INTO page_views (user_id, page, viewed_at)
VALUES (42, '/about', NOW())
ON CONFLICT DO NOTHING;
```

`ON CONFLICT` requires an appropriate **UNIQUE constraint or index** on the relevant column(s).

```sql
-- Bulk upsert
INSERT INTO product_prices (product_id, price, updated_at)
VALUES
    (1, 29.99, NOW()),
    (2, 49.99, NOW()),
    (3, 19.99, NOW())
ON CONFLICT (product_id)
DO UPDATE SET
    price = EXCLUDED.price,
    updated_at = EXCLUDED.updated_at;
```

### RETURNING (PostgreSQL)

Returns data from modified rows — no need for another SELECT:

```sql
-- Return the new row's ID
INSERT INTO employees (name, department, salary)
VALUES ('Ana', 'Engineering', 85000)
RETURNING id;

-- Return all columns
INSERT INTO employees (name, department, salary)
VALUES ('Ana', 'Engineering', 85000)
RETURNING *;

-- RETURNING with UPDATE
UPDATE employees SET salary = salary * 1.1
WHERE department = 'Engineering'
RETURNING id, name, salary AS new_salary;

-- RETURNING with DELETE
DELETE FROM employees WHERE hire_date < '2010-01-01'
RETURNING id, name;   -- tells you which rows were deleted
```

RETURNING is extremely useful in application code because it saves a round trip to the database.

### Interview Questions — Topic 8

**Q1: What is an UPSERT, and how do you implement one in PostgreSQL?**
A: An UPSERT is an INSERT that instead performs an UPDATE when a uniqueness conflict occurs. PostgreSQL uses `INSERT ... ON CONFLICT (column) DO UPDATE SET ...`. The EXCLUDED pseudo-table contains the proposed values. UPSERTs are useful for idempotent operations.

**Q2: What is the difference between DELETE and TRUNCATE?**
A: DELETE removes selected rows and can use WHERE; it fires DELETE triggers. TRUNCATE removes all rows efficiently, does not support WHERE, and fires TRUNCATE triggers if defined (not row-level DELETE triggers). Both can be rolled back in PostgreSQL.

**Q3: What is the RETURNING clause for?**
A: It returns data from rows just INSERTed, UPDATEd, or DELETEd. This saves an extra SELECT. A typical example is `INSERT ... RETURNING id` to get the auto-generated ID of the new row.

---

## TOPIC 9: Views, Materialized Views, Temporary Tables

### Views

A view is **a named query** that acts like a virtual table. A regular view does not store its result; the underlying query is evaluated when accessed.

```sql
-- Creating a view
CREATE VIEW active_employees AS
SELECT id, name, department, salary, hire_date
FROM employees
WHERE status = 'active' AND hire_date >= '2020-01-01';

-- Querying it (just like a table)
SELECT name, salary FROM active_employees WHERE department = 'Engineering';

-- Dropping it
DROP VIEW active_employees;

-- Replacing it (CREATE OR REPLACE)
CREATE OR REPLACE VIEW active_employees AS
SELECT id, name, department, salary, hire_date, email
FROM employees
WHERE status = 'active';
```

Benefits of views:
- **Encapsulation** — hide complex queries behind a simple name.
- **Security** — grant access to a view without exposing the underlying table or sensitive columns.
- **Consistency** — define a complex query once instead of copying it everywhere.

### Materialized Views (PostgreSQL)

A materialized view **stores a query result on disk**. It reads quickly, but must be refreshed to incorporate changes.

```sql
-- Creating a materialized view
CREATE MATERIALIZED VIEW monthly_revenue AS
SELECT
    DATE_TRUNC('month', order_date) AS month,
    SUM(quantity * price) AS revenue,
    COUNT(DISTINCT customer_id) AS unique_customers
FROM orders
GROUP BY DATE_TRUNC('month', order_date);

-- Reading: uses stored query results
SELECT * FROM monthly_revenue WHERE month >= '2024-01-01';

-- Refreshing: re-executes the query and replaces stored results
REFRESH MATERIALIZED VIEW monthly_revenue;

-- Concurrent refresh (permits reads during refresh)
REFRESH MATERIALIZED VIEW CONCURRENTLY monthly_revenue;
-- Requires an appropriate UNIQUE index on the materialized view!

CREATE UNIQUE INDEX ON monthly_revenue (month);
```

**View vs Materialized View:**

| Aspect | View | Materialized View |
|--------|------|-------------------|
| Data storage | no (virtual) | yes (on disk) |
| Read speed | comparable to the underlying query | often very fast (precomputed) |
| Data freshness | reflects current underlying data | may be stale |
| Refresh | evaluated on access | explicit REFRESH |
| Indexes | cannot index a regular view directly | yes |
| Use case | encapsulation, security | dashboards, reports, expensive aggregations |

### Temporary Tables

Temporary tables exist only during **the current session** (or transaction, with the appropriate option). They are automatically removed.

```sql
-- Creating a temporary table
CREATE TEMPORARY TABLE temp_results (
    id SERIAL,
    name TEXT,
    score NUMERIC
);

-- Or CREATE TEMP TABLE (short form)
CREATE TEMP TABLE temp_calc AS
SELECT department, AVG(salary) AS avg_sal
FROM employees
GROUP BY department;

-- Use it like an ordinary table
SELECT * FROM temp_calc WHERE avg_sal > 80000;

-- Automatically dropped at the end of the session
-- Or explicitly:
DROP TABLE temp_results;

-- Temporary table lasting only until transaction commit:
CREATE TEMP TABLE temp_tx (...) ON COMMIT DROP;
```

Use temporary tables for:
- Intermediate results in complex procedures.
- Staging data for ETL.
- Testing and debugging.

### Interview Questions — Topic 9

**Q1: What is the difference between a View and a Materialized View?**
A: A view is a virtual table that does not store query results. A materialized view stores the result on disk, making reads faster, but it must be refreshed with REFRESH. A regular view reflects current underlying data, while a materialized view may become stale.

**Q2: When would you use a Materialized View?**
A: For expensive aggregations that do not need real-time updates, such as dashboards, monthly reports, or analytics. For example, refresh monthly revenue computed over millions of rows every day or hour, then read it quickly. Materialized views can also be indexed for better query performance.

**Q3: What is a temporary table, and when does it disappear?**
A: A temporary table exists only in the current database session and is automatically dropped at session end. It is useful for intermediate results and ETL staging. `ON COMMIT DROP` makes it last only until the transaction is committed.

---

## TOPIC 10: Stored Procedures, Functions, Triggers (Overview)

### Functions (PostgreSQL)

```sql
-- Creating a function
CREATE OR REPLACE FUNCTION get_employee_bonus(emp_salary NUMERIC, dept TEXT)
RETURNS NUMERIC AS $$
BEGIN
    IF dept = 'Engineering' THEN
        RETURN emp_salary * 0.15;
    ELSIF dept = 'Sales' THEN
        RETURN emp_salary * 0.20;
    ELSE
        RETURN emp_salary * 0.10;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Using it
SELECT name, salary, get_employee_bonus(salary, department) AS bonus
FROM employees;
```

**SQL function vs PL/pgSQL function:**

```sql
-- SQL function (simpler; optimizer may inline it)
CREATE FUNCTION full_name(first TEXT, last TEXT)
RETURNS TEXT AS $$
    SELECT first || ' ' || last;
$$ LANGUAGE sql;

-- PL/pgSQL function (logic, loops, conditions)
CREATE FUNCTION calculate_tax(amount NUMERIC)
RETURNS NUMERIC AS $$
BEGIN
    IF amount > 100000 THEN RETURN amount * 0.3;
    ELSIF amount > 50000 THEN RETURN amount * 0.2;
    ELSE RETURN amount * 0.1;
    END IF;
END;
$$ LANGUAGE plpgsql;
```

### Stored Procedures (Since PostgreSQL 11)

Unlike functions, procedures can **manage transactions** (COMMIT/ROLLBACK within a procedure, subject to PostgreSQL's invocation restrictions).

```sql
CREATE OR REPLACE PROCEDURE transfer_funds(
    sender_id INT,
    receiver_id INT,
    amount NUMERIC
)
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE accounts SET balance = balance - amount WHERE id = sender_id;
    UPDATE accounts SET balance = balance + amount WHERE id = receiver_id;
    COMMIT;
END;
$$;

-- Calling the procedure (CALL, not SELECT)
CALL transfer_funds(1, 2, 500.00);
```

### Triggers

A trigger invokes a function **automatically** when a specified event occurs, such as INSERT, UPDATE, or DELETE.

```sql
-- Trigger function
CREATE OR REPLACE FUNCTION update_modified_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Attach the trigger
CREATE TRIGGER set_updated_at
    BEFORE UPDATE ON employees
    FOR EACH ROW
    EXECUTE FUNCTION update_modified_timestamp();

-- Now every UPDATE to employees automatically sets updated_at
```

Types of triggers:
- **BEFORE** — before an operation (can modify a row).
- **AFTER** — after an operation (for logging or notifications).
- **FOR EACH ROW** — for every affected row.
- **FOR EACH STATEMENT** — once per statement.

```sql
-- Audit log trigger
CREATE TABLE audit_log (
    id SERIAL PRIMARY KEY,
    table_name TEXT,
    action TEXT,
    old_data JSONB,
    new_data JSONB,
    changed_at TIMESTAMPTZ DEFAULT NOW(),
    changed_by TEXT DEFAULT current_user
);

CREATE OR REPLACE FUNCTION audit_trigger()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO audit_log (table_name, action, old_data, new_data)
    VALUES (
        TG_TABLE_NAME,
        TG_OP,
        CASE WHEN TG_OP = 'DELETE' THEN row_to_json(OLD)::jsonb ELSE NULL END,
        CASE WHEN TG_OP != 'DELETE' THEN row_to_json(NEW)::jsonb ELSE NULL END
    );
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;
```

### When to Use Which

- **Functions** — calculations, transformations, and reusable logic inside queries.
- **Procedures** — transactional batch operations and administrative jobs.
- **Triggers** — automatic actions (auditing, updated_at, validation, denormalization).

**Caution with triggers:** They can make a system harder to understand and debug because the logic is hidden. They also add overhead to writes. Use them judiciously.

### Interview Questions — Topic 10

**Q1: What is the difference between a Function and a Stored Procedure in PostgreSQL?**
A: A function is invoked in an expression (such as SELECT), returns a result, and cannot commit or roll back its own transaction. A procedure is called with CALL and may manage transactions under certain conditions; procedures were introduced in PostgreSQL 11. Use functions for calculations and procedures for batch/administrative tasks.

**Q2: What is a trigger, and what are its risks?**
A: A trigger invokes logic automatically on events such as INSERT, UPDATE, and DELETE. Risks include hidden behavior, harder debugging, write overhead, cascading effects, and more complex migrations. Triggers are often useful for audit logs or updated_at, but avoid unnecessary business logic in them.

---

# PART 3: DATABASE DESIGN

---

## TOPIC 11: Normalization (1NF, 2NF, 3NF, BCNF)

### What Is Normalization?

Normalization organizes data into tables to **reduce redundancy** and **prevent anomalies** (insertion, update, and deletion anomalies).

### Anomalies Without Normalization

Imagine an `orders_flat` table:

```
order_id | customer_name | customer_email      | product | price | quantity
1        | Ana           | ana@mail.com        | Laptop  | 1000  | 1
2        | Ana           | ana@mail.com        | Mouse   | 25    | 2
3        | Marko         | marko@mail.com      | Laptop  | 1000  | 1
```

Problems:
- **Update anomaly:** Ana changes her email — every one of her rows needs updating.
- **Insertion anomaly:** We cannot add a new customer until they place an order.
- **Deletion anomaly:** Deleting all of Marko's orders also loses his customer data.

### 1NF (First Normal Form)

Rules:
1. Each column contains **atomic** (indivisible) values in the context of the domain.
2. There are no repeating groups of columns.
3. Rows are identifiable using a key.

```
-- VIOLATES 1NF (non-atomic values):
id | name  | phones
1  | Ana   | 065123, 066456        -- multiple values in one column

-- VIOLATES 1NF (repeating groups):
id | name  | phone1  | phone2  | phone3    -- how many columns? What if we need four?

-- 1NF:
-- employees table:                 phones table:
-- id | name                   id | employee_id | phone
-- 1  | Ana                    1  | 1           | 065123
--                             2  | 1           | 066456
```

### 2NF (Second Normal Form)

Requirements: 1NF + **every non-key attribute depends on the ENTIRE candidate key**, not just part of a composite key.

This matters especially when you have a **composite** key (multiple columns).

```
-- Table: student_courses
-- Composite PK: (student_id, course_id)

student_id | course_id | student_name | course_name | grade
1          | 101       | Ana          | Math        | A
1          | 102       | Ana          | Physics     | B
2          | 101       | Marko        | Math        | C

-- VIOLATES 2NF:
-- student_name depends ONLY on student_id (part of the key), not the whole key
-- course_name depends ONLY on course_id (part of the key)

-- 2NF:
-- students(student_id PK, student_name)
-- courses(course_id PK, course_name)
-- enrollments(student_id, course_id, grade) PK(student_id, course_id)
```

### 3NF (Third Normal Form)

Requirements: 2NF + **no problematic transitive dependencies** of non-key attributes on keys through other non-key attributes.

```
-- Table: employees
-- PK: employee_id

employee_id | name  | department_id | department_name | department_location
1           | Ana   | 10            | Engineering     | Belgrade
2           | Marko | 10            | Engineering     | Belgrade
3           | Jovan | 20            | Marketing       | Novi Sad

-- VIOLATES 3NF:
-- department_name and department_location depend on department_id, not employee_id
-- This is a transitive dependency: employee_id -> department_id -> department_name

-- 3NF:
-- employees(employee_id PK, name, department_id FK)
-- departments(department_id PK, department_name, department_location)
```

### BCNF (Boyce-Codd Normal Form)

BCNF requires **every determinant X in a nontrivial functional dependency X → Y to be a superkey**.

BCNF is stricter than 3NF. Differences usually arise only with more complex functional dependencies.

```
-- Example that satisfies 3NF but NOT BCNF:
-- table: teaching(student, subject, professor)
-- Dependencies:
--   (student, subject) -> professor (composite PK)
--   professor -> subject (each professor teaches only one subject)
--
-- professor -> subject is a dependency where professor is NOT a superkey
-- Solution: split into two tables
```

### Practical Normalization Example

```
-- Unnormalized:
order_id | date       | cust_name | cust_email    | items
1        | 2024-01-01 | Ana       | ana@mail.com  | Laptop:1000:1, Mouse:25:2

-- 1NF (atomic values):
order_id | date       | cust_name | cust_email    | product | price | qty
1        | 2024-01-01 | Ana       | ana@mail.com  | Laptop  | 1000  | 1
1        | 2024-01-01 | Ana       | ana@mail.com  | Mouse   | 25    | 2

-- 2NF (split according to dependencies on the key):
-- orders(order_id, date, customer_id)
-- order_items(order_id, product_id, qty)   PK(order_id, product_id)
-- customers(customer_id, name, email)
-- products(product_id, name, price)

-- 3NF: already satisfies 3NF because there are no transitive dependencies
```

### How Far Should You Normalize?

- **3NF is the usual standard for most applications**.
- BCNF may be beneficial but often makes little practical difference.
- 4NF and 5NF exist but are rarely discussed in standard interviews.
- Sometimes **denormalization** is better (next topic).

### Interview Questions — Topic 11

**Q1: Explain normalization and why it matters.**
A: Normalization splits data into appropriate tables to reduce redundancy and avoid insert, update, and delete anomalies. Without normalization, the same information is stored in multiple places, which can cause inconsistencies when only one copy is updated.

**Q2: Explain the difference between 1NF, 2NF, and 3NF.**
A: 1NF: atomic values, no repeating groups, and identifiable rows. 2NF: non-key attributes depend on the whole candidate key, not just part of it. 3NF: removes inappropriate transitive dependencies. Each normal form builds on the previous one.

**Q3: How far do you usually normalize in practice?**
A: 3NF is a common target for OLTP (transactional) systems, with BCNF where appropriate. In analytics and reporting, I may intentionally denormalize into star schemas or wide tables to optimize reads. It is a tradeoff between redundancy and the need for joins.

---

## TOPIC 12: Denormalization (When, Why, Tradeoffs)

### What Is Denormalization?

Intentionally introducing redundant data to **speed up reads** — the opposite of normalization.

### When Should You Denormalize?

1. **Read-heavy workloads** — many more reads than writes (e.g., a 90:10 ratio).
2. **Frequent expensive JOINs** — repeatedly joining five or more tables for one view.
3. **Reporting/analytics** — dashboards and reports where read performance is critical.
4. **Cached/derived fields** — total comment count, last login, etc.

### Denormalization Techniques

#### 1. Duplicated Columns

```sql
-- Normalized:
-- orders(id, customer_id, ...)  + customers(id, name, email)
-- Each time, JOIN to display the customer's name

-- Denormalized: add customer_name directly to orders
ALTER TABLE orders ADD COLUMN customer_name TEXT;
-- When creating an order, copy the name from customers
-- Tradeoff: if the customer changes their name, orders may need updating too
```

#### 2. Precomputed Fields (Computed/Derived)

```sql
-- Instead of calculating COUNT(*) every time:
ALTER TABLE posts ADD COLUMN comment_count INTEGER DEFAULT 0;

-- Update after every new comment (trigger or application logic):
UPDATE posts SET comment_count = comment_count + 1 WHERE id = 123;

-- Now displaying the count does not require a COUNT(*) JOIN:
SELECT title, comment_count FROM posts;  -- instant!
```

#### 3. Materialized Views (Covered in Topic 9)

#### 4. Star Schema (Data Warehousing)

```sql
-- Fact table: central table containing measures
-- fact_sales(date_id, product_id, customer_id, store_id, quantity, revenue)

-- Dimension tables: descriptive attributes
-- dim_date(id, date, month, quarter, year, day_of_week)
-- dim_product(id, name, category, brand)
-- dim_customer(id, name, city, country, segment)
-- dim_store(id, name, city, region)

-- Straightforward analysis JOINs (one per dimension):
SELECT
    d.year, d.quarter, p.category,
    SUM(f.revenue) AS total_revenue
FROM fact_sales f
JOIN dim_date d ON f.date_id = d.id
JOIN dim_product p ON f.product_id = p.id
GROUP BY d.year, d.quarter, p.category;
```

### Tradeoffs

| Aspect | Normalized | Denormalized |
|--------|--------------|-----------------|
| Reading | can require more JOINs | often faster |
| Writing | generally simpler | more updates may be needed |
| Storage | less redundancy | more redundancy |
| Consistency | easier to maintain | potential inconsistencies |
| Query complexity | more complex SELECTs | simpler SELECTs |
| Application complexity | generally simpler | synchronization logic required |

### Interview Rule of Thumb

"Normalize first (often to 3NF), then denormalize selectively where measurements show that read performance is a bottleneck."

### Interview Questions — Topic 12

**Q1: When would you denormalize a database?**
A: For read-heavy workloads, repeated expensive JOINs on critical paths, or reporting/analytics where query speed is the priority. I start with a normalized design and denormalize specific parts based on measurements.

**Q2: What are the risks of denormalization?**
A: (1) Data inconsistency when the same information is stored in several places; (2) more complicated updates; (3) extra storage; and (4) more application logic to keep copies synchronized. Mitigations include triggers, event-driven updates, or intentionally accepting eventual consistency.

---

## TOPIC 13: ER Diagrams, Schema Design, Naming Conventions

### Relationship Types

#### One-to-One (1:1)

One row in table A corresponds to one row in table B.

```sql
-- Example: User and UserProfile are separate because profiles have many rarely-read fields
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);

CREATE TABLE user_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),  -- PK is also an FK!
    bio TEXT,
    avatar_url TEXT,
    date_of_birth DATE
);
```

#### One-to-Many (1:N) — Most Common

One row in table A corresponds to multiple rows in table B.

```sql
-- One department has many employees
CREATE TABLE departments (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE employees (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    department_id INTEGER REFERENCES departments(id)  -- FK on the "many" side
);
```

**The foreign key belongs on the "many" side!**

#### Many-to-Many (M:N)

Implemented with a **junction/bridge table**:

```sql
-- One student takes many courses; one course has many students
CREATE TABLE students (id SERIAL PRIMARY KEY, name TEXT);
CREATE TABLE courses (id SERIAL PRIMARY KEY, title TEXT);

-- Junction table
CREATE TABLE enrollments (
    student_id INTEGER REFERENCES students(id),
    course_id INTEGER REFERENCES courses(id),
    enrolled_at TIMESTAMPTZ DEFAULT NOW(),
    grade CHAR(1),
    PRIMARY KEY (student_id, course_id)  -- composite primary key
);
```

### Naming Conventions

In interviews, demonstrate that you know common conventions. Consistency matters more than the exact convention you choose.

| Aspect | Recommendation | Example |
|--------|-----------|--------|
| Tables | plural, snake_case | `employees`, `order_items` |
| Columns | singular, snake_case | `first_name`, `created_at` |
| Primary key | `id` | `employees.id` |
| Foreign key | `singular_table_id` | `department_id`, `customer_id` |
| Boolean | prefixes `is_`, `has_`, `can_` | `is_active`, `has_paid` |
| Timestamps | suffix `_at` | `created_at`, `updated_at`, `deleted_at` |
| Indexes | `idx_table_columns` | `idx_employees_department_id` |
| Constraints | `uq_table_columns`, `chk_table_condition` | `uq_users_email` |

### Soft Delete Pattern

Instead of physically deleting a row, set `deleted_at`:

```sql
ALTER TABLE employees ADD COLUMN deleted_at TIMESTAMPTZ;

-- "Delete" an employee
### Timestamps Pattern

-- All normal queries should filter:
SELECT * FROM employees WHERE deleted_at IS NULL;

-- Or create a view:
CREATE VIEW active_employees AS
SELECT * FROM employees WHERE deleted_at IS NULL;
```

### Timestamps pattern

Every table should have:

```sql
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    -- ... columns ...
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trigger for updated_at (already shown in Topic 10)
```

**Prefer TIMESTAMPTZ** for timestamps that represent real-world instants; it makes time-zone handling safer. TIMESTAMP without a time zone is appropriate for local wall-clock values.

### Interview Questions — Topic 13

**Q1: How would you implement a many-to-many relationship?**
A: Through a junction (bridge) table with foreign keys to both tables. For students and courses, I would create enrollments with student_id and course_id. A composite primary key (student_id, course_id) prevents duplicate enrollments. The table can also have columns such as grade or enrolled_at.

**Q2: Why use TIMESTAMPTZ instead of TIMESTAMP?**
A: TIMESTAMP stores a date and time without time-zone information. TIMESTAMPTZ represents an absolute instant, stored internally in a time-zone-independent way and displayed according to the session time zone. It avoids a whole class of time-zone bugs.

**Q3: What is a soft delete, and why use one?**
A: Instead of physically deleting a row, set its deleted_at timestamp. Benefits: the row can be restored, audit history is retained, and foreign-key references remain intact. Drawbacks: queries must filter `WHERE deleted_at IS NULL` and the table grows. A partial index for active rows can help.

---

## TOPIC 14: Data Types

### Numeric Types

| Type | Size | Range | Use for |
|-----|----------|-------|-----------|
| `SMALLINT` | 2 bytes | -32,768 to 32,767 | status codes, small counters |
| `INTEGER` | 4 bytes | about -2.1B to 2.1B | IDs, most counters |
| `BIGINT` | 8 bytes | about -9.2×10¹⁸ to 9.2×10¹⁸ | large systems, large IDs |
| `SERIAL` | 4 bytes | auto-increment INTEGER | primary keys (legacy approach) |
| `BIGSERIAL` | 8 bytes | auto-increment BIGINT | primary keys in large tables |
| `NUMERIC(p,s)` | variable | exact decimal | money, finance |
| `REAL` | 4 bytes | about 6 significant decimal digits | approximate scientific values |
| `DOUBLE PRECISION` | 8 bytes | about 15 significant decimal digits | approximate scientific values |

**NEVER use REAL/DOUBLE for money!** Floating-point rounding errors:

```sql
SELECT 0.1 + 0.2;  -- 0.30000000000000004
-- Use NUMERIC(10, 2) for money:
SELECT CAST(0.1 AS NUMERIC) + CAST(0.2 AS NUMERIC);  -- 0.3
```

**SERIAL vs IDENTITY (Modern Approach):**

```sql
-- Legacy (SERIAL):
CREATE TABLE users (id SERIAL PRIMARY KEY);

-- Modern (GENERATED ALWAYS AS IDENTITY): SQL standard
CREATE TABLE users (id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY);
```

### String Types

| Type | Description | Maximum length |
|-----|------|-----------|
| `CHAR(n)` | fixed length, padded with spaces | n characters |
| `VARCHAR(n)` | variable length with a limit | n characters |
| `TEXT` | variable length without a specified limit | practically unlimited |

**In PostgreSQL, TEXT and VARCHAR use the same underlying storage!** The key difference is the optional length constraint. Use:
- `TEXT` for most strings (without arbitrary limits).
- `VARCHAR(n)` where a length limit has business meaning (e.g., country_code VARCHAR(3)).
- `CHAR(n)` rarely (it is space-padded).

### Date/Time Types

| Type | Description | Example |
|-----|------|--------|
| `DATE` | date only | '2024-01-15' |
| `TIME` | time only | '14:30:00' |
| `TIMESTAMP` | date + time, WITHOUT time zone | '2024-01-15 14:30:00' |
| `TIMESTAMPTZ` | timestamp representing an instant, WITH time-zone conversion | '2024-01-15 14:30:00+01' |
| `INTERVAL` | duration | '2 hours 30 minutes' |

```sql
-- Useful functions
SELECT NOW();                           -- current timestamp with time-zone handling
SELECT CURRENT_DATE;                    -- current date
SELECT AGE(NOW(), hire_date);           -- difference as an interval
SELECT DATE_TRUNC('month', NOW());      -- beginning of the current month
SELECT EXTRACT(YEAR FROM hire_date);    -- extract the year
```

### Boolean

```sql
-- TRUE inputs include: TRUE, 'yes', 'on', '1', 't', 'y'
-- FALSE inputs include: FALSE, 'no', 'off', '0', 'f', 'n'
-- Values are stored as TRUE, FALSE, or NULL

CREATE TABLE features (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    is_enabled BOOLEAN NOT NULL DEFAULT FALSE
);
```

### UUID

```sql
-- Useful for distributed ID generation without sequence coordination
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL
);

-- Or use gen_random_uuid() (built into modern PostgreSQL versions)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL
);
```

**UUID vs SERIAL for Primary Keys:**

| Aspect | SERIAL/BIGSERIAL | UUID |
|--------|-----------------|------|
| Size | 4/8 bytes | 16 bytes |
| Generation | sequential | generated identifiers (often random) |
| Index performance | often better locality | random UUIDs can cause scattered writes |
| Distributed use | may require coordination | usually no central coordinator needed |
| Predictability | predictable | typically hard to guess |

### JSONB (PostgreSQL)

```sql
CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    type TEXT NOT NULL,
    data JSONB NOT NULL,          -- structured JSON
    created_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO events (type, data) VALUES
('user_signup', '{"name": "Ana", "email": "ana@mail.com", "plan": "pro"}');

-- Query JSONB
SELECT data->>'name' AS name FROM events WHERE type = 'user_signup';
SELECT * FROM events WHERE data @> '{"plan": "pro"}';  -- contains
SELECT * FROM events WHERE data->>'email' LIKE '%@mail.com';

-- GIN index for JSONB
CREATE INDEX idx_events_data ON events USING GIN (data);
```

### Interview Questions — Topic 14

**Q1: Why should you avoid FLOAT/DOUBLE for money?**
A: Floating-point arithmetic has rounding errors (`0.1 + 0.2 != 0.3` in typical binary floating point). Use NUMERIC(precision, scale) for exact decimal arithmetic. For example, NUMERIC(10,2) can store up to 10 digits total, including 2 after the decimal point.

**Q2: When would you use UUID instead of SERIAL for a primary key?**
A: In distributed systems where several servers generate IDs: SERIAL usually requires a coordinated sequence, while UUIDs can be generated independently. UUIDs also make IDs harder to guess. Downsides include 16-byte size versus 4/8 bytes, sometimes worse index locality, and reduced readability.

**Q3: Why do TEXT and VARCHAR have similar performance in PostgreSQL?**
A: PostgreSQL uses the same underlying variable-length storage for both, with TOAST for sufficiently large values. VARCHAR(n) adds a maximum-length check. Storage and performance are generally comparable.

---

## TOPIC 15: Constraints (PK, FK, UNIQUE, CHECK, NOT NULL, CASCADE, DEFAULT)

### PRIMARY KEY

A unique row identifier. Automatically implies NOT NULL and UNIQUE, and creates an index.

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL
);

-- Composite primary key
CREATE TABLE order_items (
    order_id INTEGER REFERENCES orders(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL,
    PRIMARY KEY (order_id, product_id)
);
```

### FOREIGN KEY

A reference to a key in another table. Enforces **referential integrity** — preventing invalid references.

```sql
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Explicit syntax:
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    CONSTRAINT fk_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);
```

#### ON DELETE / ON UPDATE Options:

| Option | Behavior |
|--------|----------|
| `CASCADE` | automatically delete/update child rows |
| `RESTRICT` | refuse to delete/update a referenced parent row |
| `SET NULL` | set the child's foreign key to NULL |
| `SET DEFAULT` | set the child's foreign key to its default |
| `NO ACTION` | similar to RESTRICT, but can be checked later if the constraint is deferrable |

```sql
-- CASCADE: deleting a customer deletes their orders
CREATE TABLE orders (
    customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE
);

-- SET NULL: deleting a department sets employees' department_id to NULL
CREATE TABLE employees (
    department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL
);

-- RESTRICT: cannot delete a department with employees
CREATE TABLE employees (
    department_id INTEGER REFERENCES departments(id) ON DELETE RESTRICT
);
```

### UNIQUE

Ensures values in a column or combination of columns are unique (subject to NULL semantics).

```sql
-- One column
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL
);

-- Multiple columns (the combination must be unique)
CREATE TABLE enrollments (
    student_id INTEGER REFERENCES students(id),
    course_id INTEGER REFERENCES courses(id),
    UNIQUE (student_id, course_id)
);
```

**NULL with UNIQUE:** PostgreSQL normally allows **multiple NULLs** in a UNIQUE column because NULLs are treated as distinct by default. If you need different behavior, consider `NULLS NOT DISTINCT` (PostgreSQL 15+) or an appropriate unique index:

```sql
CREATE UNIQUE INDEX idx_one_null ON users (email) WHERE email IS NOT NULL;
```

### CHECK

Database-level validation:

```sql
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    price NUMERIC(10, 2) CHECK (price > 0),
    stock INTEGER CHECK (stock >= 0),
    category TEXT CHECK (category IN ('electronics', 'clothing', 'food')),
    CONSTRAINT price_less_than_max CHECK (price < 1000000)
);

-- CHECK across multiple columns
CREATE TABLE events (
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    CONSTRAINT valid_dates CHECK (end_date > start_date)
);
```

### NOT NULL

```sql
CREATE TABLE employees (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,         -- required field
    email TEXT NOT NULL,        -- required field
    nickname TEXT,              -- optional (may be NULL)
    salary NUMERIC NOT NULL CHECK (salary > 0)
);
```

**Design principle:** Mark all mandatory columns NOT NULL. Start with clear constraints and relax them only if the requirements warrant it. Unexpected NULLs are a frequent source of bugs.

### DEFAULT

```sql
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending',
    quantity INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_paid BOOLEAN NOT NULL DEFAULT FALSE
);
```

### Combined Example

```sql
CREATE TABLE products (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    sku TEXT NOT NULL UNIQUE,
    price NUMERIC(10, 2) NOT NULL CHECK (price > 0),
    cost NUMERIC(10, 2) CHECK (cost > 0),
    stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    category TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT positive_margin CHECK (price > COALESCE(cost, 0))
);
```

### Interview Questions — Topic 15

**Q1: What is the difference between CASCADE and RESTRICT for ON DELETE?**
A: CASCADE automatically deletes child rows when the parent is deleted (for example, removing a customer also removes their orders). RESTRICT blocks deletion of the parent while child rows exist. CASCADE is convenient but can be risky; RESTRICT is more conservative.

**Q2: Why use a database CHECK constraint instead of checking only in the application?**
A: Application code may have bugs or multiple entry points (APIs, admin tools, migrations, direct SQL). The database provides a final line of defense: if CHECK requires `price > 0`, invalid prices are rejected regardless of where the INSERT originated. This is defense in depth.

**Q3: Can a UNIQUE column contain multiple NULL values?**
A: Yes, in PostgreSQL by default, since NULLs are treated as distinct. SQL Server generally allows only one NULL in a single-column unique constraint. PostgreSQL 15+ can also enforce `NULLS NOT DISTINCT`. NULL handling is a notable cross-database difference.

---

# PART 4: INDEXING AND QUERY PERFORMANCE

---

## TOPIC 16: B-tree Indexes

### What Is an Index?

An index is **a separate data structure** that speeds up table lookups, much like a book index helps you find pages.

Without a useful index, the database may need to read **every row** (Sequential Scan / Full Table Scan). With one, it can locate matching rows much more efficiently.

### B-tree (Balanced Tree)

**The default index type** in most relational databases. Useful for: `=`, `<`, `>`, `<=`, `>=`, `BETWEEN`, `IN`, and some prefix `LIKE` cases (but not generally `LIKE '%suffix'`).

#### How It Works Internally

A B-tree is a balanced search tree with:
- **Root node** — the top of the tree and starting point for a lookup.
- **Internal nodes** — guide the search to appropriate branches.
- **Leaf nodes** — contain indexed values and references to table rows.

```
                    [50]                          -- root
                   /    \
              [20,30]    [70,90]                  -- internal nodes
              / | \      / | \
         [10,15] [25] [55,60] [75,80] [95,100]   -- linked leaf nodes
```

Linked leaf pages make range scans efficient because the database can traverse consecutive indexed values.

**Lookup complexity: O(log N)** in the usual tree model — far fewer steps than scanning a million rows.

#### Creating an Index

```sql
-- Regular index
CREATE INDEX idx_employees_department ON employees (department);

-- Unique index (automatically created for PK and UNIQUE constraints)
CREATE UNIQUE INDEX idx_users_email ON users (email);

-- Inspect existing indexes
SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'employees';
```

#### When B-tree Helps, and When It Does Not

**Helps:**

```sql
-- Equality (=)
SELECT * FROM employees WHERE department = 'Engineering';

-- Range (<, >, BETWEEN)
SELECT * FROM employees WHERE salary BETWEEN 50000 AND 100000;

-- Prefix LIKE
SELECT * FROM employees WHERE name LIKE 'Ana%';

-- IN
SELECT * FROM employees WHERE department IN ('Engineering', 'Sales');

-- ORDER BY (may avoid an explicit sort)
SELECT * FROM employees ORDER BY salary;

-- MIN/MAX (may scan only the first/last index entry)
SELECT MIN(salary) FROM employees;
```

**Does NOT help:**

```sql
-- Suffix/infix LIKE (B-tree cannot seek efficiently from a leading wildcard)
SELECT * FROM employees WHERE name LIKE '%ana';
SELECT * FROM employees WHERE name LIKE '%ana%';

-- Function on an indexed column (may prevent direct index use)
SELECT * FROM employees WHERE LOWER(name) = 'ana';
-- Solution: expression index
CREATE INDEX idx_emp_name_lower ON employees (LOWER(name));

-- NOT, !=, <> (often match too many rows to benefit from an index)
SELECT * FROM employees WHERE department != 'Engineering';

-- Low-selectivity column (e.g., boolean, gender)
SELECT * FROM employees WHERE is_active = TRUE;  -- 95% of rows are TRUE
-- Index may not help because most of the table is read anyway
```

### Selectivity

The proportion of rows satisfying a condition. A highly selective filter matches relatively few rows, so an index is often more beneficial.

- `WHERE id = 42` → 1 row out of a million = 0.0001% → **highly selective; an index helps**.
- `WHERE gender = 'M'` → 500K out of a million = 50% → **low selectivity; a full scan may be better**.

The optimizer decides based on its cost estimates; there is no universal cutoff like 5–10% of a table.

### Costs of Indexes

Indexes are not free:
1. **Disk space** — indexes occupy additional storage (sometimes a substantial fraction of the table size).
2. **Slower writes** — INSERT/UPDATE/DELETE may need to update indexes too.
3. **More I/O and maintenance** — backups, replication, and vacuuming may involve more work.

**Rule of thumb:** Do not index everything. Index columns that help actual WHERE, JOIN, and ORDER BY patterns, based on query plans and measurements.

### Interview Questions — Topic 16

**Q1: What is a B-tree index, and what is its search complexity?**
A: A B-tree is a balanced search tree that keeps index keys ordered. It supports equality lookups, ranges, suitable prefix patterns, ordering, and MIN/MAX optimization. Its lookup depth grows logarithmically with the number of entries.

**Q2: Why might `WHERE LOWER(name) = 'ana'` not use an index on `name`?**
A: Because the predicate applies a function to the column, an ordinary index on name may not directly support that search. Create an expression index, e.g., `CREATE INDEX idx ON table_name (LOWER(name))`, to index the transformed expression.

**Q3: What are the costs of indexes?**
A: Additional disk space, extra INSERT/UPDATE/DELETE maintenance, and more storage/backup overhead. Indexes should support actual query patterns, not simply be added to every column.

**Q4: When might the database choose NOT to use an index?**
A: When a query reads much of the table, a sequential scan may be cheaper than many random lookups. Very small tables also often favor sequential scans. The decision depends on statistics, storage, data distribution, and the cost model.

---

## TOPIC 17: Index Types and Composite Indexes

### Hash Index

Supports **exact equality (=)** lookups, not range conditions, sorting, or LIKE.

```sql
CREATE INDEX idx_users_email_hash ON users USING HASH (email);
```

Hash indexes may perform well for equality, but:
- They do not support `<`, `>`, `BETWEEN`, or `ORDER BY`.
- In older PostgreSQL versions (before 10) they were not WAL-logged.
- They are uncommon in many workloads because B-tree already handles equality well.

### GIN (Generalized Inverted Index)

For **multiple indexed values inside a column**: arrays, JSONB, and full-text search.

```sql
-- JSONB index
CREATE INDEX idx_events_data ON events USING GIN (data);
-- Now this can use the index:
SELECT * FROM events WHERE data @> '{"plan": "pro"}';

-- Full-text search
CREATE INDEX idx_articles_body ON articles USING GIN (to_tsvector('english', body));
-- Now this can use the index:
SELECT * FROM articles WHERE to_tsvector('english', body) @@ to_tsquery('python & backend');

-- Array index
CREATE INDEX idx_tags ON posts USING GIN (tags);
-- Now this can use the index:
SELECT * FROM posts WHERE tags @> ARRAY['python'];
```

### GiST (Generalized Search Tree)

For geometric/spatial values, range types, and nearest-neighbor searches.

```sql
-- Range index (e.g., for booking systems)
CREATE TABLE bookings (
    id SERIAL PRIMARY KEY,
    room_id INTEGER,
    during TSTZRANGE NOT NULL    -- timestamp range type
);

CREATE INDEX idx_bookings_during ON bookings USING GiST (during);
-- Now this can use the index:
SELECT * FROM bookings WHERE during && tstzrange('2024-01-01', '2024-01-31');

-- PostGIS (geospatial queries)
CREATE INDEX idx_locations_geom ON locations USING GiST (geom);
```

### BRIN (Block Range Index)

For **physically correlated data** (e.g., timestamps in an append-only table). BRIN indexes are exceptionally small.

```sql
-- A logs table where rows are inserted in chronological order
CREATE INDEX idx_logs_created ON logs USING BRIN (created_at);

-- BRIN stores min/max summaries for block ranges
-- Very small (KB instead of MB), but less precise
-- Excellent for time-series, log tables, and append-only tables
```

### Composite (Multicolumn) Index

An index across multiple columns. **Column order is CRITICAL!**

```sql
CREATE INDEX idx_emp_dept_salary ON employees (department, salary);
```

#### Leftmost-Prefix Rule

A composite index (A, B, C) is usually most effective for queries filtering on:
- A ✅
- A, B ✅
- A, B, C ✅
- B alone ⚠️ (the leading column is absent; some plans still exploit the index)
- C alone ⚠️
- B, C without A ⚠️

```sql
-- Index on (department, salary)

-- Typically USES the index:
WHERE department = 'Engineering'                           -- ✅ (A only)
WHERE department = 'Engineering' AND salary > 80000        -- ✅ (A, B)
WHERE department = 'Engineering' ORDER BY salary           -- ✅ (A + sort by B)

-- May NOT use the index efficiently:
WHERE salary > 80000                                       -- ⚠️ (B only; no A predicate)
```

#### Choosing Column Order

1. **Equality first, range second:** Put columns used with `=` before columns used with range predicates (`>`, `<`, `BETWEEN`), considering the full query pattern.

```sql
-- Query: WHERE department = 'Eng' AND salary > 80000
-- Good: (department, salary) — equality before range
-- Less suitable: (salary, department) — range before equality

-- With (department, salary): locate 'Eng', then scan salary > 80000
-- With (salary, department): scan salaries > 80000, then filter department
```

2. **Consider selectivity and workload**, especially when multiple equality filters are present; putting the most selective column first is not a universal rule.

### How Many Indexes Are Too Many?

- OLTP (transactional systems): a handful of indexes per table may be typical, but the right count varies.
- Every index adds some write overhead.
- Having 15 indexes on one table warrants investigation, but is not automatically wrong.
- Regularly check for unused indexes:

```sql
-- PostgreSQL: find unused indexes
SELECT indexrelname, idx_scan
FROM pg_stat_user_indexes
WHERE idx_scan = 0 AND schemaname = 'public';
```

### Interview Questions — Topic 17

**Q1: Explain the leftmost-prefix rule for composite indexes.**
A: An index on (A, B, C) generally supports filters on A, (A, B), or (A, B, C) most directly. Filtering only on B or C is often less efficient because the leading key is not constrained. Modern optimizers may still find some benefit; check EXPLAIN.

**Q2: How would you organize a composite index for `WHERE status = 'active' AND created_at > '2024-01-01'`?**
A: Often `(status, created_at)`: place the equality predicate first and the range predicate second. The database can locate the status group and then scan the relevant date range. Confirm with the actual workload and query plan.

**Q3: When would you use a GIN index?**
A: For JSONB containment searches (`@>`), full-text search (tsvector), and arrays. GIN is an inverted index mapping contained terms/values to rows, ideal when one row contains multiple searchable elements.

---

## TOPIC 18: Covering, Partial, and Expression Indexes

### Covering Index (INCLUDE)

An index containing all columns needed by a query, potentially allowing an **Index-Only Scan** without fetching table data (subject to visibility checks).

```sql
-- A frequently executed query:
SELECT name, salary FROM employees WHERE department = 'Engineering';

-- Ordinary index: look up department, then fetch name and salary from the table
CREATE INDEX idx_dept ON employees (department);

-- Covering index: all needed columns are in the index!
CREATE INDEX idx_dept_covering ON employees (department) INCLUDE (name, salary);
```

INCLUDE columns are stored as payload in leaf entries; they are **not search keys**. They can help avoid reading the table but cannot serve as leading key predicates.

```sql
-- Difference between composite and covering indexes
CREATE INDEX idx_composite ON employees (department, name, salary);
-- Can support WHERE department = ... AND name = ...
-- But uses more index-key storage

CREATE INDEX idx_covering ON employees (department) INCLUDE (name, salary);
-- Supports lookup by WHERE department = ... (not by the included columns)
-- But name and salary can be read from the index
-- A smaller search key because INCLUDE columns are not internal search keys
```

### Partial Index (Filtered Index)

Indexes only **a subset of rows**, producing a smaller, potentially faster index.

```sql
-- Index only active users (many queries filter for active users)
CREATE INDEX idx_active_users ON users (email) WHERE is_active = TRUE;
-- Much smaller than an index across every user!

-- Index only unprocessed orders
CREATE INDEX idx_pending_orders ON orders (created_at) WHERE status = 'pending';
-- Once an order is processed, it no longer qualifies for the partial index

-- Soft delete: index only non-deleted rows
CREATE INDEX idx_active_employees ON employees (name) WHERE deleted_at IS NULL;
```

A partial index can be used when the planner can establish that the query's WHERE predicate **implies the index predicate**:

```sql
-- Index predicate: WHERE is_active = TRUE
SELECT * FROM users WHERE email = 'x' AND is_active = TRUE;   -- ✅ predicate matches
SELECT * FROM users WHERE email = 'x' AND is_active = FALSE;  -- ❌ predicate does not match
SELECT * FROM users WHERE email = 'x';                         -- ❌ predicate not guaranteed
```

### Expression Index (Index on an Expression)

Indexes the result of an expression/function:

```sql
-- Case-insensitive lookup
CREATE INDEX idx_lower_email ON users (LOWER(email));
-- Now this can use the index:
SELECT * FROM users WHERE LOWER(email) = 'ana@mail.com';

-- Extracting a date from a timestamp
CREATE INDEX idx_order_date ON orders (DATE(created_at));
-- Now this can use the index:
SELECT * FROM orders WHERE DATE(created_at) = '2024-01-15';

-- Extracting a value from JSONB
CREATE INDEX idx_data_plan ON events ((data->>'plan'));
-- Now this can use the index:
SELECT * FROM events WHERE data->>'plan' = 'pro';
```

### Interview Questions — Topic 18

**Q1: What is a covering index, and why is it fast?**
A: A covering index contains all columns required by a query, either as key columns or INCLUDE columns. It may support an Index-Only Scan and avoid many table accesses. PostgreSQL's visibility information still affects whether heap lookups are needed.

**Q2: When would you use a partial index?**
A: When important queries repeatedly filter on a small subset of rows. For instance, if 99% of records are completed, an index with `WHERE status = 'pending'` can be much smaller. Partial indexes are also useful for soft deletes (`WHERE deleted_at IS NULL`).

---

## TOPIC 19: EXPLAIN / EXPLAIN ANALYZE

### EXPLAIN — What the Database Plans to Do

```sql
EXPLAIN SELECT name, salary FROM employees WHERE department = 'Engineering';
```

```
Seq Scan on employees  (cost=0.00..25.00 rows=10 width=36)
  Filter: (department = 'Engineering'::text)
```

### EXPLAIN ANALYZE — What Actually Happened

```sql
EXPLAIN ANALYZE SELECT name, salary FROM employees WHERE department = 'Engineering';
```

```
Seq Scan on employees  (cost=0.00..25.00 rows=10 width=36)
                        (actual time=0.015..0.089 rows=15 loops=1)
  Filter: (department = 'Engineering'::text)
  Rows Removed by Filter: 85
Planning Time: 0.082 ms
Execution Time: 0.112 ms
```

**EXPLAIN** shows the plan without executing the query. **EXPLAIN ANALYZE** executes it and reports actual measurements. **CAUTION:** EXPLAIN ANALYZE on INSERT/UPDATE/DELETE REALLY MODIFIES DATA! Run such tests inside a transaction and roll them back when appropriate:

```sql
BEGIN;
EXPLAIN ANALYZE UPDATE employees SET salary = salary * 1.1 WHERE department = 'Engineering';
ROLLBACK;
```

### Reading a Query Plan

#### Scan types (not a universal fastest-to-slowest ranking):

| Scan type | Description | Typical use |
|----------|------|--------|
| Index Only Scan | mostly reads index entries | when index covers the query and visibility permits |
| Index Scan | index + potential heap access | selective lookups |
| Bitmap Index Scan | build bitmap, then fetch heap pages | a moderate number of matching rows |
| Seq Scan | scans the whole table | small tables or queries returning many rows |

#### Key Metrics:

```
                   predvidjeno    stvarno
                   estimated      actual
rows=10            estimated row count  → actual rows=15 (difference!)
width=36           estimated average row width in bytes
actual time=0.015..0.089   time in milliseconds (startup..total)
loops=1            number of times this node was executed
```

**If estimated `rows` and `actual rows` differ dramatically**, statistics or cardinality assumptions may be wrong. Consider:

```sql
ANALYZE employees;   -- update table statistics
```

#### JOIN Algorithms:

```
Nested Loop    - useful with small row counts and efficient inner lookups
Hash Join      - builds a hash table on one input; useful for larger joins
Merge Join     - both inputs are sorted on the join keys
```

### Practical Optimization Example

```sql
-- Slow query (Sequential Scan):
EXPLAIN ANALYZE
SELECT e.name, d.name AS dept
FROM employees e
JOIN departments d ON e.department_id = d.id
WHERE e.salary > 80000 AND d.location = 'Belgrade';

-- Plan before optimization:
-- Hash Join (cost=100.00)
--   -> Seq Scan on employees (rows=1000)
--        Filter: salary > 80000, Rows Removed: 9000
--   -> Seq Scan on departments (rows=50)

-- Add indexes:
CREATE INDEX idx_emp_salary ON employees (salary) WHERE salary > 80000;
CREATE INDEX idx_dept_location ON departments (location);

-- Plan after optimization:
-- Nested Loop (cost=15.00)
--   -> Index Scan on departments using idx_dept_location (rows=5)
--   -> Index Scan on employees using idx_emp_dept (rows=10)
```

### Useful EXPLAIN Options

```sql
-- More detailed output
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM employees WHERE department = 'Engineering';

-- BUFFERS shows buffer hits, reads, and other I/O statistics
-- Buffers: shared hit=5 read=12
-- hit = found in PostgreSQL's buffer cache; read = had to be read into buffers

-- JSON output format (for programmatic parsing)
EXPLAIN (ANALYZE, FORMAT JSON) SELECT ...;
```

### Interview Questions — Topic 19

**Q1: What is the difference between EXPLAIN and EXPLAIN ANALYZE?**
A: EXPLAIN displays the planned execution strategy without running the query. EXPLAIN ANALYZE runs it and reports actual timings, row counts, and optional I/O statistics. For data-changing queries, use a transaction and ROLLBACK to avoid keeping test changes.

**Q2: What does a large difference between estimated rows and actual rows mean?**
A: The optimizer's cardinality estimate is wrong. Possible causes include outdated table statistics or correlations not captured by basic statistics. Run `ANALYZE table_name` where appropriate, check auto-analyze, and inspect statistics and predicates.

**Q3: Which scan type is best, and why is it not always used?**
A: There is no universally best scan. An Index-Only Scan may be excellent for selective, covered queries, but requires a suitable index and may still check heap visibility. A Seq Scan can be faster when much of the table must be read, or the table is small.

---

## TOPIC 20: N+1 Problems, Slow Query Optimization, Anti-patterns

### N+1 Problem

One of the most common backend performance issues. It occurs when a query loads N rows and then the application runs N additional queries, one per row.

```python
# N+1 in Python (pseudocode):
orders = db.query("SELECT * FROM orders LIMIT 100")      # 1 query

for order in orders:
    customer = db.query(                                    # 100 queries!
        "SELECT * FROM customers WHERE id = %s", order.customer_id
    )
    print(f"{customer.name}: {order.total}")

# TOTAL: 1 + 100 = 101 queries instead of 1!
```

**Solution: JOIN or IN**

```python
# With a JOIN: one query
results = db.query("""
    SELECT o.*, c.name AS customer_name
    FROM orders o
    JOIN customers c ON o.customer_id = c.id
    LIMIT 100
""")

# With IN (batch): two queries
orders = db.query("SELECT * FROM orders LIMIT 100")
customer_ids = [o.customer_id for o in orders]
customers = db.query(
    "SELECT * FROM customers WHERE id = ANY(%s)", [customer_ids]
)
```

In ORMs (SQLAlchemy):

```python
# N+1 (lazy loading, common default):
orders = session.query(Order).limit(100).all()
for order in orders:
    print(order.customer.name)   # each attribute access can trigger a new query!

# Solution: eager loading
from sqlalchemy.orm import joinedload
orders = session.query(Order).options(joinedload(Order.customer)).limit(100).all()
```

### SQL Anti-patterns

#### 1. SELECT *

```sql
-- Bad:
SELECT * FROM employees WHERE id = 42;

-- Good:
SELECT name, email, salary FROM employees WHERE id = 42;
```

#### 2. Function Applied to an Indexed Column

```sql
-- Bad (prevents regular index use):
SELECT * FROM orders WHERE YEAR(created_at) = 2024;

-- Good (index-friendly):
SELECT * FROM orders
WHERE created_at >= '2024-01-01' AND created_at < '2025-01-01';
```

#### 3. OR Across Different Columns

```sql
-- Bad (may be harder to optimize):
SELECT * FROM employees WHERE department = 'Eng' OR salary > 100000;

-- Alternative (UNION ALL; each branch may use its own index):
SELECT * FROM employees WHERE department = 'Eng'
UNION ALL
SELECT * FROM employees WHERE salary > 100000 AND department != 'Eng';
```

#### 4. NOT IN with a Subquery (NULL Gotcha)

Already covered in Topic 4 — consider NOT EXISTS.

#### 5. Pagination with a Large OFFSET

Already covered in Topic 1 — use keyset pagination.

#### 6. COUNT(*) for Existence Checks

```sql
-- Bad:
SELECT COUNT(*) FROM orders WHERE customer_id = 42;
-- Counts ALL orders (potentially millions!)

-- Better: stop after the first match
SELECT EXISTS (SELECT 1 FROM orders WHERE customer_id = 42);
-- Or:
SELECT 1 FROM orders WHERE customer_id = 42 LIMIT 1;
```

#### 7. Too Few / Too Many Indexes

- Too few: slow SELECT queries.
- Too many: slower INSERT/UPDATE/DELETE, more storage, and maintenance complexity.

### Slow Query Checklist

1. **EXPLAIN ANALYZE** — inspect the plan.
2. **Missing index?** — add a targeted index when justified.
3. **Seq Scan on a large table?** — investigate whether an index would help.
4. **Row estimate vs actual?** — review statistics and ANALYZE.
5. **N+1?** — check logs for repeated queries.
6. **SELECT *?** — return only required columns.
7. **Function on a column?** — rewrite the predicate or add an expression index.
8. **Large OFFSET?** — consider keyset pagination.
9. **Unnecessary ORDER BY?** — remove it when ordering is not needed.

### Interview Questions — Topic 20

**Q1: What is the N+1 problem, and how do you fix it?**
A: N+1 occurs when an application fetches N records and then issues a separate query for each one (e.g., looking up each order's customer). Fix it with a JOIN or batched IN/ANY queries. In ORMs, use eager loading (joinedload/selectinload in SQLAlchemy) instead of inappropriate lazy loading.

**Q2: How would you optimize a slow SQL query?**
A: (1) Inspect EXPLAIN ANALYZE; (2) check for missing indexes; (3) look for functions that prevent efficient index use; (4) return only necessary columns; (5) check large OFFSET pagination; (6) update statistics if needed; and (7) consider covering indexes when heap I/O is the bottleneck.

**Q3: Why might `WHERE YEAR(created_at) = 2024` fail to use an index on created_at?**
A: Applying a function to the column can prevent a regular B-tree index from being used efficiently. Rewrite it as a range: `WHERE created_at >= '2024-01-01' AND created_at < '2025-01-01'`. (YEAR() is not standard PostgreSQL syntax.)

---

# PART 5: TRANSACTIONS AND CONCURRENCY

---

## TOPIC 21: ACID Properties

### A — Atomicity

A transaction is **all or nothing**: either all its operations succeed, or none of its changes are kept.

```sql
BEGIN;
    UPDATE accounts SET balance = balance - 500 WHERE id = 1;  -- debit 500
    UPDATE accounts SET balance = balance + 500 WHERE id = 2;  -- credit 500
COMMIT;

-- If either UPDATE fails (error, crash, or power failure),
-- NEITHER transaction change is committed; the original balances remain
```

Without atomicity, money could be debited from one account but never credited to another.

### C — Consistency

A transaction moves the database from one **valid state to another valid state**. Database constraints (PK, FK, CHECK, UNIQUE) must remain satisfied.

```sql
-- CHECK constraint: balance >= 0
BEGIN;
    UPDATE accounts SET balance = balance - 500 WHERE id = 1;
    -- If balance becomes negative, the CHECK constraint fails
    -- The entire transaction is rolled back
COMMIT;
```

### I — Isolation

Concurrent transactions are isolated according to the selected isolation level. Under the strongest level, their effects are equivalent to **some serial order**. One transaction should not see another's uncommitted changes.

```sql
-- Transaction A:                    -- Transaction B:
BEGIN;                                BEGIN;
UPDATE accounts SET balance =         SELECT balance FROM accounts
  balance - 500 WHERE id = 1;          WHERE id = 1;
-- What does B see? It depends        -- Old state or new state?
-- on the isolation level!            -- Depends on isolation level!
COMMIT;                               COMMIT;
```

### D — Durability

Once COMMIT succeeds, changes are **durable** even if the server crashes (subject to durability configuration and storage guarantees).

Implementation: **Write-Ahead Log (WAL)**. The database logs changes before relevant data pages are written. After a crash, recovery replays the needed log records.

### Practical Example

```sql
-- Money transfer (classic atomicity example):
BEGIN;

    -- Check whether the sender has enough funds
    SELECT balance FROM accounts WHERE id = 1 FOR UPDATE;  -- lock the row

    -- If there are enough funds:
    UPDATE accounts SET balance = balance - 500 WHERE id = 1;
    UPDATE accounts SET balance = balance + 500 WHERE id = 2;

    -- Record the transfer
    INSERT INTO transfers (from_id, to_id, amount, created_at)
    VALUES (1, 2, 500, NOW());

COMMIT;

-- If anything fails:
ROLLBACK;  -- undo all changes
```

### SAVEPOINT

```sql
BEGIN;
    INSERT INTO orders (customer_id, total) VALUES (1, 100);

    SAVEPOINT sp1;

    INSERT INTO order_items (order_id, product_id) VALUES (1, 999);
    -- Error! Product 999 does not exist (foreign-key violation)

    ROLLBACK TO SAVEPOINT sp1;  -- undo only the operations after sp1
    -- The orders INSERT is still part of the transaction!

    INSERT INTO order_items (order_id, product_id) VALUES (1, 1);  -- valid
COMMIT;
```

### Interview Questions — Topic 21

**Q1: Explain the ACID properties.**
A: Atomicity — all or nothing. Consistency — transactions maintain the database's integrity rules. Isolation — concurrent operations are separated according to the isolation level. Durability — successfully committed changes survive crashes, typically supported by WAL and durable storage.

**Q2: How does a database guarantee durability?**
A: It uses a Write-Ahead Log (WAL): log records are written before modified data pages are persisted, and normally flushed according to durability settings before COMMIT completes. After a crash, the database can replay WAL to recover committed changes.

**Q3: What is a SAVEPOINT, and when would you use it?**
A: A SAVEPOINT marks a point within a transaction. `ROLLBACK TO SAVEPOINT` undoes work performed after it without rolling back the whole transaction. Useful when processing batches where some records can fail but earlier successful work should remain.

---

## TOPIC 22: Isolation Levels

### Concurrency Problems (Anomalies)

#### Dirty Read
A transaction reads data another transaction **wrote but has not committed**. If the writer rolls back, the reader saw data that never became committed.

#### Non-repeatable Read
A transaction reads the same row twice and sees **different values** because another transaction updated and committed it in between.

#### Phantom Read
A transaction repeats a query and sees **a different set of rows** because another transaction inserted or deleted matching rows.

### The Four Isolation Levels

| Level | Dirty Read | Non-Repeatable Read | Phantom Read |
|-------|-----------|-------------------|-------------|
| Read Uncommitted | possible | possible | possible |
| **Read Committed** | **prevented** | possible | possible |
| Repeatable Read | prevented | **prevented** | possible* |
| Serializable | prevented | prevented | **prevented** |

*PostgreSQL also prevents phantom reads at Repeatable Read through its MVCC implementation.

### Read Committed (PostgreSQL Default)

Each statement sees a snapshot of data committed **before that statement began**.

```sql
-- Transaction A:                    -- Transaction B:
BEGIN;                                BEGIN;
SELECT salary FROM emp WHERE id=1;    
-- sees 80000                         UPDATE emp SET salary=90000 WHERE id=1;
                                      COMMIT;
SELECT salary FROM emp WHERE id=1;    
-- sees 90000! (non-repeatable read)
COMMIT;
```

### Repeatable Read

A transaction sees a stable snapshot of committed data (established at its first qualifying statement in PostgreSQL), rather than a new snapshot for every statement.

```sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
BEGIN;                                
SELECT salary FROM emp WHERE id=1;    -- B: UPDATE salary=90000; COMMIT;
-- sees 80000
SELECT salary FROM emp WHERE id=1;    
-- STILL sees 80000! (same transaction snapshot)

-- But if A tries to UPDATE the same row B changed:
UPDATE emp SET salary = salary + 5000 WHERE id = 1;
-- ERROR: could not serialize access due to concurrent update
-- Must ROLLBACK and retry!
COMMIT;
```

### Serializable

The strongest isolation level. The database ensures that concurrent transactions have an effect **equivalent to some serial execution** (transactions may have to be retried).

```sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
BEGIN;
    SELECT SUM(amount) FROM transactions WHERE account_id = 1;
    INSERT INTO transactions (account_id, amount) VALUES (1, -100);
COMMIT;
-- If a concurrent transaction would violate serializability,
-- one transaction receives a serialization error and must retry
```

### Which Level Should You Use?

- **Read Committed (default):** Suitable for many OLTP applications; a practical balance of isolation and concurrency.
- **Repeatable Read:** Useful when you need a consistent snapshot across a transaction (reports, batch processing).
- **Serializable:** For workflows with complex cross-row invariants that require serializable behavior. Handle serialization failures with retries.

### Setting the Isolation Level

```sql
-- For one transaction:
BEGIN ISOLATION LEVEL REPEATABLE READ;
-- Or:
BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

-- For the entire session:
SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL SERIALIZABLE;

-- Check the current level:
SHOW transaction_isolation;
```

### Interview Questions — Topic 22

**Q1: Explain the difference between Read Committed and Repeatable Read.**
A: Read Committed uses a new snapshot for each statement, so two SELECTs in the same transaction can see newly committed changes. Repeatable Read uses a stable snapshot across the transaction, though it may raise an error if concurrent updates conflict.

**Q2: What is a phantom read?**
A: Repeating the same predicate query in one transaction yields a different set of matching rows — for example, `SELECT COUNT(*) WHERE salary > 80000` returns 10 and then 11 after another transaction inserts a matching employee. PostgreSQL's Repeatable Read prevents this, and Serializable also rules it out.

**Q3: When would you use Serializable isolation?**
A: When correctness depends on enforcing complex invariants across concurrent transactions (e.g., preventing write skew). The tradeoff is more overhead and possible serialization failures, which the application must retry.

---

## TOPIC 23: Locking

### Pessimistic Locking

Lock the row **before** changing it. Other transactions that need a conflicting lock must wait.

```sql
BEGIN;
    -- Lock the row (others cannot make conflicting changes until we finish)
    SELECT * FROM accounts WHERE id = 1 FOR UPDATE;

    -- Now safely update it:
    UPDATE accounts SET balance = balance - 500 WHERE id = 1;
COMMIT;
-- Only then can conflicting operations proceed
```

#### Lock Types:

```sql
-- FOR UPDATE: exclusive row lock for conflicting writes/locks
SELECT * FROM accounts WHERE id = 1 FOR UPDATE;

-- FOR SHARE: shared row lock, allowing compatible readers
SELECT * FROM accounts WHERE id = 1 FOR SHARE;

-- SKIP LOCKED: skip locked rows (ideal for job queues!)
SELECT * FROM tasks WHERE status = 'pending'
ORDER BY created_at
LIMIT 1
FOR UPDATE SKIP LOCKED;

-- NOWAIT: raise an error immediately instead of waiting
SELECT * FROM accounts WHERE id = 1 FOR UPDATE NOWAIT;
```

#### Queue Pattern with SKIP LOCKED:

```sql
-- Worker 1 and Worker 2 process jobs concurrently:
BEGIN;
    SELECT id, payload FROM job_queue
    WHERE status = 'pending'
    ORDER BY created_at
    LIMIT 1
    FOR UPDATE SKIP LOCKED;     -- each worker claims a DIFFERENT available job!

    -- Process the job...
    UPDATE job_queue SET status = 'done' WHERE id = ...;
COMMIT;
```

### Optimistic Locking (Without Taking a Long-lived Lock)

Do not lock the row in advance; on UPDATE, verify that nothing changed since you read it.

```sql
-- Add a version column:
ALTER TABLE products ADD COLUMN version INTEGER DEFAULT 1;

-- Read:
SELECT id, name, price, version FROM products WHERE id = 42;
-- Obtained: price=100, version=3

-- Update with a version check:
UPDATE products
SET price = 110, version = version + 1
WHERE id = 42 AND version = 3;    -- check that the version has not changed!

-- If another transaction already changed it (version is now 4),
-- UPDATE affects no rows (0 rows affected)
-- The application detects this and retries
```

**Alternative Without a Version Column — Use updated_at:**

```sql
UPDATE products
SET price = 110, updated_at = NOW()
WHERE id = 42 AND updated_at = '2024-01-15 14:30:00';
```

### Pessimistic vs Optimistic

| Aspect | Pessimistic | Optimistic |
|--------|------------|-----------|
| Mechanism | lock row (FOR UPDATE) | check version on UPDATE |
| Conflict | wait (or NOWAIT/SKIP) | detect conflict and retry |
| Better for | frequent conflicts | rare conflicts |
| Performance | may block others | avoids waiting upfront, but retries cost time |
| Complexity | often simpler | application retry logic required |

### Interview Questions — Topic 23

**Q1: Explain the difference between pessimistic and optimistic locking.**
A: Pessimistic locking acquires a row lock with FOR UPDATE before a change, causing conflicting transactions to wait. Useful when conflicts are frequent. Optimistic locking does not lock in advance; UPDATE checks a version/timestamp and retries if it changed. It is useful when collisions are rare.

**Q2: What is SKIP LOCKED, and when would you use it?**
A: `SKIP LOCKED` with SELECT FOR UPDATE skips rows already locked by other workers rather than waiting. It is ideal for job queues: multiple workers can claim **different** available jobs concurrently.

---

## TOPIC 24: Deadlocks

### What Is a Deadlock?

Two or more transactions wait for one another to release locks, so **none can proceed**.

```sql
-- Transaction A:                    -- Transaction B:
BEGIN;                                BEGIN;
UPDATE accounts SET balance=100       UPDATE accounts SET balance=200
  WHERE id = 1;                         WHERE id = 2;
-- A holds lock on id=1               -- B holds lock on id=2

UPDATE accounts SET balance=200       UPDATE accounts SET balance=100
  WHERE id = 2;                         WHERE id = 1;
-- A waits for id=2 (held by B)       -- B waits for id=1 (held by A)
-- DEADLOCK! Neither transaction can proceed
```

### Detection and Resolution

PostgreSQL automatically detects deadlocks (after a wait exceeding `deadlock_timeout`, default around one second) and **aborts one transaction**:

```
ERROR: deadlock detected
DETAIL: Process 1234 waits for ShareLock on transaction 5678;
        blocked by process 5678.
Process 5678 waits for ShareLock on transaction 1234;
        blocked by process 1234.
```

### Prevention

#### 1. Always Acquire Locks in the Same Order

```sql
-- ALWAYS acquire locks in increasing ID order:
-- Transaction A:        -- Transaction B:
UPDATE ... WHERE id=1;   UPDATE ... WHERE id=1;  -- waits (OK: no deadlock)
UPDATE ... WHERE id=2;   UPDATE ... WHERE id=2;  -- after A finishes
```

#### 2. Keep Transactions Short

The shorter a transaction, the less opportunity for deadlocks. Do not keep transactions open while waiting for user input or remote API calls.

#### 3. Retry Logic in the Application

```python
import time
from psycopg2 import errors

MAX_RETRIES = 3

for attempt in range(MAX_RETRIES):
    try:
        with conn.cursor() as cur:
            cur.execute("BEGIN")
            cur.execute("UPDATE accounts SET balance = balance - 500 WHERE id = 1")
            cur.execute("UPDATE accounts SET balance = balance + 500 WHERE id = 2")
            cur.execute("COMMIT")
        break
    except errors.DeadlockDetected:
        conn.rollback()
        if attempt < MAX_RETRIES - 1:
            time.sleep(0.1 * (2 ** attempt))  # exponential backoff
        else:
            raise
```

### Interview Questions — Topic 24

**Q1: What is a deadlock, and how can you prevent it?**
A: A deadlock occurs when two or more transactions wait for locks held by one another, preventing progress. Prevent it by (1) locking resources in a consistent order (e.g., by ID), (2) keeping transactions short, and (3) adding retry logic for deadlock-related transaction failures. PostgreSQL detects deadlocks and aborts one participating transaction.

---

## TOPIC 25: MVCC (Multi-Version Concurrency Control)

### What Is MVCC?

MVCC is a mechanism PostgreSQL uses so that **ordinary readers do not block writers, and writers do not block ordinary readers**. A transaction sees a snapshot of the database, with snapshot timing depending on the isolation level.

### How It Works Internally

Every PostgreSQL row version has hidden system columns:
- **xmin** — transaction ID associated with creating that row version.
- **xmax** — transaction ID associated with deleting/updating/locking the row version (special states are possible).

```sql
-- Inspect hidden system columns:
SELECT xmin, xmax, * FROM employees LIMIT 5;
```

#### UPDATE Creates a New Row Version

When you run UPDATE, PostgreSQL:
1. Marks the old row version as superseded.
2. Creates a NEW version with the updated values and a new xmin.
3. Both versions may coexist on disk until cleanup.

```
-- Before UPDATE (salary = 80000):
xmin=100, xmax=0, name='Ana', salary=80000   -- active row version

-- After UPDATE salary = 90000 (transaction 150):
xmin=100, xmax=150, name='Ana', salary=80000  -- dead/obsolete row version
xmin=150, xmax=0,   name='Ana', salary=90000  -- current row version
```

#### Visibility Rules

A transaction sees a row version according to snapshot visibility rules, including:
- Whether its `xmin` is visible to the snapshot.
- Whether `xmax` makes the version invisible to the snapshot (and whether the relevant transaction committed).

### Why Does MVCC Matter?

1. **Ordinary readers do not block writers** — a reader can observe an older visible row version while a writer creates a new one.
2. **Ordinary writers do not block readers** — readers use snapshots instead of waiting for most row-level write locks.
3. This is one reason PostgreSQL handles concurrent read/write workloads well.

### VACUUM — Cleaning Up Dead Row Versions

Because updates create new row versions, old versions can accumulate (bloat). **VACUUM** reclaims space occupied by dead tuples when they are no longer needed.

```sql
-- Manual VACUUM
VACUUM employees;

-- VACUUM FULL (locks and compacts the table; use rarely!)
VACUUM FULL employees;

-- VACUUM with ANALYZE (also updates statistics)
VACUUM ANALYZE employees;
```

**Autovacuum** schedules VACUUM automatically, controlled through configuration. Usually you should tune it rather than disable it.

### Interview Questions — Topic 25

**Q1: Explain how MVCC works in PostgreSQL.**
A: Row versions contain metadata such as xmin and xmax. An UPDATE creates a new row version. Transactions read versions visible to their snapshot, allowing readers to see previously committed data while writers produce newer versions. This reduces reader–writer blocking.

**Q2: Why is VACUUM important?**
A: MVCC leaves dead row versions behind after updates and deletes. VACUUM makes their space reusable once no active snapshot needs them. Without effective vacuuming, tables can bloat, queries slow down, and transaction-ID wraparound becomes a risk. Autovacuum handles routine cleanup automatically.

**Q3: What is table bloat, and how do you detect it?**
A: Bloat is storage occupied by dead or otherwise inefficiently packed tuples. Investigate with tools such as the `pgstattuple` extension and table-size trends. Routine VACUUM reclaims reusable space; VACUUM FULL rewrites and compacts the table but requires an exclusive lock. Proper autovacuum tuning helps prevent excessive bloat.

---

# PART 6: POSTGRESQL-SPECIFIC FEATURES

---

## TOPIC 26: PostgreSQL vs MySQL

### Key Differences

| Aspect | PostgreSQL | MySQL |
|--------|-----------|-------|
| MVCC | MVCC using row versions | depends on storage engine (InnoDB supports MVCC) |
| SQL standards | generally strict | behavior depends on SQL mode; can be more permissive |
| JSONB | rich JSONB support, GIN indexes | JSON data type with indexing options |
| Full-text search | built-in (tsvector) | built-in full-text indexing |
| Window functions | supported | supported since MySQL 8.0 |
| CTE | supported, including recursive CTEs | supported since MySQL 8.0 |
| Materialized views | built-in | no equivalent built-in native materialized view |
| UPSERT | ON CONFLICT | ON DUPLICATE KEY UPDATE |
| Data types | rich (JSONB, arrays, ranges, inet, UUID, etc.) | different, narrower set of built-in types |
| Replication | physical streaming, logical | binary-log-based and other replication options |
| Default isolation | Read Committed | Repeatable Read (InnoDB) |
| Write performance | workload dependent | workload dependent |
| Read performance | strong; workload dependent | strong; workload dependent |
| License | PostgreSQL license, permissive open source | GPL with commercial options |
| Stewardship | open-source community | Oracle |

### Why Backend Developers Choose PostgreSQL

1. **Strictness** — helps catch incorrect SQL instead of silently permitting ambiguous behavior.
2. **JSONB** — allows relational and document-like data in the same database.
3. **Advanced types** — native arrays, ranges, inet, cidr, and UUIDs.
4. **Extensions** — PostGIS, pg_trgm, TimescaleDB, pgvector, etc.
5. **Permissive open-source license** — no mandatory enterprise edition for core functionality.

### MySQL Differences Worth Knowing

```sql
-- MySQL: GROUP BY without grouping all selected nonaggregate columns (depends on SQL mode)
SELECT department, name, MAX(salary)
FROM employees
GROUP BY department;
-- Permissive MySQL settings may return an arbitrary 'name' for each group: BAD!
-- PostgreSQL: ERROR (usually the correct strict behavior)

-- MySQL: a different LIMIT/OFFSET syntax is supported
SELECT * FROM employees LIMIT 10, 5;   -- MySQL: five rows starting at offset 10
SELECT * FROM employees LIMIT 5 OFFSET 10;  -- standard form (PG and MySQL)

-- MySQL AUTO_INCREMENT vs PostgreSQL SERIAL
-- MySQL:
CREATE TABLE users (id INT AUTO_INCREMENT PRIMARY KEY);
-- PostgreSQL:
CREATE TABLE users (id SERIAL PRIMARY KEY);
```

### Interview Questions — Topic 26

**Q1: Why might you choose PostgreSQL instead of MySQL for a new project?**
A: Reasons include PostgreSQL's strong SQL feature set, JSONB and GIN indexes, rich built-in data types, materialized views, permissive license, and powerful extensions such as PostGIS. I might choose MySQL for an existing MySQL-based system or where its ecosystem and team expertise are decisive. The best choice depends on the workload.

---

## TOPIC 27: JSONB, Arrays, Composite Types

### JSONB

JSONB stores parsed JSON in a binary representation, allowing efficient processing and indexing.

```sql
-- JSON vs JSONB:
-- JSON: stores text and preserves whitespace, duplicate keys, and key order
-- JSONB: stores parsed binary JSON, supports indexes, does not preserve duplicate keys

CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    type TEXT NOT NULL,
    data JSONB NOT NULL DEFAULT '{}'
);

INSERT INTO events (type, data) VALUES
('user_signup', '{"name": "Ana", "email": "ana@mail.com", "tags": ["premium", "early"]}'),
('purchase', '{"product": "Laptop", "amount": 999.99, "currency": "USD"}');
```

#### JSONB Operators

```sql
-- -> returns a JSON element (as JSON)
SELECT data->'name' FROM events;           -- "Ana" (including JSON quotes)

-- ->> returns TEXT
SELECT data->>'name' FROM events;          -- Ana (without quotes)

-- #> path navigation
SELECT data#>'{tags,0}' FROM events;       -- "premium"

-- @> containment: does JSON contain the specified structure?
SELECT * FROM events WHERE data @> '{"name": "Ana"}';

-- ? checks whether a key exists
SELECT * FROM events WHERE data ? 'email';

-- ?| checks whether any listed key exists
SELECT * FROM events WHERE data ?| array['email', 'phone'];

-- ?& checks whether ALL listed keys exist
SELECT * FROM events WHERE data ?& array['name', 'email'];
```

#### Updating JSONB

```sql
-- jsonb_set: set a value at a specified path
UPDATE events SET data = jsonb_set(data, '{city}', '"Belgrade"')
WHERE id = 1;

-- || merge two JSONB objects
UPDATE events SET data = data || '{"verified": true}'
WHERE id = 1;

-- - remove a key
UPDATE events SET data = data - 'temporary_field'
WHERE id = 1;
```

#### JSONB Indexes

```sql
-- GIN index for @>, ?, ?|, ?&
CREATE INDEX idx_events_data ON events USING GIN (data);

-- GIN with jsonb_path_ops (smaller and faster for @>, but not for ?)
CREATE INDEX idx_events_data ON events USING GIN (data jsonb_path_ops);

-- Index on a specific key
CREATE INDEX idx_events_email ON events ((data->>'email'));
```

### Arrays

```sql
CREATE TABLE posts (
    id SERIAL PRIMARY KEY,
    title TEXT,
    tags TEXT[] NOT NULL DEFAULT '{}'   -- array of strings
);

INSERT INTO posts (title, tags) VALUES
('Python Tips', ARRAY['python', 'backend', 'tips']),
('SQL Deep Dive', '{"sql", "database", "postgresql"}');  -- alternative syntax

-- Searches
SELECT * FROM posts WHERE 'python' = ANY(tags);        -- contains the element
SELECT * FROM posts WHERE tags @> ARRAY['python'];     -- contains all listed elements
SELECT * FROM posts WHERE tags && ARRAY['python', 'sql'];  -- overlaps (at least one)

-- GIN index for arrays
CREATE INDEX idx_posts_tags ON posts USING GIN (tags);
```

### When to Use JSONB vs Relational Tables

| Use JSONB when... | Use relational tables when... |
|---------------------|----------------------|
| The schema is flexible/unknown | The schema is stable |
| You rarely filter on the nested data | You frequently search/filter the data |
| Data is auxiliary (metadata, config) | Data is core (customers, orders) |
| You do not need joins on nested data | You need joins |
| Foreign-key relationships are not required for nested elements | You need referential integrity |

### Interview Questions — Topic 27

**Q1: When would you use a JSONB column instead of relational tables?**
A: For flexible or semi-structured data where fields change frequently (event metadata, user preferences, form submissions). I would avoid it as a blanket replacement for core relational data requiring foreign keys and joins. JSONB is excellent for flexible portions of a relational schema.

**Q2: What is the difference between JSON and JSONB in PostgreSQL?**
A: JSON stores the original JSON text, preserving whitespace, key order, and duplicate keys in its input representation. JSONB parses it into a binary format, supports efficient indexing (e.g., GIN), removes duplicate keys, and does not preserve whitespace or original key order. JSONB is often the default choice for querying JSON.

---

# PART 7: PYTHON + DATABASES (OVERVIEW)

---

## TOPIC 31: psycopg2/psycopg3 (Overview)

### Connecting and Basic Queries

```python
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    dbname="mydb",
    user="postgres",
    password="secret"
)

with conn.cursor() as cur:
    cur.execute("SELECT id, name, salary FROM employees WHERE department = %s", ('Engineering',))
    rows = cur.fetchall()
    for row in rows:
        print(row)  # (1, 'Ana', 85000)

conn.close()
```

### SQL Injection — CRITICAL

```python
# DANGEROUS — never do this:
cur.execute(f"SELECT * FROM users WHERE email = '{user_input}'")
# user_input = "'; DROP TABLE users; --"

# SAFE — always use parameterized queries:
cur.execute("SELECT * FROM users WHERE email = %s", (user_input,))
```

**Rule:** NEVER use string formatting (f-strings, %, .format()) to insert untrusted values into SQL. ALWAYS use parameterized queries (`%s` placeholders with psycopg).

### Context Managers and Transactions

```python
# psycopg2: autocommit is False by default
# Each execute happens in a transaction; COMMIT or ROLLBACK explicitly

with psycopg2.connect(...) as conn:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO users (name) VALUES (%s)", ("Ana",))
        cur.execute("INSERT INTO users (name) VALUES (%s)", ("Marko",))
    conn.commit()  # COMMIT both operations

# psycopg3 (more modern):
import psycopg
with psycopg.connect(...) as conn:
    with conn.transaction():  # automatic COMMIT/ROLLBACK on exit
        conn.execute("INSERT INTO users (name) VALUES (%s)", ("Ana",))
```

### Interview Questions — Topic 31

**Q1: What is SQL injection, and how do you prevent it?**
A: SQL injection occurs when an attacker introduces malicious SQL through user-supplied input. Prevention: use parameterized queries (`%s` placeholders in psycopg), not string interpolation for values. The driver handles parameters as data rather than SQL syntax.

---

## TOPIC 28: VACUUM, Autovacuum, Bloat

### Why Does VACUUM Exist?

As described in Topic 25 (MVCC), PostgreSQL does not immediately erase old row versions. After UPDATE or DELETE, obsolete versions may remain on disk as "dead tuples." VACUUM **reclaims their space for reuse**.

### Three Problems Without VACUUM

1. **Table bloat** — dead tuples accumulate and tables grow unnecessarily.
2. **Index bloat** — indexes may contain obsolete references, increasing storage and overhead.
3. **Transaction ID wraparound** — PostgreSQL uses transaction identifiers that must be managed to avoid wraparound issues. VACUUM freezes sufficiently old tuples to maintain correct visibility and prevent shutdown protections from being triggered.

### VACUUM Types

#### VACUUM (Regular/Lazy)

```sql
-- Marks dead tuple space as available for REUSE
-- Usually does NOT return space to the operating system!
-- Allows normal reads and writes while VACUUM runs
VACUUM employees;

-- With VERBOSE for detailed output
VACUUM VERBOSE employees;
-- INFO: "employees": removed 1500 dead row versions in 30 pages
-- DETAIL: 500 dead row versions cannot be removed yet

-- VACUUM + update statistics
VACUUM ANALYZE employees;
```

Key point: regular VACUUM usually **does not shrink the table file on disk**. It marks freed space as reusable within the relation (and may truncate empty end pages in some cases).

#### VACUUM FULL

```sql
-- Rewrites the entire table and physically shrinks the file
-- Takes an EXCLUSIVE LOCK: normal reads and writes are blocked!
-- Use only when severe bloat justifies the disruption
VACUUM FULL employees;
```

**VACUUM FULL can disrupt production** because it takes an exclusive lock. Alternatives such as `pg_repack` can reduce blocking, but still have operational considerations.

#### ANALYZE

```sql
-- Not VACUUM, but commonly used alongside it
-- Updates statistics that the query planner uses for estimates
ANALYZE employees;

-- Only a specific column
ANALYZE employees (salary, department);
```

### Autovacuum

PostgreSQL runs background processes that automatically schedule VACUUM and ANALYZE. Settings are controlled in `postgresql.conf` and per-table configuration.

#### Key Parameters

```
autovacuum = on                          # enabled by default
autovacuum_naptime = 60                  # check interval (seconds)

# When to trigger VACUUM:
autovacuum_vacuum_threshold = 50         # minimum dead-tuple count
autovacuum_vacuum_scale_factor = 0.2     # plus 20% of table size
# Formula: trigger VACUUM when dead_tuples > threshold + scale_factor * table_size
# For 10,000 rows: threshold 50 + 0.2*10000 = 2050 dead tuples

# When to trigger ANALYZE:
autovacuum_analyze_threshold = 50
autovacuum_analyze_scale_factor = 0.1    # 10% of table size

# Resource usage (throttling):
autovacuum_vacuum_cost_limit = 200       # pause after this much cost
autovacuum_vacuum_cost_delay = 2ms       # pause length
```

#### Per-Table Autovacuum Settings

For tables with special needs (e.g., very large tables with frequent updates):

```sql
ALTER TABLE hot_table SET (
    autovacuum_vacuum_scale_factor = 0.01,    -- VACUUM with 1% dead tuples
    autovacuum_analyze_scale_factor = 0.005,  -- ANALYZE with 0.5%
    autovacuum_vacuum_cost_delay = 0          -- no throttling for this table
);
```

### Monitoring Bloat

```sql
-- Estimate bloat (simple method)
SELECT
    schemaname, relname,
    n_live_tup,
    n_dead_tup,
    ROUND(n_dead_tup::numeric / NULLIF(n_live_tup + n_dead_tup, 0) * 100, 2) AS dead_pct,
    last_vacuum,
    last_autovacuum,
    last_analyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;

-- Actual vs expected table size
SELECT
    relname,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
    pg_size_pretty(pg_relation_size(relid)) AS table_size,
    pg_size_pretty(pg_indexes_size(relid)) AS index_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
```

### Transaction ID Wraparound

```sql
-- Check proximity to wraparound
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    2147483647 - age(datfrozenxid) AS remaining
FROM pg_database
ORDER BY xid_age DESC;

-- If remaining gets critically low, urgently investigate and perform anti-wraparound vacuuming
VACUUM FREEZE employees;
```

If transaction-ID aging is left unmanaged in production, PostgreSQL may eventually refuse normal write transactions to protect data integrity. Monitoring and responsive autovacuum settings are critical.

### Interview Questions — Topic 28

**Q1: What is VACUUM, and why is it necessary in PostgreSQL?**
A: VACUUM cleans up dead tuples left by MVCC after updates and deletes. Without it, tables and indexes can bloat and transaction-ID wraparound risks increase. Autovacuum performs this maintenance in the background.

**Q2: What is the difference between VACUUM and VACUUM FULL?**
A: Ordinary VACUUM generally makes dead space reusable without rewriting the entire table and allows normal database activity to continue. VACUUM FULL rewrites the table to compact it and reclaim disk space, but takes an exclusive lock. Use normal VACUUM routinely; reserve VACUUM FULL for exceptional cases or consider alternatives.

**Q3: What is transaction ID wraparound, and why is it dangerous?**
A: PostgreSQL transaction IDs have a finite numbering range. Old tuple visibility information must be frozen to avoid ambiguous visibility after ID reuse. If maintenance falls too far behind, PostgreSQL protects itself by restricting normal writes. Monitor `age(datfrozenxid)` and autovacuum health.

---

## TOPIC 29: pg_stat_statements, pg_stat_user_tables

### pg_stat_statements — A Key Performance Tool

An extension that tracks **SQL statement statistics**: execution counts, timings, and various I/O measures.

```sql
-- Enable the extension (setup may require a restart)
-- postgresql.conf:
-- shared_preload_libraries = 'pg_stat_statements'

CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

#### Finding the Slowest Queries

```sql
-- Top 10 statements by total execution time
SELECT
    calls,
    ROUND(total_exec_time::numeric, 2) AS total_ms,
    ROUND(mean_exec_time::numeric, 2) AS avg_ms,
    ROUND((100 * total_exec_time / SUM(total_exec_time) OVER())::numeric, 2) AS pct,
    LEFT(query, 100) AS query_preview
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 10;

-- Top 10 statements by number of calls (possible N+1 problem?)
SELECT
    calls,
    ROUND(mean_exec_time::numeric, 2) AS avg_ms,
    LEFT(query, 100) AS query_preview
FROM pg_stat_statements
ORDER BY calls DESC
LIMIT 10;

-- Top 10 by I/O (disk reads)
SELECT
    calls,
    shared_blks_read,    -- blocks read into shared buffers
    shared_blks_hit,     -- shared buffer cache hits
    ROUND(shared_blks_hit::numeric / NULLIF(shared_blks_hit + shared_blks_read, 0) * 100, 2) AS cache_hit_pct,
    LEFT(query, 100) AS query_preview
FROM pg_stat_statements
ORDER BY shared_blks_read DESC
LIMIT 10;
```

#### Resetting Statistics

```sql
SELECT pg_stat_statements_reset();  -- reset measurements
```

### pg_stat_user_tables — Table Health

```sql
SELECT
    schemaname,
    relname AS table_name,
    seq_scan,              -- sequential scan count
    seq_tup_read,          -- tuples read by sequential scans
    idx_scan,              -- index scan count
    idx_tup_fetch,         -- rows fetched using indexes
    n_tup_ins,             -- estimated number of inserted tuples
    n_tup_upd,             -- estimated number of updated tuples
    n_tup_del,             -- estimated number of deleted tuples
    n_live_tup,            -- estimated live tuples
    n_dead_tup,            -- estimated dead tuples (awaiting cleanup)
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY seq_scan DESC;
```

#### Useful Diagnostic Queries

```sql
-- Tables worth investigating for missing indexes (many seq scans)
SELECT relname, seq_scan, idx_scan,
       ROUND(seq_scan::numeric / NULLIF(seq_scan + idx_scan, 0) * 100, 2) AS seq_pct
FROM pg_stat_user_tables
WHERE seq_scan > 100
ORDER BY seq_pct DESC;

-- Potentially unused indexes (take space and slow writes)
SELECT
    indexrelname AS index_name,
    relname AS table_name,
    idx_scan,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE idx_scan = 0 AND schemaname = 'public'
ORDER BY pg_relation_size(indexrelid) DESC;

-- Cache hit ratio (interpret in context, not against a universal threshold)
SELECT
    SUM(heap_blks_hit) AS cache_hits,
    SUM(heap_blks_read) AS disk_reads,
    ROUND(SUM(heap_blks_hit)::numeric / NULLIF(SUM(heap_blks_hit) + SUM(heap_blks_read), 0) * 100, 2) AS hit_ratio
FROM pg_statio_user_tables;
```

### pg_stat_activity — Currently Active Sessions

```sql
-- What is happening in the database right now?
SELECT
    pid,
    usename,
    application_name,
    state,               -- active, idle, idle in transaction
    wait_event_type,
    query_start,
    NOW() - query_start AS duration,
    LEFT(query, 80) AS query
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY query_start;

-- Cancel a slow query
SELECT pg_cancel_backend(pid);     -- cancel (graceful)
SELECT pg_terminate_backend(pid);  -- terminate the backend session
```

### Interview Questions — Topic 29

**Q1: How would you find the slowest queries in PostgreSQL?**
A: Use the `pg_stat_statements` extension. Sort by `total_exec_time` to see overall impact or `mean_exec_time` to see average latency. Also inspect `calls`: a 1 ms query called a million times may consume far more total time than a 100 ms query called ten times.

**Q2: How do you know if a table is missing an index?**
A: Inspect `pg_stat_user_tables` metrics such as `seq_scan`, `idx_scan`, and `seq_tup_read`. High sequential-read activity can warrant investigation, but it does not by itself prove an index is missing. Combine this with `pg_stat_statements` and EXPLAIN plans for specific queries.

**Q3: What is a good cache hit ratio, and why does it matter?**
A: A high cache hit ratio can indicate efficient reuse of cached pages, but there is no universal threshold such as 99% for every workload. A low ratio might reflect a working set larger than memory, cold scans, or I/O-heavy access patterns. Investigate with `pg_statio_user_tables` and disk metrics.

---

## TOPIC 30: Connection Pooling (PgBouncer)

### Why Is Connection Pooling Important?

Each PostgreSQL connection typically uses **a server process**. Processes consume:
- Memory (often several MB per connection).
- CPU/process-management overhead.
- Resources for TLS and authentication handshakes.

Without pooling, hundreds of web workers can open hundreds of server connections. Pooling lets many clients share fewer database connections, reducing overhead.

### How a Connection Pool Works

```
[Web Worker 1] ─┐
[Web Worker 2] ─┤
[Web Worker 3] ─┼──→ [Connection Pool] ──→ [PostgreSQL]
[Web Worker 4] ─┤     (20 konekcija)        (20 procesa)
[Web Worker 5] ─┘
...
[Web Worker 500]
```

A worker requests a connection → the pool supplies an available one → the worker finishes → the connection is returned to the pool for reuse instead of being closed.

### PgBouncer

A popular external PostgreSQL connection pooler that sits between applications and the database.

#### Three Pooling Modes

**1. Session pooling (default)**
A server connection is assigned to a client for the entire session and released when the session ends.
- Supports typical PostgreSQL session features (prepared statements, temporary tables, session variables).
- Offers the least multiplexing because connections are reserved at session level.

**2. Transaction pooling (often recommended)**
A server connection is assigned only during a transaction, then returned to the pool.
- Efficient because many clients are idle between transactions.
- Session-dependent features require care: temporary tables, session-level SET, LISTEN/NOTIFY, and certain prepared-statement configurations may not behave as with session pooling.
- Often the preferred choice for stateless web services.

**3. Statement pooling**
A server connection is assigned per statement and released immediately afterward.
- Most aggressive multiplexing, but not suitable for explicit multi-statement transactions.
- Used less often.

#### Configuring PgBouncer

```ini
; pgbouncer.ini

[databases]
mydb = host=127.0.0.1 port=5432 dbname=mydb

[pgbouncer]
listen_port = 6432              ; PgBouncer listens here
listen_addr = 0.0.0.0

pool_mode = transaction         ; transaction pooling

; Pool size
default_pool_size = 20          ; max server connections per user/database pool
min_pool_size = 5               ; keep at least this many open
max_client_conn = 1000          ; maximum client connections to PgBouncer

; Timeouts
server_idle_timeout = 600       ; close idle server connection after 10 minutes
client_idle_timeout = 0         ; do not time out idle clients
query_timeout = 30              ; terminate queries exceeding 30 seconds
```

The application connects to PgBouncer (often port 6432) rather than directly to PostgreSQL (typically port 5432).

### Application-Level Pooling (SQLAlchemy)

Besides an external pooler, most ORMs provide an internal connection pool:

```python
from sqlalchemy import create_engine

engine = create_engine(
    "postgresql://user:pass@localhost:5432/mydb",
    pool_size=20,           # number of connections in the pool
    max_overflow=10,        # extra connections if the pool is full
    pool_timeout=30,        # wait up to 30 seconds for a connection
    pool_recycle=1800,      # recycle connections after 30 minutes
    pool_pre_ping=True,     # check that a connection is alive before use
)
```

### How Many Connections Do You Need?

A rough starting formula:

```
optimal_connections = (CPU_cores * 2) + effective_spindle_count
```

For a server with 8 CPU cores and an SSD:
- `(8 * 2) + 1 = 17` connections.

More connections do NOT necessarily mean better performance. Too many can cause:
- Lock contention.
- Excessive context switching.
- Excessive RAM consumption.

**Rule of thumb:** Start with a modest pool, load test, and adjust. The right size depends on workload, query latency, and architecture.

### Interview Questions — Topic 30

**Q1: Why is connection pooling useful in PostgreSQL?**
A: PostgreSQL usually uses a separate server process per connection, which consumes memory and other resources. With hundreds of concurrent clients, overhead adds up. Connection pools reuse a limited number of connections across many clients and avoid repeated connection setup and TLS/authentication handshakes.

**Q2: What is the difference between session pooling and transaction pooling in PgBouncer?**
A: Session pooling reserves a server connection for the whole client session, preserving session state but limiting multiplexing. Transaction pooling reserves it only for the duration of a transaction, enabling more reuse. Applications must avoid assumptions about state persisting on the same server connection; prepared statements and other session features require configuration and care.

**Q3: How many connections should be configured in a pool?**
A: A formula such as `(CPU_cores * 2) + 1` is sometimes used as an initial heuristic, not a universal rule. Excess connections can increase contention, context switches, and memory usage. Start with a modest size, load-test your workload, and minimize how long transactions hold connections.

---

# PART 7: PYTHON + DATABASES (CONTINUED)

---

## TOPIC 32: SQLAlchemy Core

### What Is SQLAlchemy?

SQLAlchemy is **one of the best-known Python libraries** for database access. It has two major layers:

1. **Core** — SQL Expression Language, a Pythonic API for constructing SQL.
2. **ORM** — Object Relational Mapper, mapping Python classes to database tables.

### Engine — The Starting Point

```python
from sqlalchemy import create_engine

engine = create_engine(
    "postgresql+psycopg2://user:password@localhost:5432/mydb",
    echo=True,          # log SQL statements (for debugging)
    pool_size=10,
    max_overflow=5,
)

# URL format:
# dialect+driver://username:password@host:port/database
# postgresql+psycopg2://...    (PostgreSQL with psycopg2 driver)
# postgresql+asyncpg://...     (PostgreSQL async)
# mysql+pymysql://...          (MySQL)
# sqlite:///path/to/db.sqlite  (SQLite)
```

### Connections and Raw SQL

```python
from sqlalchemy import text

with engine.connect() as conn:
    # Raw SQL with parameters
    result = conn.execute(
        text("SELECT id, name, salary FROM employees WHERE department = :dept"),
        {"dept": "Engineering"}
    )

    for row in result:
        print(row.id, row.name, row.salary)  # access by column name

    # INSERT/UPDATE/DELETE require a transaction commit
    conn.execute(
        text("INSERT INTO employees (name, salary) VALUES (:name, :salary)"),
        {"name": "Ana", "salary": 85000}
    )
    conn.commit()
```

### MetaData and Table Definitions

```python
from sqlalchemy import MetaData, Table, Column, Integer, String, Numeric, ForeignKey, DateTime
from sqlalchemy.sql import func

metadata = MetaData()

departments = Table("departments", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("budget", Numeric(12, 2)),
)

employees = Table("employees", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("department_id", Integer, ForeignKey("departments.id")),
    Column("salary", Numeric(10, 2), nullable=False),
    Column("created_at", DateTime, server_default=func.now()),
)

# Create the tables in the database
metadata.create_all(engine)

# Or reflect existing database tables
metadata.reflect(bind=engine)
existing_table = metadata.tables["users"]
```

### SQL Expression Language

Instead of writing raw SQL, you work with Python objects:

```python
from sqlalchemy import select, insert, update, delete, and_, or_, func

# SELECT
stmt = (
    select(employees.c.name, employees.c.salary)
    .where(employees.c.department_id == 1)
    .where(employees.c.salary > 80000)
    .order_by(employees.c.salary.desc())
    .limit(10)
)

with engine.connect() as conn:
    result = conn.execute(stmt)
    for row in result:
        print(row.name, row.salary)

# JOIN
stmt = (
    select(employees.c.name, departments.c.name.label("dept_name"))
    .join(departments, employees.c.department_id == departments.c.id)
    .where(departments.c.name == "Engineering")
)

# GROUP BY + aggregate
stmt = (
    select(
        departments.c.name,
        func.count(employees.c.id).label("emp_count"),
        func.avg(employees.c.salary).label("avg_salary"),
    )
    .join(employees, departments.c.id == employees.c.department_id)
    .group_by(departments.c.name)
    .having(func.count(employees.c.id) > 5)
)

# INSERT
stmt = insert(employees).values(name="Marko", department_id=1, salary=90000)
with engine.connect() as conn:
    result = conn.execute(stmt)
    conn.commit()
    print(result.inserted_primary_key)  # (42,)

# UPDATE
stmt = (
    update(employees)
    .where(employees.c.department_id == 1)
    .values(salary=employees.c.salary * 1.1)
)

# DELETE
stmt = delete(employees).where(employees.c.id == 42)
```

### When to Use Core vs ORM

| Core | ORM |
|------|-----|
| Performance-sensitive queries | CRUD operations |
| Complex reporting/analytics | Domain objects with behavior |
| Bulk operations | Relationships among objects |
| Migrations and explicit SQL control | Many web application operations |
| When you want direct control of generated SQL | When you favor object-oriented productivity |

### Interview Questions — Topic 32

**Q1: What is SQLAlchemy Core, and how does it differ from the ORM?**
A: Core is a SQL Expression Language that uses Table objects and Python expressions to construct SQL, without mapping tables to domain classes. The ORM maps classes to tables and adds Session, relationships, and loading strategies. Core offers direct SQL control and can be suitable for bulk/analytic workloads; the ORM is convenient for object-oriented CRUD.

**Q2: Why do you use `text()` for raw SQL in SQLAlchemy?**
A: `text()` marks a string as a SQL statement and supports safely bound named parameters such as `:param`. Binding values rather than interpolating them helps prevent SQL injection and allows SQLAlchemy to handle parameter types correctly.

---

## TOPIC 33: SQLAlchemy ORM

### Defining Models

```python
from sqlalchemy import ForeignKey, String, Numeric, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    budget: Mapped[float | None] = mapped_column(Numeric(12, 2))

    employees: Mapped[list["Employee"]] = relationship(back_populates="department")

    def __repr__(self):
        return f"Department(id={self.id}, name={self.name!r})"

class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    salary: Mapped[float] = mapped_column(Numeric(10, 2))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    department: Mapped[Department | None] = relationship(back_populates="employees")

    def __repr__(self):
        return f"Employee(id={self.id}, name={self.name!r})"
```

SQLAlchemy 2.0 commonly uses `Mapped[]` type annotations and `mapped_column()` as its modern declarative style, rather than relying only on the older Column style.

### Session — Working with Objects

```python
from sqlalchemy.orm import Session

# Create
with Session(engine) as session:
    dept = Department(name="Engineering", budget=500000)
    session.add(dept)

    emp = Employee(name="Ana", salary=85000, department=dept)
    session.add(emp)

    session.commit()
    print(emp.id)  # auto-generated ID

# Read
with Session(engine) as session:
    emp = session.get(Employee, 42)  # by primary key
    print(emp.name, emp.department.name)  # access a relationship

# Update
with Session(engine) as session:
    emp = session.get(Employee, 42)
    emp.salary = 95000       # just change the attribute
    session.commit()         # SQLAlchemy generates the UPDATE

# Delete
with Session(engine) as session:
    emp = session.get(Employee, 42)
    session.delete(emp)
    session.commit()
```

### Querying (select)

```python
from sqlalchemy import select, func

with Session(engine) as session:
    # All employees in Engineering
    stmt = select(Employee).where(Employee.department_id == 1)
    employees = session.scalars(stmt).all()

    # With a JOIN
    stmt = (
        select(Employee)
        .join(Employee.department)
        .where(Department.name == "Engineering")
        .order_by(Employee.salary.desc())
    )
    for emp in session.scalars(stmt):
        print(emp.name, emp.salary)

    # Aggregation
    stmt = (
        select(Department.name, func.count(Employee.id), func.avg(Employee.salary))
        .join(Employee, isouter=True)
        .group_by(Department.name)
    )
    for name, count, avg_sal in session.execute(stmt):
        print(f"{name}: {count} employees, avg ${avg_sal}")
```

### Lazy vs Eager Loading

**Lazy loading:** A relationship is loaded when accessed, which may cause an N+1 query problem.

```python
with Session(engine) as session:
    employees = session.scalars(select(Employee)).all()  # 1 query

    for emp in employees:
        print(emp.department.name)  # N queries (one lazy load per employee)
```

**Eager loading:** Load related objects in advance.

```python
from sqlalchemy.orm import joinedload, selectinload, subqueryload

# joinedload: SQL JOIN (one query)
stmt = select(Employee).options(joinedload(Employee.department))
employees = session.scalars(stmt).unique().all()
# SELECT employees.*, departments.* FROM employees JOIN departments ...

# selectinload: SELECT IN (two queries; often better for collections)
stmt = select(Department).options(selectinload(Department.employees))
departments = session.scalars(stmt).all()
# 1: SELECT * FROM departments
# 2: SELECT * FROM employees WHERE department_id IN (1, 2, 3, ...)
```

**Rule of thumb:**
- `joinedload` is often useful for many-to-one relationships (employee → department).
- `selectinload` is often useful for one-to-many relationships (department → employees).

### Unit of Work Pattern

Session tracks changes and flushes SQL as needed, usually before or during `commit()`:

```python
with Session(engine) as session:
    emp = session.get(Employee, 1)
    emp.name = "Ana Updated"         # tracked by the session

    dept = Department(name="New Dept")
    session.add(dept)                 # new object

    old = session.get(Employee, 99)
    session.delete(old)               # marked for deletion

    session.commit()
    # SQLAlchemy generates:
    # UPDATE employees SET name = 'Ana Updated' WHERE id = 1
    # INSERT INTO departments (name) VALUES ('New Dept')
    # DELETE FROM employees WHERE id = 99
```

### Interview Questions — Topic 33

**Q1: What is the ORM N+1 problem, and how do you solve it?**
A: N+1 occurs when the ORM lazily loads a relationship for N objects, producing N additional queries. Use eager loading such as `joinedload()` (JOIN-based) or `selectinload()` (batched IN queries), choosing the strategy that fits the relationship and workload.

**Q2: What is the Unit of Work pattern in SQLAlchemy?**
A: A Session tracks new, changed, and deleted objects and flushes the required SQL operations as a unit. Changes are coordinated within a transaction so they can commit or roll back together. Note that a flush may happen before `commit()`; commit is not the only time SQL is sent.

**Q3: What is the difference between `session.execute()` and `session.scalars()`?**
A: `execute()` returns a Result whose rows may contain multiple columns or entities. `scalars()` returns the first element from each result row. For `select(Employee)`, `scalars()` yields Employee objects directly, while `execute()` yields rows wrapping them.

---

## TOPIC 34: Alembic Migrations

### What Is Alembic?

Alembic is a **database schema migration tool**, effectively version control for database structures. It is commonly used with SQLAlchemy.

Why use migrations? You need more than manually running `ALTER TABLE` in production:
- Change history (who, when, what).
- Rollback/downgrade options where feasible.
- Consistency across environments (dev, staging, production).
- Automated application during deployment.

### Initialization

```bash
# Install
pip install alembic

# Initialize in the project
alembic init alembic
```

This creates:
```
alembic/
├── env.py              # configuration (connection, metadata)
├── script.py.mako      # migration template
├── versions/           # migrations folder
│   └── (migrations go here)
alembic.ini             # configuration file (database URL)
```

### Configuration

```ini
# alembic.ini
sqlalchemy.url = postgresql://user:pass@localhost:5432/mydb
```

```python
# alembic/env.py — set target_metadata
from myapp.models import Base
target_metadata = Base.metadata
```

### Creating Migrations

```bash
# Automatic (detect differences between models and database)
alembic revision --autogenerate -m "add users table"

# Manual (empty migration file to fill in yourself)
alembic revision -m "add index on email"
```

#### Example of an Auto-Generated Migration

```python
# alembic/versions/abc123_add_users_table.py

"""add users table"""

revision = 'abc123'
down_revision = None       # initial migration
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table('users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('idx_users_email', 'users', ['email'], unique=True)

def downgrade():
    op.drop_index('idx_users_email', 'users')
    op.drop_table('users')
```

#### Manual Migration — Adding a Column

```python
def upgrade():
    op.add_column('users', sa.Column('is_active', sa.Boolean(), 
                                      server_default=sa.text('true'), 
                                      nullable=False))

def downgrade():
    op.drop_column('users', 'is_active')
```

### Applying Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Apply one revision at a time
alembic upgrade +1

# Downgrade by one revision
alembic downgrade -1

# Downgrade to a specific revision
alembic downgrade abc123

# Downgrade everything (to base)
alembic downgrade base

# Show the current version
alembic current

# Show the history
alembic history
```

### Common Migration Operations

```python
# Add a column
op.add_column('users', sa.Column('phone', sa.String(20)))

# Drop a column
op.drop_column('users', 'phone')

# Change a column's type
op.alter_column('users', 'name', type_=sa.String(200))

# Add an index
op.create_index('idx_users_city', 'users', ['city'])

# Add a foreign key
op.create_foreign_key('fk_orders_customer', 'orders', 'customers',
                       ['customer_id'], ['id'], ondelete='CASCADE')

# Add a unique constraint
op.create_unique_constraint('uq_users_email', 'users', ['email'])

# Rename a table
op.rename_table('old_name', 'new_name')

# Bulk data migration
from alembic import op
from sqlalchemy import text

def upgrade():
    conn = op.get_bind()
    conn.execute(text("UPDATE users SET status = 'active' WHERE status IS NULL"))
```

### Interview Questions — Topic 34

**Q1: What is Alembic, and why is it used?**
A: Alembic manages versioned database schema migrations. Each change, such as a new table or index, is represented in a revision with upgrade() and optionally downgrade() logic. It provides traceability and consistent deployments across environments.

**Q2: What does `--autogenerate` do, and what are its limitations?**
A: Autogenerate compares SQLAlchemy metadata with the current database schema and proposes a migration for detected differences. It may interpret column renames as drop/add operations, miss some type changes, and cannot infer arbitrary data migrations. Always review generated migrations before applying them.

**Q3: How would you roll back a migration in production?**
A: A command such as `alembic downgrade -1` can run the previous revision's downgrade if it exists and is safe. However, some schema changes are irreversible or risk data loss. Prefer tested, backwards-compatible migrations and a clearly defined rollback or roll-forward plan for production.

---

## TOPIC 35: Async Database Access (asyncpg, Async SQLAlchemy 2.0)

### Why Use Async DB Access?

In async web frameworks (FastAPI, aiohttp), a blocking database call made on the event-loop thread prevents it from servicing other requests. Async DB drivers let the event loop handle other work while waiting for database responses.

### asyncpg — A Fast Async PostgreSQL Driver

```python
import asyncpg
import asyncio

async def main():
    conn = await asyncpg.connect(
        host="localhost", database="mydb",
        user="postgres", password="secret"
    )

    # SELECT
    rows = await conn.fetch(
        "SELECT id, name, salary FROM employees WHERE department = $1",
        "Engineering"
    )
    for row in rows:
        print(row["name"], row["salary"])  # dictionary-like access

    # One row
    row = await conn.fetchrow(
        "SELECT * FROM employees WHERE id = $1", 42
    )

    # One value
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM employees WHERE salary > $1", 80000
    )

    # INSERT/UPDATE
    await conn.execute(
        "INSERT INTO employees (name, salary) VALUES ($1, $2)",
        "Ana", 85000
    )

    await conn.close()

asyncio.run(main())
```

**Note:** asyncpg uses `$1, $2, $3` placeholders for parameters (unlike `%s` in psycopg2).

### asyncpg Connection Pool

```python
import asyncpg

async def main():
    pool = await asyncpg.create_pool(
        host="localhost", database="mydb",
        user="postgres", password="secret",
        min_size=5,      # minimum connections
        max_size=20,     # maximum connections
    )

    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM employees")

    await pool.close()
```

### Async SQLAlchemy 2.0

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select

engine = create_async_engine(
    "postgresql+asyncpg://user:pass@localhost:5432/mydb",
    pool_size=20,
    max_overflow=10,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_employees():
    async with async_session() as session:
        stmt = select(Employee).where(Employee.salary > 80000)
        result = await session.scalars(stmt)
        return result.all()

async def create_employee(name: str, salary: float):
    async with async_session() as session:
        emp = Employee(name=name, salary=salary)
        session.add(emp)
        await session.commit()
        return emp

# FastAPI integration
from fastapi import FastAPI, Depends

app = FastAPI()

async def get_db():
    async with async_session() as session:
        yield session

@app.get("/employees")
async def list_employees(db: AsyncSession = Depends(get_db)):
    result = await db.scalars(select(Employee))
    return result.all()
```

### Implicit Lazy Loading Is Problematic in Async Mode!

```python
# This raises an error in async mode!
async with async_session() as session:
    emp = await session.get(Employee, 1)
    print(emp.department.name)  # MissingGreenlet error!

# Must eagerly load the relationship:
stmt = select(Employee).options(selectinload(Employee.department))
emp = await session.scalar(stmt.where(Employee.id == 1))
print(emp.department.name)  # OK — already loaded
```

### Interview Questions — Topic 35

**Q1: Why use an async DB driver in a FastAPI application?**
A: Async frameworks use event loops. Calling a blocking DB driver directly from the event-loop thread stalls other tasks. An async driver such as asyncpg releases the event loop during I/O waits, enabling efficient concurrent request handling.

**Q2: Why is lazy loading problematic in async SQLAlchemy?**
A: Lazy loading can trigger implicit database I/O when a relationship attribute is accessed. In async code, implicit I/O is not supported in ordinary attribute access and can raise errors. Prefer explicit eager loading (`selectinload`, `joinedload`) or supported async-aware attribute access patterns.

---

## TOPIC 36: Testing with a Database

### Approach 1: Test Database + Transaction Rollback

A common pattern: each test runs in a transaction that is rolled back afterward:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

TEST_DB_URL = "postgresql://user:pass@localhost:5432/test_db"

@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DB_URL)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture
def db_session(engine):
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn)

    yield session

    session.close()
    trans.rollback()   # undo ALL changes — leave database clean
    conn.close()

# Tests
def test_create_employee(db_session):
    emp = Employee(name="Test", salary=50000)
    db_session.add(emp)
    db_session.flush()  # write SQL (within the uncommitted transaction)

    assert emp.id is not None
    assert emp.name == "Test"
    # At the end of the test: ROLLBACK — emp is not retained

def test_get_employees_empty(db_session):
    result = db_session.scalars(select(Employee)).all()
    assert result == []  # previous test was rolled back!
```

### Approach 2: factory_boy for Test Data

```python
import factory
from factory.alchemy import SQLAlchemyModelFactory

class DepartmentFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Department
        sqlalchemy_session_persistence = "flush"

    name = factory.Sequence(lambda n: f"Department {n}")
    budget = factory.Faker("random_int", min=100000, max=1000000)

class EmployeeFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Employee
        sqlalchemy_session_persistence = "flush"

    name = factory.Faker("name")
    salary = factory.Faker("random_int", min=40000, max=120000)
    department = factory.SubFactory(DepartmentFactory)

# In the test:
def test_employee_in_department(db_session):
    EmployeeFactory._meta.sqlalchemy_session = db_session
    DepartmentFactory._meta.sqlalchemy_session = db_session

    dept = DepartmentFactory(name="Engineering")
    emp1 = EmployeeFactory(department=dept)
    emp2 = EmployeeFactory(department=dept)

    assert len(dept.employees) == 2
```

### Approach 3: Testcontainers (Isolated PostgreSQL in Docker)

```python
import pytest
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def db_engine():
    with PostgresContainer("postgres:15") as postgres:
        engine = create_engine(postgres.get_connection_url())
        Base.metadata.create_all(engine)
        yield engine
```

Each test run gets a fresh PostgreSQL instance in a Docker container. This provides strong isolation but adds setup cost.

### Database Testing Rules

1. **Never run tests against production** — use a test database or container.
2. **Each test must be isolated** — it must not rely on another test's state.
3. **Transaction rollback** is often a fast isolation method.
4. Use **factory_boy** to create test data instead of repetitive manual INSERTs.
5. **Test your business logic**, not the ORM library's internal behavior.

### Interview Questions — Topic 36

**Q1: How do you isolate database tests so they do not depend on one another?**
A: A common approach is to run each test in a transaction and roll it back after the test. Another option is Testcontainers, which provides a fresh PostgreSQL instance in Docker for a test run. The goal is to keep tests independent and reproducible.

**Q2: What is factory_boy, and why use it in tests?**
A: A library for generating test objects with sensible defaults. Instead of manually constructing `Employee(name="Test", salary=50000, department_id=1, ...)` everywhere, define a factory and call `EmployeeFactory()`. It supports unique sequences, related objects via SubFactory, and realistic dummy data via Faker.

---

# PART 8: NoSQL AND OTHER DATABASES

---

## TOPIC 37: Redis

### What Is Redis?

Redis is an **in-memory key-value store** that holds data primarily in RAM, enabling very low-latency operations. Common uses include caching, session storage, rate limiting, queues, and real-time analytics.

### Data Structures

Redis is more than a basic key-value store; it supports rich data structures:

#### Strings

```redis
SET user:1:name "Ana"
GET user:1:name              # "Ana"

SET counter 0
INCR counter                 # 1
INCRBY counter 5             # 6

# With TTL (expiry)
SET session:abc123 "user_data" EX 3600    # expires after one hour
TTL session:abc123                         # remaining time
```

#### Hashes (Maps/Dictionaries)

```redis
HSET user:1 name "Ana" email "ana@mail.com" age 28
HGET user:1 name             # "Ana"
HGETALL user:1               # {"name": "Ana", "email": "ana@mail.com", "age": "28"}
HINCRBY user:1 age 1         # 29
```

#### Lists (Linked Lists)

```redis
LPUSH queue:emails "email1" "email2"     # push left
RPUSH queue:emails "email3"              # push right
RPOP queue:emails                        # pop right: "email3"
LPOP queue:emails                        # pop left: "email2"
LRANGE queue:emails 0 -1                 # all elements
LLEN queue:emails                        # length
```

#### Sets (Unique Elements)

```redis
SADD tags:post:1 "python" "backend" "tutorial"
SMEMBERS tags:post:1                     # all tags
SISMEMBER tags:post:1 "python"           # 1 (true)

SADD tags:post:2 "python" "flask" "web"
SINTER tags:post:1 tags:post:2           # intersection: {"python"}
SUNION tags:post:1 tags:post:2           # all unique tags
```

#### Sorted Sets (Ranked Lists)

```redis
ZADD leaderboard 100 "Ana" 85 "Marko" 92 "Jovan"
ZRANGE leaderboard 0 -1 WITHSCORES      # sorted by score
ZREVRANGE leaderboard 0 2                # top three
ZRANK leaderboard "Ana"                  # rank (zero-based)
ZINCRBY leaderboard 10 "Marko"           # Marko: 95
```

### Caching Pattern

```python
import redis
import json

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

def get_user(user_id):
    cache_key = f"user:{user_id}"

    cached = r.get(cache_key)
    if cached:
        return json.loads(cached)         # cache HIT

    user = db.query("SELECT * FROM users WHERE id = %s", user_id)
    r.setex(cache_key, 3600, json.dumps(user))   # cache for one hour

    return user                            # cache MISS

def update_user(user_id, data):
    db.execute("UPDATE users SET ... WHERE id = %s", user_id)
    r.delete(f"user:{user_id}")           # invalidate cache
```

### Cache Invalidation Strategies

| Strategy | Description | Use case |
|-----------|------|----------|
| TTL | cache expires after N seconds | many common scenarios |
| Write-through | update cache and database in the write path | when fresh cached data is important |
| Write-behind | update cache first, then persist asynchronously | high write throughput, with durability tradeoffs |
| Cache-aside | application manages reads (cache → DB) and writes (DB → invalidate cache) | common general-purpose pattern |

### Persistence (Data Durability)

Redis stores data in memory but can persist it to disk:

- **RDB (snapshotting):** Periodic snapshots. Writes since the last snapshot may be lost after a crash.
- **AOF (Append Only File):** Logs write operations. Recovery durability depends on fsync configuration, often once per second.
- **Both:** RDB + AOF can provide useful complementary recovery options.

### Pub/Sub

```redis
# Subscriber (waits for messages):
SUBSCRIBE notifications

# Publisher (sends messages):
PUBLISH notifications "New order #123"
```

```python
# Python subscriber
import redis

r = redis.Redis()
pubsub = r.pubsub()
pubsub.subscribe('notifications')

for message in pubsub.listen():
    if message['type'] == 'message':
        print(f"Received: {message['data']}")
```

### Interview Questions — Topic 37

**Q1: When would you use Redis?**
A: (1) Caching frequent database reads; (2) session storage; (3) rate limiting using counters and expiration; (4) leaderboards with Sorted Sets; (5) job queues with Lists or Streams; and (6) approximate unique counts with HyperLogLog for real-time analytics.

**Q2: What happens to Redis data when the server crashes?**
A: It depends on persistence settings. Without persistence, in-memory data is lost. With RDB, you restore from the most recent snapshot. With AOF, you can replay logged operations, subject to fsync configuration. For a disposable cache, persistence may be unnecessary because the cache can be rebuilt.

**Q3: Explain the cache-aside pattern.**
A: The application manages caching. (1) Read: check the cache first; on a miss, read from the database and populate the cache. (2) Write: update the database, then invalidate the relevant cached entry. The next read repopulates it with fresh data. It is a common, straightforward pattern.

---

## TOPIC 38: MongoDB Fundamentals

### What Is MongoDB?

MongoDB is a **document-oriented NoSQL database**. Instead of relational tables and rows, it stores **documents** (BSON objects resembling JSON) in **collections**.

### Concepts: SQL vs MongoDB

| SQL | MongoDB |
|-----|---------|
| Database | Database |
| Table | Collection |
| Row | Document |
| Column | Field |
| JOIN | Embedding / $lookup |
| Primary Key | _id (typically generated automatically) |
| Schema | flexible/document-oriented |

### CRUD Operations

```javascript
// INSERT
db.users.insertOne({
    name: "Ana",
    email: "ana@mail.com",
    age: 28,
    tags: ["python", "backend"],
    address: { city: "Belgrade", country: "Serbia" }
});

db.users.insertMany([
    { name: "Marko", email: "marko@mail.com", age: 32 },
    { name: "Jovan", email: "jovan@mail.com", age: 25 }
]);

// FIND (SELECT)
db.users.find({ age: { $gt: 25 } });                    // WHERE age > 25
db.users.find({ tags: "python" });                       // where tags contains "python"
db.users.find({ "address.city": "Belgrade" });           // nested field
db.users.find({ age: { $gte: 25, $lte: 35 } });        // BETWEEN
db.users.find({ name: { $in: ["Ana", "Marko"] } });    // IN

db.users.findOne({ email: "ana@mail.com" });             // one document

// Projection (SELECT specific columns)
db.users.find({}, { name: 1, email: 1, _id: 0 });       // only name and email

// Sort, limit, skip
db.users.find().sort({ age: -1 }).limit(10).skip(20);

// UPDATE
db.users.updateOne(
    { email: "ana@mail.com" },
    { $set: { age: 29, "address.city": "Novi Sad" } }
);

db.users.updateMany(
    { age: { $lt: 25 } },
    { $set: { status: "junior" } }
);

// $inc, $push, $pull
db.users.updateOne({ _id: id }, { $inc: { age: 1 } });
db.users.updateOne({ _id: id }, { $push: { tags: "mongodb" } });
db.users.updateOne({ _id: id }, { $pull: { tags: "python" } });

// DELETE
db.users.deleteOne({ email: "ana@mail.com" });
db.users.deleteMany({ status: "inactive" });
```

### Indexes in MongoDB

```javascript
db.users.createIndex({ email: 1 }, { unique: true });    // B-tree, unique
db.users.createIndex({ age: 1, name: 1 });               // composite
db.users.createIndex({ tags: 1 });                        // multikey (array)
db.users.createIndex({ "address.city": 1 });              // nested field
db.users.createIndex({ name: "text" });                   // full-text
```

### Aggregation Pipeline

MongoDB's framework for filtering, grouping, joining, and other data transformations:

```javascript
db.orders.aggregate([
    { $match: { status: "completed" } },                    // WHERE

    { $group: {                                              // GROUP BY
        _id: "$customer_id",
        total_spent: { $sum: "$amount" },
        order_count: { $sum: 1 },
        avg_order: { $avg: "$amount" }
    }},

    { $match: { total_spent: { $gt: 1000 } } },            // HAVING

    { $sort: { total_spent: -1 } },                          // ORDER BY

    { $limit: 10 },                                          // LIMIT

    { $lookup: {                                             // JOIN
        from: "customers",
        localField: "_id",
        foreignField: "_id",
        as: "customer"
    }},

    { $unwind: "$customer" },                                // flatten array

    { $project: {                                            // SELECT columns
        customer_name: "$customer.name",
        total_spent: 1,
        order_count: 1
    }}
]);
```

### Embedding vs Referencing

**Embedding (Nesting):**
```javascript
// User with embedded addresses
{
    name: "Ana",
    addresses: [
        { city: "Belgrade", zip: "11000" },
        { city: "Novi Sad", zip: "21000" }
    ]
}
// Fast to read (everything in one document)
// Good when: data is always read together, one-to-few relationship
```

**Referencing:**
```javascript
// User document
{ _id: ObjectId("abc"), name: "Ana" }

// Order documents
{ user_id: ObjectId("abc"), product: "Laptop", amount: 999 }
{ user_id: ObjectId("abc"), product: "Mouse", amount: 25 }

// Requires $lookup (JOIN) to combine documents
// Good when: independent updates, one-to-many or many-to-many data
```

### Interview Questions — Topic 38

**Q1: When would you choose MongoDB over PostgreSQL?**
A: For naturally document-shaped data, flexible schemas, and workloads where embedding related information simplifies queries. Examples include content management, flexible profiles, and event metadata. PostgreSQL may be a better fit for complex relational constraints and joins. Both databases support transactions; MongoDB should not be dismissed solely because the application needs ACID properties.

**Q2: Embedding vs referencing — how do you decide?**
A: Embed data that is often read together, has bounded size, and rarely needs independent updates (e.g., a user's small set of addresses). Reference data that can grow unbounded, must be queried independently, or changes separately (e.g., a user with 10,000 orders). Design around access and update patterns, not a universal rule.

---

## TOPIC 39: SQL vs NoSQL — Decision Framework

### When to Use SQL (Relational Databases)

1. **Structured data** with a clear schema.
2. **ACID transactions** are critical (finance, inventory).
3. **Complex relationships** among entities (JOINs).
4. **Referential integrity** (foreign keys and constraints).
5. **Complex queries** (aggregations, window functions, subqueries).
6. **Strong consistency and integrity requirements**.

### When to Use NoSQL

1. **Flexible schema** — records may have different fields.
2. **Very large data volumes** with horizontally scalable access patterns.
3. **High write throughput** (logs, IoT sensors, event streams).
4. **Simple or specialized access patterns** (key-value lookups, document retrieval).
5. **Availability or distribution needs**, depending on the system.
6. **Denormalized records** that are commonly read together.

### Types of NoSQL Databases

| Type | Example | Use case |
|-----|--------|----------|
| Key-Value | Redis, Memcached, DynamoDB | Caching, session, config |
| Document | MongoDB, CouchDB | CMS, user profiles, catalogs |
| Column-Family | Cassandra, HBase | Time-series, IoT, heavy write |
| Graph | Neo4j, Amazon Neptune | Social networks, recommendations |
| Time-Series | TimescaleDB, InfluxDB | Metrics, monitoring, IoT |
| Search | Elasticsearch | Full-text search, log analysis |

### Decision Matrix

```
Do you need ACID transactions?
  Yes → SQL (PostgreSQL)
  No ↓

Does your data have complex relationships (joins across 3+ tables)?
  Yes → SQL
  No ↓

Does the schema change frequently?
  Yes → Document DB (MongoDB) or JSONB in PostgreSQL
  No ↓

Extremely high write throughput (100K+ writes/sec)?
  Yes → Evaluate Cassandra or DynamoDB
  No ↓

Key-value access pattern (get/set by key)?
  Yes → Redis or DynamoDB
  No ↓

Full-text search?
  Yes → Elasticsearch (often alongside a primary SQL database)
  No ↓

Graph traversal (friends of friends, recommendations)?
  Yes → Neo4j
  No ↓

Default → Consider PostgreSQL (flexible general-purpose option)
```

### "Polyglot Persistence"

Many modern systems use **multiple databases** to meet different needs:

```
PostgreSQL  → primary data store (users, orders, products)
Redis       → caching, sessions, rate limiting
Elasticsearch → search, log analysis
Kafka       → event streaming
S3          → file storage
```

### Interview Questions — Topic 39

**Q1: How do you choose between SQL and NoSQL?**
A: Start with the workload: Do I need complex joins and database-enforced relationships? A relational system is often a strong choice. Is the data document-shaped or are access patterns specialized? Consider an appropriate NoSQL system. Do I need distributed scalability or specific consistency guarantees? Evaluate actual product capabilities. PostgreSQL is a good default for many applications, including those with some JSONB data.

**Q2: What is polyglot persistence?**
A: Using different storage technologies for different needs within one system: for example, PostgreSQL for core relational data, Redis for caching, Elasticsearch for search, and Kafka for event streaming (Kafka is a streaming platform, not a general-purpose database). Each tool serves a different access pattern, at the cost of operational complexity.

---

## TOPIC 40: Overview of Other Database Types

### Key-Value (Redis, DynamoDB, etcd)

The simplest model is key → value. Query capabilities vary by product and are often designed around primary-key access.

**DynamoDB** (AWS-managed):
- Serverless options and automatic scaling.
- Low-latency key-based access at scale when designed and provisioned appropriately.
- Partition key + optional sort key.
- Good for serverless apps, gaming data, and session stores.

### Column-Family (Cassandra, HBase)

Data is organized into column families with designs optimized for **large distributed write workloads** and **horizontal scaling**.

**Cassandra:**
- Peer-to-peer architecture without a single primary server.
- Horizontal scaling by adding nodes.
- Tunable consistency.
- CQL (Cassandra Query Language) resembles SQL but has different capabilities and restrictions.
- Useful for high-volume IoT, time-series-like, and messaging workloads.

### Graph (Neo4j, Amazon Neptune)

Represents data as **nodes** and **relationships**, optimized for graph traversal.

```cypher
// Cypher (Neo4j query language)

// Find friends of friends
MATCH (me:Person {name: "Ana"})-[:FRIENDS]->(friend)-[:FRIENDS]->(fof)
WHERE fof <> me AND NOT (me)-[:FRIENDS]->(fof)
RETURN fof.name AS suggestion

// Shortest path between two users
MATCH path = shortestPath((a:Person {name: "Ana"})-[:FRIENDS*]-(b:Person {name: "Marko"}))
RETURN path
```

Best for: social networks, recommendation engines, fraud detection, and knowledge graphs.

### Time-Series (TimescaleDB, InfluxDB)

Optimized for time-stamped, often append-oriented data.

**TimescaleDB** (a PostgreSQL extension):
- PostgreSQL and SQL features.
- Automatic time-based partitioning (hypertables).
- Compression and/or columnar storage options depending on version/configuration.
- Continuous aggregates (incrementally maintained materialized aggregates).
- Useful for server metrics, IoT, and financial time-series data.

### Search (Elasticsearch)

A full-text search engine built on Apache Lucene. Often used alongside a primary transactional database.

- Inverted index (each term → documents containing that term).
- Near-real-time indexing and search visibility.
- Text analysis (stemming, tokenization, fuzzy matching).
- Useful for product search, log analysis (ELK stack), and autocomplete.

### Interview Questions — Topic 40

**Q1: Name several NoSQL database types and one example of each.**
A: Key-value (Redis) for caching/sessions; document (MongoDB) for CMS/profiles; wide-column (Cassandra) for high-volume event data; graph (Neo4j) for relationships/fraud analysis; time-series (TimescaleDB) for metrics; and search (Elasticsearch) for text search and log analytics.

**Q2: When would you choose Cassandra?**
A: For high write throughput, multi-datacenter deployments, horizontal scaling across nodes, and fault tolerance. It is not a natural fit for complex relational joins, or small projects that do not need distributed scale. Design consistency and transactions around the guarantees Cassandra actually offers.

---

# PART 9: PRODUCTION DATABASE PATTERNS

---

## TOPIC 41: Connection Pooling in Depth

Most fundamentals were covered in Topic 30. Here we add production-specific details.

### Pool Sizing in Practice

```python
# SQLAlchemy production configuration
engine = create_engine(
    DATABASE_URL,
    pool_size=20,           # persistent pool
    max_overflow=10,        # temporary connections (up to 30 total)
    pool_timeout=30,        # max wait for a free connection (QueuePool)
    pool_recycle=1800,      # recycle after 30 minutes (avoid stale connections)
    pool_pre_ping=True,     # check connection health before use
)
```

#### pool_pre_ping

Without pre_ping, the first query may fail after the database restarts or a firewall drops an idle connection. With pre_ping, SQLAlchemy checks connectivity on checkout (often through a lightweight ping or query). There is some overhead, but it reduces stale-connection errors.

#### pool_recycle

Some databases (especially MySQL) close connections after a `wait_timeout`. If a pool holds a connection too long, it may become stale. `pool_recycle=1800` replaces connections once they exceed 30 minutes of age when checked out.

### Health Check Endpoint

```python
@app.get("/health")
async def health_check():
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "healthy", "db": "connected"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "db": str(e)}
        )
```

### Monitoring the Pool

```python
# SQLAlchemy pool status
pool = engine.pool
print(f"Pool size: {pool.size()}")
print(f"Checked out: {pool.checkedout()}")
print(f"Overflow: {pool.overflow()}")
print(f"Checked in: {pool.checkedin()}")
```

### Interview Questions — Topic 41

**Q1: What is pool_pre_ping, and why is it useful?**
A: When a pooled connection is checked out, SQLAlchemy tests whether it is alive. Without this, a dropped idle connection can cause the first query to fail. A lightweight ping adds some overhead but improves resilience to connection resets.

---

## TOPIC 42: Read Replicas, WAL, Streaming Replication

### Write-Ahead Log (WAL)

PostgreSQL records changes in the WAL before the corresponding modified table pages are persisted. This supports Durability (the D in ACID).

```
1. Client: UPDATE employees SET salary = 90000 WHERE id = 1
2. PostgreSQL: write the change to WAL (sequential and efficient)
3. PostgreSQL: return "COMMIT OK" to the client
4. PostgreSQL: later flush the relevant modified data pages to disk
5. If the server crashes between steps 3 and 4, recovery replays WAL
```

WAL is also used for:
- **Replication** — stream WAL to replicas.
- **Point-in-Time Recovery** — restore to a particular earlier point.
- **Logical decoding** — Change Data Capture (CDC).

### Streaming Replication

A primary server continuously sends WAL data to one or more replicas.

```
[Primary/Master]  ──WAL stream──→  [Replica 1 (read-only)]
                  ──WAL stream──→  [Replica 2 (read-only)]
```

#### Synchronous vs Asynchronous Replication

**Asynchronous (default):** The primary does not wait for the replica to acknowledge every commit. Commits are faster, but replicas may lag and failover can lose recently committed data.

**Synchronous:** The primary waits for acknowledgment from designated synchronous standby server(s), according to the configured mode. This improves failover durability guarantees but increases commit latency; the exact guarantee depends on configuration.

### Read Replicas in an Application

```python
# Two engines: one for writes, one for reads
write_engine = create_engine("postgresql://primary:5432/mydb")
read_engine = create_engine("postgresql://replica:5432/mydb")

# Write operations go to the primary
with Session(write_engine) as session:
    emp = Employee(name="Ana", salary=85000)
    session.add(emp)
    session.commit()

# Read operations go to a replica (less load on primary)
with Session(read_engine) as session:
    employees = session.scalars(select(Employee)).all()
```

**CAUTION: Read-after-write consistency!** If you write to the primary and immediately read from a replica, it may not have replayed the change yet (replication lag). Use the primary for read-after-write operations that require immediate consistency.

### Interview Questions — Topic 42

**Q1: What is WAL, and why does it exist?**
A: Write-Ahead Logging records changes before the corresponding data pages are written. It supports crash recovery and durability. WAL also underpins physical replication and Point-in-Time Recovery.

**Q2: What is replication lag, and what problem does it cause?**
A: Replication lag is the delay between a change committing on the primary and becoming available on a replica. A read-after-write request may therefore see stale data. Mitigations include routing consistency-critical reads to the primary, monitoring lag, or using stronger replication guarantees as appropriate.

---

## TOPIC 43: Database Migrations in Production (Zero Downtime)

### The Problem

A typical migration:

```
1. Deploy new code (expects a new column)
2. Run the migration (add the column)
3. Between steps 1 and 2: ERROR! Code references a nonexistent column
```

### Solution: Expand–Contract Pattern

Migration across **multiple deployments**:

**Deploy 1 — Expand:**
1. Add the new column (often nullable initially, with suitable defaults).
2. Update code to write to both old and new columns.
3. Backfill historical data into the new column.

**Deploy 2 — Contract:**
1. Ensure code no longer depends on the old column.
2. Drop the old column only when safe.

### Example: Renaming a Column (name → full_name)

```python
# Migration 1: add a new column
def upgrade():
    op.add_column('users', sa.Column('full_name', sa.String(200)))
    # Backfill
    op.execute("UPDATE users SET full_name = name WHERE full_name IS NULL")

# Deploy 1: code writes to both columns
def create_user(name):
    db.execute("INSERT INTO users (name, full_name) VALUES (%s, %s)", (name, name))

# Migration 2: add a NOT NULL constraint
def upgrade():
    op.alter_column('users', 'full_name', nullable=False)

# Deploy 2: code uses only full_name
# Migration 3: drop the old column
def upgrade():
    op.drop_column('users', 'name')
```

### Risky Migrations

| Operation | Risk | Solution |
|-----------|-------|---------|
| DROP COLUMN | application code still uses it | expand–contract across deployments |
| ADD COLUMN NOT NULL without planning/backfill | may fail or require locking and scanning | add nullable, backfill, then add constraint safely |
| ADD INDEX | ordinary build can block writes | `CREATE INDEX CONCURRENTLY` (PostgreSQL) |
| ALTER COLUMN TYPE | may rewrite the table | new column + backfill + switch |
| RENAME COLUMN | old application code uses the previous name | compatibility phase + coordinated rollout |

#### CREATE INDEX CONCURRENTLY

```sql
-- RISKY (blocks table writes):
CREATE INDEX idx_users_email ON users (email);

-- SAFER (allows concurrent writes):
CREATE INDEX CONCURRENTLY idx_users_email ON users (email);
-- Slower, but does not block normal writes
-- Cannot run inside a transaction block (Alembic needs an autocommit block)
```

### Interview Questions — Topic 43

**Q1: How do you perform zero-downtime migrations?**
A: Use expand–contract across deployments. (1) Expand: introduce new schema elements without removing old ones; deploy code compatible with both. (2) Contract: after all application instances use the new schema, remove obsolete columns/tables. Do not drop a column in the same rollout while old code may still use it.

**Q2: Why can CREATE INDEX be risky in production?**
A: Regular CREATE INDEX can block writes while the index is built, which may take a long time on a large table. In PostgreSQL, `CREATE INDEX CONCURRENTLY` generally allows ongoing writes but takes longer and cannot run inside a transaction block.

---

## TOPIC 44: Backup, Recovery, Point-in-Time Recovery (PITR)

### Backup Types

#### pg_dump (Logical Backup)

```bash
# Back up the entire database
pg_dump -h localhost -U postgres mydb > backup.sql

# Custom format (compressed; supports parallel restore)
pg_dump -Fc -h localhost -U postgres mydb > backup.dump

# A single table only
pg_dump -t employees -h localhost -U postgres mydb > employees.sql

# Schema only (no data)
pg_dump --schema-only mydb > schema.sql

# Data only (no schema)
pg_dump --data-only mydb > data.sql
```

```bash
# Restore
psql -h localhost -U postgres mydb < backup.sql

# Custom-format restore (parallel)
pg_restore -j 4 -h localhost -U postgres -d mydb backup.dump
```

**Advantages:** Portable and selective (tables/schemas); useful across supported versions.
**Disadvantages:** Can be slow for very large databases; a dump represents a consistent snapshot, but is not a substitute for continuous backup/PITR.

#### pg_basebackup (Physical Backup)

Copies PostgreSQL's physical data files with the required recovery data. Useful for larger databases and physical recovery.

```bash
pg_basebackup -h localhost -U replication -D /backups/base -Ft -z -P
# -Ft: tar format
# -z: compression
# -P: progress display
```

#### Continuous Archiving (WAL Archiving)

Combines a base backup with archived WAL for Point-in-Time Recovery.

```
Base backup (Sunday)  +  WAL files (continuous archive)
       ↓                        ↓
  State on Sunday     +   All changes since Sunday
       ↓
  Restore to a RECOVERABLE POINT IN TIME!
```

### Point-in-Time Recovery (PITR)

```
Someone accidentally ran: DROP TABLE users; (at 14:35)

With PITR:
1. Restore this morning's base backup (06:00)
2. Replay WAL records up to 14:34 (before the DROP)
3. The database is restored to a point before the accidental DROP!
```

### Production Backup Strategy

```
Daily:    physical base backup (frequency based on recovery targets)
Ongoing:  WAL archiving (continuous)
Weekly:   pg_dump selected tables (for easier individual-object restores)
Monthly:  Test restoration in staging! (an untested backup is not dependable)
```

### The 3-2-1 Backup Rule

- **3** copies of the data.
- **2** different storage media or systems.
- **1** off-site copy (another data center/region).

### Interview Questions — Topic 44

**Q1: What is Point-in-Time Recovery (PITR)?**
A: The ability to restore a database to a chosen point in its recoverable history. It combines a base backup with a continuous archive of WAL records. Restore the base backup, then replay WAL to the desired moment. It is critical for recovery from accidental changes such as DROP TABLE or an incorrect mass UPDATE.

**Q2: What is the difference between pg_dump and pg_basebackup?**
A: pg_dump is a logical export, flexible and portable for selected objects or complete databases. pg_basebackup creates a physical base backup and can be combined with WAL archiving for PITR. For small databases a logical backup may be sufficient; for production, choose backups according to recovery time and recovery point objectives.

---

## TOPIC 45: Monitoring and Alerting

### Key Monitoring Metrics

#### 1. Connections

```sql
-- Current connections
SELECT count(*) FROM pg_stat_activity;

-- Grouped by session state
SELECT state, count(*) FROM pg_stat_activity GROUP BY state;
-- active: executing a query
-- idle: waiting
-- idle in transaction: transaction open but not executing (DANGEROUS!)

-- Maximum allowed connections
SHOW max_connections;

-- Alert if > 80% of max_connections
```

**"Idle in transaction"** sessions can hold locks and delay cleanup by VACUUM. Configure `idle_in_transaction_session_timeout`:

```sql
SET idle_in_transaction_session_timeout = '5min';
```

#### 2. Query Performance

```sql
-- Slow queries (past hour)
SELECT pid, now() - query_start AS duration, LEFT(query, 100)
FROM pg_stat_activity
WHERE state = 'active' AND now() - query_start > interval '5 seconds';

-- Configure slow query logging
-- postgresql.conf:
-- log_min_duration_statement = 1000   # log queries taking > 1 second
```

#### 3. Cache Hit Ratio

```sql
SELECT
    sum(heap_blks_hit) / NULLIF(sum(heap_blks_hit) + sum(heap_blks_read), 0) AS ratio
FROM pg_statio_user_tables;
-- Example reference: > 0.99 (99%); adjust for workload
-- If low, investigate memory size, working set, and query behavior
```

#### 4. Replication Lag

```sql
-- On the primary:
SELECT
    client_addr,
    state,
    pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn) AS send_lag_bytes,
    pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_lag_bytes
FROM pg_stat_replication;

-- Alert if replay lag exceeds the service threshold
```

#### 5. Disk Space

```sql
-- Database size
SELECT pg_size_pretty(pg_database_size('mydb'));

-- Top 10 tables by size
SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 10;

-- Alert if disk usage exceeds a chosen threshold
```

#### 6. Dead Tuples and VACUUM

```sql
SELECT relname, n_dead_tup, n_live_tup,
       ROUND(n_dead_tup::numeric / NULLIF(n_live_tup, 0) * 100, 2) AS dead_pct,
       last_autovacuum
FROM pg_stat_user_tables
WHERE n_dead_tup > 10000
ORDER BY n_dead_tup DESC;

-- Alert on sustained high dead-tuple ratio or lack of autovacuum activity
```

### Monitoring Tool Stack

```
Prometheus + Grafana:
  - postgres_exporter for PostgreSQL metrics
  - Dashboards for the metrics listed above
  - Alert rules for thresholds

pgwatch2:
  - Specialized PostgreSQL monitoring
  - Prebuilt dashboards

Datadog / New Relic:
  - SaaS solutions with PostgreSQL integrations
  - Query performance, slow query analysis
```

### Alert Thresholds (Illustrative)

| Metric | Warning | Critical |
|---------|---------|----------|
| Connection usage | > 70% | > 90% |
| Cache hit ratio | < 99% | < 95% |
| Replication lag | > 10s | > 60s |
| Disk usage | > 75% | > 90% |
| Long-running queries | > 30s | > 5min |
| Dead tuple ratio | > 10% | > 30% |
| Idle in transaction | > 1min | > 5min |

### Interview Questions — Topic 45

**Q1: Which PostgreSQL metrics would you monitor in production?**
A: Monitor (1) active connections vs max_connections, (2) cache behavior, (3) replication lag, (4) slow queries and total query load, (5) dead tuples and VACUUM, (6) disk usage, and (7) "idle in transaction" sessions. Prometheus with postgres_exporter and Grafana is one common stack. Set thresholds based on workload and service objectives.

**Q2: What is an "idle in transaction" session, and why is it dangerous?**
A: A session has begun a transaction but is currently doing no work. It can hold locks, delay VACUUM cleanup by retaining an old snapshot, and contribute to table bloat. Set `idle_in_transaction_session_timeout` to close such sessions when appropriate.

**Q3: How do you detect whether a replica is lagging behind the primary?**
A: On the primary, inspect `pg_stat_replication` for fields such as `sent_lsn`, `replay_lsn`, and `replay_lag` (the exact meaning and availability depend on PostgreSQL version and state). You can also compare LSN positions and measure byte lag. Alert thresholds should be chosen for your application's tolerance, not blindly set to universal values. Causes include network latency, replica load, and high write volume.
