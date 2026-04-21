---
name: Pipeline stack
type: fact
date: YYYY-MM-DD
---

# Stack

| Layer | Choice | Version | Notes |
|-------|--------|---------|-------|
| Orchestrator | Airflow / Dagster / Prefect | | |
| Transforms | dbt | | core / cloud? |
| Warehouse | Snowflake / BigQuery / Postgres | | |
| Ingestion | Fivetran / Airbyte / custom | | |
| Streaming | Kafka / Kinesis / ? | | |
| Observability | Monte Carlo / Elementary / custom | | |

## Conventions
- Naming: `<source>__<entity>` for staging, `<domain>_<entity>` for marts
- Testing: every mart has `not_null` + `unique` on PK
- CI: `dbt test` on PR, blocks merge on failure
