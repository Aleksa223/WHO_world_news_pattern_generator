# WHO World News fetchers

The WHO scripts download the latest news and other public content from the
World Health Organization without an API key. A separate technology-news
fetcher uses the public Hacker News API without requiring a token.

## Run it

Python 3.10 or newer is recommended. The fetchers use only Python's standard
library, so no package installation is required to run them.

```powershell
python who_news_scripts/who_news.py
```

By default, up to 10 records whose `news_type` contains `news`
(case-insensitive) are printed as JSON and stored in the local SQLite database
`articles/who_news.db`. A first run starts with the newest records. Later runs
read the IDs already stored, page past them, and collect the next unseen batch.
WHO article IDs and SQLite upserts prevent duplicates, so the database can grow
beyond the per-run limit. The scheduled pipeline later applies the documented
one-year retention policy to the general WHO news table.

The database has two layers:

- `articles`: matching news records returned by WHO.
- `stg_articles`: a staging view that keeps only records whose `news_type`
  contains `news`, using a case-insensitive SQL comparison.

The dbt staging model for this source is `staging/who/who_stg_news.sql`. The news
transformation in `intermediate/who_int_news_articles.sql` normalizes the
news type and adds parsed publication dates and article slugs. The combined
model in `intermediate/who_int_content.sql` unifies all seven WHO content
sources, and `intermediate/who_int_title_topics.sql` extracts literal title
words plus conservative canonical topic families. The marts in
`marts/who/who_mart_news_monthly_summary.sql` and
`marts/who/who_mart_top_topics_by_category.sql` summarize the combined content.
`who_mart_top_title_words` and `who_mart_top_title_topics` provide the expanded
top-20 literal and grouped views within each WHO content category.
Raw WHO, Hacker News, and GDELT records remain in their source databases,
while dbt writes its staging, intermediate, seed, and mart relations to
`warehouse/analytics.db`. dbt keeps Tech and Economic article change history
separately in `warehouse/snapshot_history.db`.
After installing the project requirements, build it from the project root with:

```powershell
dbt build --profiles-dir .
```

To fetch 25 records and use a different database location:

```powershell
python who_news_scripts/who_news.py --limit 25 --database articles/who_my_news.db
```

To fetch 200 records into the raw and staging layers:

```powershell
python who_news_scripts/who_news.py --limit 200
```

To also save the current response as JSON:

```powershell
python who_news_scripts/who_news.py --limit 25 --output articles/who_latest_news.json
```

To refresh the file every five minutes, until you press `Ctrl+C`:

```powershell
python who_news_scripts/who_news.py --limit 25 --output articles/who_latest_news.json --watch 300
```

The saved structure is:

```json
{
  "source": "https://www.who.int/api/news/newsitems",
  "fetched_at": "2026-09-10T15:00:00+00:00",
  "count": 1,
  "scanned": 1,
  "skipped_existing": 0,
  "scan_limit_reached": false,
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

The endpoint is live rather than a streaming feed. Each run starts at WHO's
newest records, refreshes a bounded set of IDs already in the destination, and
continues until it has found the requested unseen batch or exhausted the
available source data. `--watch` repeats that incremental process on the
configured interval.

## Fetch WHO Statements

`who_news_scripts/who_statements.py` pages through the WHO newsroom feed, keeps
only records whose news type is `Statement`, and upserts them into the
dedicated `articles/who_statement_news.db` SQLite database:

```powershell
python who_news_scripts/who_statements.py --limit 200 --output articles/who_latest_statements.json
```

The database contains a raw `statements` table and a filtered
`stg_statements` view. Repeated runs refresh encountered WHO IDs and page to
the next unseen statements without creating duplicates. The command also
supports `--database`, `--timeout`, and `--watch` in the same way as the
general news pipeline.

## Fetch WHO Campaigns

`who_news_scripts/who_campaigns.py` reads campaign cards from WHO's official
campaigns index and upserts their titles and URLs into
`articles/who_campaign_news.db`:

```powershell
python who_news_scripts/who_campaigns.py --limit 25 --output articles/who_latest_campaigns.json
```

Campaigns are stored in a raw `campaigns` table and a filtered
`stg_campaigns` view. The command also supports `--database`, `--timeout`, and
`--watch`.

## Fetch WHO Events

`who_news_scripts/who_events.py` follows WHO's official paginated events
listing and upserts event titles, displayed dates, and URLs into
`articles/who_event_news.db`:

```powershell
python who_news_scripts/who_events.py --limit 25 --output articles/who_latest_events.json
```

Events are stored in a raw `events` table and a filtered `stg_events` view.
The command also supports `--database`, `--timeout`, and `--watch`.

## Fetch WHO Feature Stories

`who_news_scripts/who_feature_stories.py` pages through WHO's public Feature
Stories API and upserts story titles, publication dates, URLs, and thumbnails
into `articles/who_stories_news.db`:

```powershell
python who_news_scripts/who_feature_stories.py --limit 200 --output articles/who_latest_feature_stories.json
```

Feature stories are stored in a raw `feature_stories` table and a filtered
`stg_feature_stories` view. The command also supports `--database`,
`--timeout`, and `--watch`.

## Fetch WHO Speeches

`who_news_scripts/who_speeches.py` pages through WHO's public Speeches API and
upserts speech titles, publication dates, tags, subtitles, URLs, and thumbnails
into `articles/who_speech_news.db`:

```powershell
python who_news_scripts/who_speeches.py --limit 200 --output articles/who_latest_speeches.json
```

Speeches are stored in a raw `speeches` table and a filtered `stg_speeches`
view. The command also supports `--database`, `--timeout`, and `--watch`.

## Fetch WHO Commentaries

`who_news_scripts/who_commentaries.py` pages through WHO's public Commentaries
API and upserts commentary titles, publication dates, URLs, and thumbnails
into `articles/who_commentary_news.db`:

```powershell
python who_news_scripts/who_commentaries.py --limit 200 --output articles/who_latest_commentaries.json
```

Commentaries are stored in a raw `commentaries` table and a filtered
`stg_commentaries` view. The command also supports `--database`, `--timeout`,
and `--watch`.

## Fetch technology news

`tech_news_scripts/tech_news.py` fetches recent stories from the official
[Hacker News API](https://github.com/HackerNews/API). The public API does not
require a token. Run the fetcher from the project root:

```powershell
python tech_news_scripts/tech_news.py --output tech_articles/tech_news.json
```

The default request retrieves up to 200 unseen items from the current
`newstories` feed and refreshes up to 200 stored stories still present there.
It stores them in `tech_articles/tech_news.db`, allowing repeated runs to move
deeper through the feed while keeping mutable scores, comment counts, titles,
and feed ranks current. Records are upserted by Hacker News item ID into the
`tech_articles` table and exposed through the
`stg_tech_articles` view. Stored fields include the article and discussion
URLs, author, publication time, score, and comment count. Self-posts without an
external URL use their Hacker News discussion URL.

Use `--limit` to request between 1 and 500 stories, `--workers` to control
concurrent item requests, `--output tech_articles/tech_news.json` to save the
response as JSON, and `--watch` to poll repeatedly.

The dbt staging and mart layers are organized by source: WHO models live under
`staging/who/` and `marts/who/`, while Hacker News models live under
`staging/tech/` and `marts/tech/`. Hacker News
items are split into `tech_stg_story`, `tech_stg_comment`, `tech_stg_job`,
`tech_stg_poll`, and `tech_stg_pollopt` according to `item_type`. The current
fetcher loads the `newstories` feed, so `tech_stg_story` is populated while the
other four models remain ready for future ingestion of those API item types.
`tech_mart_daily_story_summary` reports daily volume and engagement, while
`tech_mart_top_stories` ranks the ten highest-engagement stories per day.
`tech_int_title_topics` extracts significant title words, while
`tech_mart_top_title_words` and `tech_mart_top_title_topics` rank literal words
and conservative word families. The tokenizer preserves common punctuation-
sensitive names such as C++, C#, .NET, and Node.js before splitting titles.
Refresh the Hacker News staging, title-analysis seeds, intermediate model, and
marts with:

```powershell
dbt build --select tech_title_stopwords tech_title_topic_map path:staging/tech path:intermediate/tech path:marts/tech --profiles-dir .
```

Query the grouped Tech or WHO title topics directly:

```powershell
sqlite3 -header -column warehouse/analytics.db "SELECT topic_rank, topic, grouped_words, unique_title_count, story_count FROM tech_mart_top_title_topics ORDER BY topic_rank;"
sqlite3 -header -column warehouse/analytics.db "SELECT category, topic_rank, topic, grouped_words, unique_title_count, content_count FROM who_mart_top_title_topics ORDER BY category, topic_rank;"
```

The technology-news fetcher can be run standalone with the command above. It is
also included in the daily Airflow pipeline described below.

## Fetch economic news

`economic_news_scripts/economic_news.py` searches the free GDELT DOC 2.0 API
for recent reporting about the economy, inflation, GDP, unemployment,
recessions, interest rates, central banks, and fiscal policy. GDELT does not
require an API key. Every request includes GDELT's `sourcelang:english` query
operator, and the fetcher also discards any response row that is not labeled
as English. New fetches therefore store only English-source article titles.
Run the fetcher from the project root:

```powershell
python economic_news_scripts/economic_news.py --output economic_articles/economic_news.json
```

The default request retrieves up to 200 results from the previous day and
upserts them into `economic_articles/economic_news.db`. Articles are
deduplicated using a stable hash of their canonical URL. The database contains
the raw `economic_articles` table and a filtered `stg_economic_articles` view.
Existing non-English records from earlier runs are preserved; fetching again
does not delete them, but no new non-English records are added.
Stored fields include title, URL, source domain and country, language, image,
GDELT observation time, query, and ingestion timestamps. The title fields have
distinct purposes: `title` is the display value (English after translation),
`title_original` preserves the source text, and `title_english` stores the
English result. `translation_status` is `original_english` for source titles
already in English, `pending` before translation, `translated` after a
successful Azure request, or `failed` when an attempted translation could not
be completed.

Use `--limit` to request up to 250 results, `--timespan` to select a window such
as `1week`, `--query` to replace the default economic search expression,
`--output` to save the response as JSON, and `--watch` to poll repeatedly.
The English source-language filter remains mandatory when `--query` is used.
GDELT requests must be at least five seconds apart, so shorter watch intervals
are rejected.

### Translate economic titles with Azure

The translator uses the Azure Translator Text API v3 and batches pending titles
to reduce the number of requests. Create a Translator resource in Azure, then
set its credentials in the current PowerShell session. The subscription key is
a secret: never paste it into source files or commit it to Git.

```powershell
$env:AZURE_TRANSLATOR_KEY = "<your-translator-key>"
$env:AZURE_TRANSLATOR_REGION = "<your-resource-region>"
$env:AZURE_TRANSLATOR_ENDPOINT = "https://api.cognitive.microsofttranslator.com"
```

`AZURE_TRANSLATOR_KEY` is required. `AZURE_TRANSLATOR_REGION` is required for a
regional or Azure AI multi-service resource and may be omitted for a global
Translator resource. `AZURE_TRANSLATOR_ENDPOINT` is optional and defaults to
the global endpoint shown above; set it to the endpoint from the Azure portal
when your resource uses a custom endpoint. `.env.example` documents the names,
but the scripts read the actual values from the process environment rather than
loading that file automatically.

Translate pending titles already stored in the database:

```powershell
python economic_news_scripts/azure_translate.py
```

Fetch articles and translate new pending titles in one run:

```powershell
python economic_news_scripts/economic_news.py --translate --output economic_articles/economic_news.json
```

Azure currently lists up to 2 million characters per month for the F0 tier,
but quotas and prices can change. Check the
[official Azure Translator pricing page](https://azure.microsoft.com/en-us/pricing/details/translator/)
before relying on that allowance. See Microsoft's
[Translator v3 REST reference](https://learn.microsoft.com/en-us/azure/ai-services/translator/text-translation/reference/v3/translate)
for the request and batching behavior.

Query the downloaded articles directly with:

```powershell
sqlite3 -header -column economic_articles/economic_news.db "SELECT title, source, source_country, published_at FROM economic_articles ORDER BY published_at DESC LIMIT 10;"
```

The economic-news fetcher can be run standalone with the command above. It is
also included in the daily Airflow pipeline. Its dbt source and
`economic_stg_articles` model live under `staging/economic/`. The models under
`marts/economic/` provide a daily publisher-country summary and a daily ranking
of the ten source domains contributing the most feed results.
`economic_mart_top_titles` ranks exact repeated titles,
`economic_mart_top_title_words` ranks literal title words, and
`economic_mart_top_title_topics` groups conservative word variants such as
`stock` and `stocks`. Word and topic ranks use distinct-title counts first so
that one heavily syndicated headline does not dominate; article-copy and source
counts remain available alongside them.
Their `observation_date` is based on GDELT's observation timestamp and should
not be interpreted as a guaranteed publisher publication date. Refresh the
economic staging, title-analysis seeds, intermediate model, and marts after
ingestion with:

```powershell
dbt build --select economic_title_stopwords economic_title_topic_map path:staging/economic path:intermediate/economic path:marts/economic --profiles-dir .
```

Query the most common literal words or the grouped word families directly:

```powershell
sqlite3 -header -column warehouse/analytics.db "SELECT word_rank, title_word, unique_title_count, article_count FROM economic_mart_top_title_words ORDER BY word_rank;"
sqlite3 -header -column warehouse/analytics.db "SELECT topic_rank, topic, grouped_words, unique_title_count, article_count FROM economic_mart_top_title_topics ORDER BY topic_rank;"
```

## Query all news in one mart

`all_news_mart_articles` combines WHO content, Hacker News stories, and
English-language GDELT economic articles into one shared schema. Its grain is
one row per source record. `article_key` prefixes the source key with `who:`,
`tech:`, or `economic:` so it remains unique across streams. `news_type`
identifies the stream, `content_type` identifies the source record kind, and
`topic` provides the broad `health`, `technology`, or `economic` domain.

The mart does not collapse similar headlines across publishers. It preserves
the source records and their URLs, while the existing source ingestion prevents
duplicate IDs or canonical URLs within each raw database. `fetched_at` and
`last_seen_at` identify the most recent ingestion that wrote a row; incremental
WHO and Hacker News scans do not rewrite IDs they skip as already stored. WHO
campaigns may have no publication date, and GDELT's
`published_at` value is an observation-time proxy; use `observation_date` for
a consistently populated reporting date. The scheduled retention policy keeps
general WHO news for 365 days and Hacker News stories plus economic articles
for 90 days. The other WHO content types can therefore contain older records
in this combined mart.

Build this mart together with its upstream models and tests:

```powershell
dbt build --select +all_news_mart_articles --profiles-dir .
```

Query recent records or daily counts from `warehouse/analytics.db`:

```powershell
sqlite3 -header -column warehouse/analytics.db "SELECT news_type, content_type, title, source, observation_date FROM all_news_mart_articles ORDER BY observed_at DESC LIMIT 20;"
sqlite3 -header -column warehouse/analytics.db "SELECT observation_date, topic, COUNT(*) AS article_count FROM all_news_mart_articles GROUP BY observation_date, topic ORDER BY observation_date DESC, topic;"
```

## Track article changes with dbt snapshots

The project has two dbt snapshots in `snapshots/news_history.yml`:

- `tech_article_history` records meaningful Hacker News changes such as score,
  comment count, title, author, and publication metadata.
- `economic_article_history` records meaningful GDELT changes such as title,
  translation state, description, source, and publication metadata.

The snapshots use dbt's `check` strategy and write slowly changing dimension
type 2 history to `warehouse/snapshot_history.db`. Ingestion-only fields such
as `last_seen_at` are deliberately excluded, so simply seeing the same article
again does not create a new version. If a checked value changes, dbt closes the
old version and inserts a new current version. If a source row is deleted by
retention, dbt invalidates its current version instead of deleting its history.

Build both snapshots and run their tests with:

```powershell
dbt build --select path:snapshots --profiles-dir .
```

You can also use `dbt snapshot --profiles-dir .` when you only want to capture
changes, but `dbt build` is preferred here because it also runs the snapshot
tests. Each row has `dbt_valid_from` and `dbt_valid_to`; a null
`dbt_valid_to` means that the version is current. For example:

```powershell
sqlite3 -header -column warehouse/snapshot_history.db "SELECT id, title, score, comment_count, dbt_valid_from, dbt_valid_to FROM tech_article_history WHERE id = '<article-id>' ORDER BY dbt_valid_from;"
sqlite3 -header -column warehouse/snapshot_history.db "SELECT id, title, dbt_valid_from FROM economic_article_history WHERE dbt_valid_to IS NULL ORDER BY dbt_valid_from DESC LIMIT 20;"
```

Snapshot history starts with the first snapshot run; it cannot reconstruct
changes that happened earlier. It intentionally outlives the 90-day raw Tech
and Economic retention window. Add a separate history-retention policy if that
indefinite history is not desired.

## Orchestrate with Airflow

When an Airflow scheduler is running, the DAG in `dags/who_news_pipeline.py`
runs every day at 06:00 UTC. It starts the seven WHO fetchers plus the Hacker
News and GDELT economic-news fetchers in parallel, writing each source to its
SQLite database configured in `profiles.yml`. After all nine fetch tasks
succeed, it runs `dbt build` across the WHO, Tech, and Economic staging,
intermediate, mart, seed, and snapshot resources and their tests, refreshing
`warehouse/analytics.db` and capturing article changes in
`warehouse/snapshot_history.db`. A failed fetch is retried twice and prevents
dbt from building a partial daily refresh.

Every fetch task requests a batch of up to 200 unseen records per daily run.
This is not a 200-row database limit. WHO and Hacker News also refresh a
bounded set of stored records encountered in the current source, keeping
mutable metadata current while they continue paging for unseen IDs. Every raw
SQLite database retains earlier rows and deduplicates by its source ID or
canonical URL, so it can grow well beyond 200 rows without storing duplicates.
A source may add fewer than 200 rows when its current feed is exhausted, an
item fails validation, or no unseen source records exist. The JSON output files
are latest-run snapshots and are overwritten on the next run; retained history
is stored in SQLite.

After every scheduled fetch, Airflow deletes general WHO news older than 365
days and Hacker News stories or economic articles older than 90 days before
rebuilding dbt. Each database receives its own cutoff. A row exactly on its
cutoff is retained, as are rows with missing or invalid dates. Campaigns,
events, speeches, statements, commentaries, and feature stories are not cleaned
automatically because their date semantics are not all equivalent. The
incremental fetch can briefly re-ingest an older upstream record, but the same
DAG run removes it before refreshing `warehouse/analytics.db`.

Preview the cleanup without deleting anything:

```powershell
python maintenance_scripts/cleanup_old_articles.py --dry-run
```

Run the same cleanup manually with:

```powershell
python maintenance_scripts/cleanup_old_articles.py
```

Passing `--retention-days N` is an explicit override that applies `N` days to
all three cleaned databases. Without that option, the source-specific 365/90
day policy above is used.

SQLite reuses pages freed by deletion, so the database file may not immediately
become smaller on disk. Neither the scheduled nor manual cleanup runs `VACUUM`.

### Inspect ingestion runs

Every fetch or watch-loop iteration writes an `ingestion_audit` record into the
same raw SQLite database as its source data. The record includes the requested
and selected row counts, newly inserted and refreshed rows, retention
deletions, total database rows, oldest and newest valid publication times,
articles published on that UTC date, and a `running`, `succeeded`, or `failed`
status. Airflow passes one shared `pipeline_run_id` to all nine fetchers, while
manual fetches receive a generated `manual:` run ID. Error messages are
whitespace-normalized and limited to 2,000 characters.

Campaigns and events do not have a reliable raw publication-time field, so
their oldest, newest, and published-today metrics are intentionally null. Raw
audit history is preserved automatically with the existing raw-database state
snapshots.

dbt unions all nine raw audit tables into `ops_mart_ingestion_runs` in
`warehouse/analytics.db`. Build or refresh it and inspect recent runs with:

```powershell
dbt build --select +ops_mart_ingestion_runs --profiles-dir .
sqlite3 -header -column warehouse/analytics.db "SELECT pipeline_run_id, source_name, status, new_rows, refreshed_rows, deleted_rows, total_rows, published_today_rows, oldest_published_at, newest_published_at FROM ops_mart_ingestion_runs ORDER BY started_at DESC LIMIT 30;"
```

If a scheduled fetch fails, dbt correctly skips the partial warehouse refresh.
That failure is available immediately in the affected raw database and appears
in the unified operations mart after the next successful dbt build. For
example:

```powershell
sqlite3 -header -column tech_articles/tech_news.db "SELECT pipeline_run_id, status, error_type, error_message, started_at FROM ingestion_audit ORDER BY started_at DESC LIMIT 10;"
```

To create a one-time baseline for raw databases that predate auditing, run:

```powershell
python maintenance_scripts/ingestion_audit.py --run-id bootstrap
```

### Run while your computer is off with GitHub Actions

The workflow in `.github/workflows/daily-news.yml` runs the complete Airflow
DAG on a GitHub-hosted Linux machine every day at 06:17 UTC. The non-zero minute
reduces the chance of GitHub's top-of-hour scheduling delays. It can also be
started manually from the repository's **Actions** tab. Your computer and
Docker Desktop do not need to be running.

GitHub-hosted runners are temporary, so the workflow stores the nine raw SQLite
databases plus `warehouse/snapshot_history.db` as a validated
`raw-sqlite-state` workflow artifact after a successful run. The next run
restores that state before fetching. The state snapshot uses SQLite's backup
API, checks each database and expected table, and includes checksums in
`manifest.json`. Legacy state artifacts containing only the nine raw databases
are still accepted once for migration. `warehouse/analytics.db` is deliberately
rebuilt from raw data rather than restored, then it and the snapshot-history
database are uploaded with the latest JSON files as a separate
`news-analytics-<run-id>` artifact.

To enable cloud scheduling:

1. Commit and push the complete project, including `.github/workflows/`, to the
   repository's `main` branch.
2. Open the GitHub repository, select **Actions**, then enable workflows if
   GitHub asks.
3. Select **Daily News Pipeline**, choose **Run workflow**, and leave
   `reset_state` disabled for the first run. With no previous cloud snapshot,
   the workflow creates fresh databases from the public APIs.
4. Download a completed analytics database from the workflow run's
   **Artifacts** section when needed.

Pipeline state is retained for 90 days and downloadable analytics output for
14 days. If no usable state snapshot remains, manually run the workflow with
`reset_state` enabled to bootstrap fresh cloud state. Scheduled GitHub Actions
are best-effort rather than an exact-time service, and public-repository
schedules can be disabled after 60 days without repository activity. For a
strict production schedule or permanent state history, deploy the same Docker
setup to an always-on VM and use persistent storage.

This repository is public, so treat its downloadable workflow artifacts as
public data. The workflow stores public-source news data only; never put API
keys or other secrets into the databases or JSON output files.

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

The Airflow metadata is kept in the `airflow_home` Docker volume. Raw WHO data
remains under `articles/`, raw Hacker News data remains under
`tech_articles/`, raw economic news remains under `economic_articles/`, and
dbt outputs are written to `warehouse/analytics.db` and
`warehouse/snapshot_history.db`.

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

with sqlite3.connect("articles/who_news.db") as connection:
    rows = connection.execute(
        "SELECT title, published_at, url FROM articles "
        "ORDER BY published_at DESC LIMIT 10"
    ).fetchall()

for title, published_at, url in rows:
    print(published_at, title, url)
```

The transformed dbt relations are stored separately in
`warehouse/analytics.db`. For example, `who_mart_news_monthly_summary`,
`tech_mart_daily_story_summary`, and `tech_mart_top_stories` can be queried
from that database without modifying either raw source database. Historical
Tech and Economic article versions are stored in
`warehouse/snapshot_history.db`.

Official WHO API help: <https://www.who.int/api/news/newsitems/sfhelp>

## Test it

```powershell
python -m unittest discover -s tests -v
```
