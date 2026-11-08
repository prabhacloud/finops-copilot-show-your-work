# FinOps Copilot: Show Your Work

A small, auditable reference implementation for answering AWS cost questions
without treating model-generated SQL as truth.

![FinOps Copilot hero: question, validation, query, and evidence](assets/finops-copilot-hero.png)

The core pattern is deliberately simple:

```text
natural-language question
        ↓
model proposes a constrained JSON plan
        ↓
deterministic validator + allowlists
        ↓
reviewable Athena SQL + evidence record
        ↓
human or controlled service decides whether to execute
```

This repository accompanies the article
[`Your FinOps Copilot Should Show Its Work`](ARTICLE.md).

![Reference architecture for the governed query path](assets/finops-copilot-architecture.png)

## What this demo proves

- A model can be limited to a narrow query contract instead of being allowed to
  write arbitrary SQL.
- Metrics, dimensions, filters, date ranges, and result limits can be validated
  before a query is produced.
- A deterministic compiler can generate readable Athena SQL and an evidence
  record from the same validated plan.
- The result can be exercised locally against synthetic CUR-like data without
  an AWS account.

## What this demo does not claim

- The CSV is **synthetic**. It is not an AWS Cost and Usage Report and contains
  no customer or billing data.
- The local evaluator is not an Athena emulator.
- No production benchmarks, accuracy rates, savings figures, or deployment
  results are claimed.
- The CloudFormation template is a learning scaffold. Review it against your
  organization's security, tagging, retention, and FinOps policies before use.
- The sample Lambda can generate SQL but has no permission to execute Athena.

## Repository map

```text
.
├── ARTICLE.md
├── data/synthetic_cur.csv
├── example-plan.json
├── infra/template.yaml
├── src/finops_copilot/
│   ├── demo.py
│   ├── local.py
│   ├── plan.py
│   └── sql.py
└── tests/
```

## Run the local demo

Python 3.10 or newer is sufficient; the package has no runtime dependencies.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
finops-demo
```

Or pass a different allowlisted plan:

```bash
finops-demo --plan example-plan.json
```

The command prints:

1. the validated evidence record;
2. the generated Athena SQL; and
3. a local result computed from `data/synthetic_cur.csv`.

It ends with `No AWS API was called.`

## Run the tests

Using only the standard library:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The tests cover accepted plans, rejected unknown keys, unsupported metrics,
unsafe identifiers, escaped string literals, bounded limits, and a
deterministic result from the synthetic data.

## The model contract

A model is expected to propose JSON shaped like this:

```json
{
  "metric": "amortized_cost",
  "start_date": "2026-09-01",
  "end_date": "2026-10-01",
  "group_by": ["service", "environment"],
  "filters": [
    {
      "field": "team",
      "operator": "eq",
      "value": "data-platform"
    }
  ],
  "limit": 10
}
```

Dates use a half-open interval: `start_date` is inclusive and `end_date` is
exclusive. The example therefore covers every day in September without
requiring end-of-day timestamps or adding a day during SQL generation.
For a known calendar period, the application should compute these boundaries
independently and reject a model plan that does not match.

Supported metrics:

- `unblended_cost`
- `net_unblended_cost`
- `amortized_cost`

Supported grouping dimensions:

- `service`
- `account_id`
- `region`
- `environment`
- `team`
- `day`
- `month`

The validator rejects additional root keys, arbitrary columns, unsupported
operators, invalid dates, ranges longer than 366 days, duplicate dimensions,
oversized filter lists, and result limits greater than 100.

## Why not ask the model for SQL?

Raw SQL makes the model responsible for business semantics, data access, query
cost, and syntax simultaneously. A constrained plan separates those concerns:

- the model interprets intent;
- code owns metric definitions and column mappings;
- policy controls accessible data;
- the generated SQL remains visible for review.

The compiler escapes filter literals and selects identifiers only from
allowlists. The database and table names must pass a strict identifier check.
That is useful defense in depth, but it does not replace IAM, Lake Formation,
workgroup controls, logging, or human review.

## Observed validation evidence

A live Athena check over synthetic input produced query execution ID
`4dd1e94e-e6c2-47b4-a25e-cad03483faa1`: 513 ms total execution time, 347 ms
engine time, and 1,064 bytes scanned. Its top returned service totals were
Amazon Redshift `373.5`, Amazon EC2 `268.45`, and AWS Glue `178.6`.

This was one validation run, not a benchmark or savings claim. In the same
exercise, Amazon Nova Micro through `us.amazon.nova-micro-v1:0` returned an
inclusive end date despite an exclusive-date prompt. That observed failure is
why the application—not prompt wording—must own and verify date semantics.

## Optional isolated AWS scaffold

`infra/template.yaml` defines a short-lived demonstration stack containing:

- an encrypted, public-access-blocked S3 bucket with a seven-day lifecycle;
- a Glue database and CSV table for the synthetic file;
- an Athena workgroup with enforced result settings;
- a Lambda plan validator/SQL generator;
- a Lambda execution role that permits CloudWatch Logs only.

The template does not upload data, invoke the function, or execute a query.
If you choose to deploy it in a sandbox account, inspect the change set first,
upload only `data/synthetic_cur.csv` to the stack's `synthetic-cur/` prefix,
and delete the stack when finished. Because S3 buckets must be empty before
CloudFormation can delete them, remove generated objects first.

## Extending the pattern responsibly

Before connecting real billing data:

1. Define each cost basis with your FinOps stakeholders.
2. Expose curated views instead of raw CUR columns.
3. Enforce account, business-unit, and tag visibility with IAM and Lake
   Formation.
4. Add query-byte limits, timeouts, logging, and explicit execution approval.
5. Return the cost basis, date range, filters, SQL, source freshness, and query
   ID with every answer.
6. Build a fixed evaluation set that includes ambiguity, missing tags, credits,
   refunds, Savings Plans, reservations, and late-arriving adjustments.

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
