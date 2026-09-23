# WHO World News fetcher

This small Python script downloads the latest news directly from the World
Health Organization's public JSON API. It does not scrape HTML and does not
need an API key.

## Run it

Python 3.10 or newer is recommended. The script uses only Python's standard
library, so no package installation is required.

```powershell
python who_news.py
```

By default, the latest 10 records whose `news_type` contains `news`
(case-insensitive) are printed as JSON and stored in the local SQLite database
`data/who_news.db`. The pipeline pages through the mixed WHO newsroom feed
until it has collected the requested number of matching records. Repeated runs
update existing records by WHO article ID, so they do not create duplicates.

The database has two layers:

- `articles`: raw records returned by WHO.
- `stg_articles`: a staging view that keeps only records whose `news_type`
  contains `news`, using a case-insensitive SQL comparison.

The staging view is also defined as a dbt model in `staging/stg_articles.sql`.
The intermediate model in `intermediate/int_news_articles_enriched.sql`
normalizes the news type and adds parsed publication dates and article slugs.
The mart in `marts/mart_news_monthly_summary.sql` summarizes article counts and
active publication days by month and normalized news type.
After installing the project requirements, build it from the project root with:

```powershell
dbt build --profiles-dir .
```

To fetch 25 records and use a different database location:

```powershell
python who_news.py --limit 25 --database data/my_news.db
```

To fetch 200 records into the raw and staging layers:

```powershell
python who_news.py --limit 200
```

To also save the current response as JSON:

```powershell
python who_news.py --limit 25 --output data/who_news.json
```

To refresh the file every five minutes, until you press `Ctrl+C`:

```powershell
python who_news.py --limit 25 --output data/who_news.json --watch 300
```

The saved structure is:

```json
{
  "source": "https://www.who.int/api/news/newsitems",
  "fetched_at": "2026-09-10T15:00:00+00:00",
  "count": 1,
  "items": [
    {
      "id": "...",
      "title": "...",
      "news_type": "News release",
      "published_at": "2026-09-09T12:54:32Z",
      "formatted_date": "9 September 2026",
      "url": "https://www.who.int/news/item/..."
    }
  ]
}
```

The endpoint is live rather than a streaming feed: each run asks WHO for the
newest published records. `--watch` provides polling when a continuously
updated database and local file are needed.

## Fetch WHO Statements

`who_statements.py` pages through the WHO newsroom feed, keeps only records
whose news type is `Statement`, and upserts them into the dedicated
`articles/statement_news.db` SQLite database:

```powershell
python who_statements.py --limit 200 --output articles/latest_who_statements.json
```

The database contains a raw `statements` table and a filtered
`stg_statements` view. Repeated runs update existing WHO IDs instead of
creating duplicates. The command also supports `--database`, `--timeout`, and
`--watch` in the same way as the general news pipeline.

## Orchestrate with Airflow

The DAG in `dags/who_news_pipeline.py` runs every day at 06:00 UTC. It first
fetches 200 WHO records into `articles/who_news.db`, then runs `dbt build` so
the staging, intermediate, and mart views and their tests are refreshed.

### Run with Docker Desktop on Windows

Start Docker Desktop using Linux containers, then run this from the project
directory:

```powershell
docker compose up --build
```

Open <http://localhost:8080>, find `who_news_pipeline`, enable it, and use the
play button to trigger the first run. Authentication is disabled for this
localhost-only development setup. Stop the containers with:

```powershell
docker compose down
```

If Docker Desktop says that the WSL kernel is missing, open PowerShell as
Administrator, run the following command, and restart Docker Desktop (Windows
may also request a reboot):

```powershell
wsl --update --web-download
```

The Airflow metadata is kept in the `airflow_home` Docker volume, while the
WHO database and dbt outputs remain in this project directory.

### Run directly in Linux or WSL2

From a Linux environment with the project requirements installed:

```bash
export AIRFLOW_HOME="$PWD/.airflow"
export AIRFLOW__CORE__DAGS_FOLDER="$PWD/dags"
airflow standalone
```

If the DAG file is deployed separately from this repository, set
`WHO_NEWS_PROJECT_ROOT` to the absolute project directory visible to the
Airflow worker.

## Read the database

The `articles` table contains the title, type, publication time, WHO URL, and
timestamps showing when the application first and most recently saw each
record. For example, you can read the newest records from Python with:

```python
import sqlite3

with sqlite3.connect("data/who_news.db") as connection:
    rows = connection.execute(
        "SELECT title, published_at, url FROM articles "
        "ORDER BY published_at DESC LIMIT 10"
    ).fetchall()

for title, published_at, url in rows:
    print(published_at, title, url)
```

Official WHO API help: <https://www.who.int/api/news/newsitems/sfhelp>

## Test it

```powershell
python -m unittest discover -s tests -v
```
