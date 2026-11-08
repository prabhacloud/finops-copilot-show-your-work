# Your FinOps Copilot Should Show Its Work

## A governed pattern for asking AWS cost questions in plain English with CUR 2.0, Athena, and Amazon Bedrock

![FinOps Copilot: from a natural-language question to an auditable answer](assets/finops-copilot-hero.png)

“Why did our data-platform cost increase last month?”

That sounds like a simple question. In practice, a trustworthy answer depends
on decisions that are easy to hide behind a fluent paragraph:

- Which definition of cost did we use?
- Did “last month” mean calendar month, billing period, or the latest 30 days?
- Were credits, refunds, Savings Plans, and reservations included?
- Which accounts and tags were visible to the person asking?
- How fresh was the billing export?
- What query produced the number?

This is why I do not think a FinOps assistant should begin with “let the model
write SQL.” The safer design is to let the model interpret intent, then make
deterministic code own the financial definitions, access boundaries, and query
construction.

The most important product requirement is not a clever chat interface. It is
the ability to show the work behind every answer.

This article presents that pattern with a companion synthetic demo. The demo
does not use real billing data, does not claim production results, and does not
call AWS. Its purpose is to make the control boundary concrete and testable.

## The architecture

![A governed FinOps query path with deterministic validation before execution](assets/finops-copilot-architecture.png)

A production-oriented implementation could use:

1. **AWS Data Exports for CUR 2.0** to deliver detailed billing data to Amazon
   S3.
2. **AWS Glue Data Catalog** to describe curated cost views.
3. **AWS Lake Formation** and IAM to constrain who can query which data.
4. **Amazon Athena** to run transparent, reviewable SQL.
5. **An Amazon Bedrock agent or application** to translate a natural-language
   question into a constrained query plan.
6. **A validation Lambda action** to reject unsafe or ambiguous plans before
   SQL is generated.
7. **An answer contract** that returns the result together with the metric,
   time range, filters, freshness, and query evidence.

The companion repository represents the central control in Python:

```text
question → proposed JSON plan → validation → SQL + evidence → decision to run
```

The model never receives permission to create arbitrary SQL.

## Give the model a small language

Instead of requesting a query string, ask the model for a plan:

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

This plan is intentionally less expressive than SQL. That limitation is the
feature.

The date range is half-open: `start_date` is inclusive and `end_date` is
exclusive. Representing September as `[2026-09-01, 2026-10-01)` removes the
usual ambiguity around timestamps at the end of a month and composes cleanly
with the next period.

The validator in the demo accepts three cost bases, seven grouping dimensions,
two filter operators, a maximum of three grouping dimensions, a 366-day date
window, and a result limit no greater than 100. Unknown keys are rejected.
There is no field in the contract for joins, subqueries, functions, file paths,
catalog changes, or raw SQL.

```python
allowed_keys = {
    "metric",
    "start_date",
    "end_date",
    "group_by",
    "filters",
    "limit",
}

unknown = set(plan) - allowed_keys
if unknown:
    raise ValidationError(f"Unknown query-plan keys: {sorted(unknown)}")
```

That check matters. If a caller adds a `sql` property, the plan fails rather
than silently carrying an instruction into another layer.

## Put cost definitions in code, not in the prompt

The words “AWS cost” do not identify a single number. Unblended, net
unblended, and amortized cost answer different questions. A model should not
select a new formula based on how persuasive its explanation sounds.

The demo maps an approved metric name to one approved column:

```python
METRIC_COLUMNS = {
    "unblended_cost": "unblended_cost",
    "net_unblended_cost": "net_unblended_cost",
    "amortized_cost": "amortized_cost",
}
```

In a real implementation, I would place more of this logic behind curated
views. Those views can consistently encode how the organization treats shared
costs, discounts, refunds, credits, reservation fees, Savings Plans, taxes,
and allocation tags. The agent can then choose among documented concepts
instead of rebuilding finance policy for every question.

This also makes review easier. When stakeholders change a definition, the
change occurs in a governed data contract and test suite—not in dozens of
prompts.

## Compile the plan deterministically

After validation, regular code converts the plan to Athena SQL. Dimensions and
columns come from allowlists. Filter values are escaped. Database and table
identifiers must pass a strict identifier pattern.

For the example plan, the compiler produces SQL like this:

```sql
SELECT
  product_code AS "service",
  environment AS "environment",
  SUM(CAST(amortized_cost AS double)) AS total_cost
FROM "finops_demo"."cur_synthetic"
WHERE
  CAST(usage_start_date AS date) >= DATE '2026-09-01'
  AND CAST(usage_start_date AS date) < DATE '2026-10-01'
  AND team = 'data-platform'
GROUP BY product_code, environment
ORDER BY total_cost DESC
LIMIT 10
```

Readable SQL is part of the interface. It gives an engineer or analyst
something concrete to inspect when an answer looks surprising.

The query is also paired with a machine-readable evidence object:

```json
{
  "metric": "amortized_cost",
  "date_range": {
    "start_inclusive": "2026-09-01",
    "end_exclusive": "2026-10-01"
  },
  "group_by": ["service", "environment"],
  "filters": [
    {
      "field": "team",
      "operator": "eq",
      "values": ["data-platform"]
    }
  ],
  "database": "finops_demo",
  "table": "cur_synthetic",
  "limit": 10
}
```

For a real answer, I would extend this with the billing export's latest
available date, Athena query execution ID, bytes scanned, applicable policy
version, and links to the relevant dashboard or query history.

## What a live synthetic validation exposed

I also exercised the pattern in a short-lived AWS validation environment using
synthetic data. One Athena query completed with query execution ID
`4dd1e94e-e6c2-47b4-a25e-cad03483faa1`. Athena reported 513 ms total execution
time, 347 ms engine time, and 1,064 bytes scanned. The first three result rows
were:

| Service | `total_cost` |
| --- | ---: |
| Amazon Redshift | 373.5 |
| Amazon EC2 | 268.45 |
| AWS Glue | 178.6 |

These figures are evidence from one query over synthetic input, not a
benchmark or a savings claim.

The more useful finding came one step earlier. Amazon Nova Micro, invoked
through the `us.amazon.nova-micro-v1:0` inference profile, was explicitly
prompted to produce an exclusive end date but returned an inclusive month-end
value. The response was plausible JSON and still violated the intended
calendar window. That is exactly why prompt wording is not a control:
deterministic code should resolve named periods, compare the model's proposal
with that expected boundary, and reject a mismatch before SQL generation. The
generic validator also rejects empty, reversed, or oversized ranges. The model
can interpret intent, but it should not be the authority on calendar
semantics.

## Separate generation from execution

Generating a valid query does not mean the query should automatically run.

Execution is a separate decision point where you can apply:

- caller identity and data-entitlement checks;
- Lake Formation permissions;
- approved Athena workgroups;
- query scan limits and timeouts;
- account or organizational-unit restrictions;
- logging and trace correlation;
- explicit approval for expensive or unusually broad requests.

The sample CloudFormation template makes this separation visible. Its Lambda
role can write logs, but it has no Athena execution permission. The function
returns a validated SQL string and `executed: false`.

That is not a complete production security model. It is a deliberate example
of least authority at the generation step.

## Three production traps to design for

### 1. Billing data is not a real-time telemetry stream

An assistant must state how fresh its source is. A polished answer based on an
incomplete billing period can still be wrong. Late-arriving line items and
adjustments can change a result after the first query.

For questions about active incidents, operational telemetry may be a better
source than CUR. For cost analysis, disclose the latest export timestamp and
whether the period is final.

### 2. Tags are not reliable merely because they exist

An `environment=production` filter looks precise. It may exclude untagged
resources, miss inherited allocation logic, or reflect inconsistent values
such as `prod`, `Prod`, and `production`.

A useful FinOps answer should report unallocated cost and tag coverage rather
than hiding incomplete attribution. Normalization should happen in a curated
layer, with ownership for exceptions.

### 3. Conversation is not anomaly detection

A chat experience can explain a known increase, but it should not replace a
system designed to detect anomalies. AWS Cost Anomaly Detection and other
monitoring controls are better suited to continuously identifying unexpected
changes.

A strong combination is:

1. monitoring detects a material change;
2. the assistant helps investigate it;
3. the answer links back to evidence and the original signal.

## Test the questions people actually ask

Happy-path examples are not enough. Before connecting a model to billing data,
build an evaluation set containing:

- “What did we spend last month?” with no cost basis specified;
- comparisons across partial and complete months;
- accounts the caller is not permitted to see;
- missing and inconsistent tags;
- refunds, credits, taxes, and support charges;
- reservation and Savings Plans scenarios;
- zero-result questions;
- deliberate attempts to add SQL or unknown fields;
- very large date ranges and result limits;
- filter values containing quotes.

The repository includes unit tests for the mechanics of the contract. A real
evaluation suite also needs domain review: Did the system ask for
clarification when the question was ambiguous? Did it choose the approved cost
basis? Did it disclose excluded or unallocated costs? Could another analyst
reproduce the result?

## A practical rollout

I would roll this out in four stages.

**Stage 1: read-only analyst tool.** Use curated views, fixed example
questions, visible SQL, and mandatory human execution.

**Stage 2: controlled query service.** Add caller-aware authorization, Athena
workgroup controls, scan limits, logging, freshness metadata, and a fixed
evaluation suite.

**Stage 3: explanations and comparisons.** Let the model summarize returned
data, but require citations to query outputs and expose assumptions.

**Stage 4: workflow integration.** Connect anomaly alerts, ticketing, budgets,
and ownership metadata. Keep remediation actions separate and approval-based.

At every stage, measure more than response quality. Track clarification rate,
unsupported-plan rejection, query failure rate, reproducibility, source
freshness, bytes scanned, and analyst corrections.

## Try the synthetic demo

The companion repository includes:

- a synthetic CUR-like CSV;
- a model-plan validator;
- an allowlist-based Athena SQL compiler;
- a local evaluator;
- unit tests; and
- an isolated CloudFormation learning scaffold.

Run it locally:

```bash
PYTHONPATH=src python -m finops_copilot.demo
```

The command shows the validated plan, generated query, and local result, then
confirms that no AWS API was called.

## Closing thought

Natural language can make cloud cost data more accessible, but accessibility
without evidence creates a new kind of operational risk. A convincing answer
is not the same as an auditable answer.

Let the model help interpret the question. Let governed data contracts define
the numbers. Let deterministic code build the query. Let policy decide whether
it can run.

And when the answer reaches a human, make the copilot show its work.

## References

- [AWS Data Exports and CUR 2.0 documentation](https://docs.aws.amazon.com/cur/latest/userguide/dataexports-create-standard.html)
- [Querying Cost and Usage Reports with Athena](https://docs.aws.amazon.com/cur/latest/userguide/cur-query-athena.html)
- [Lake Formation permissions with Athena](https://docs.aws.amazon.com/lake-formation/latest/dg/athena-lf.html)
- [Amazon Bedrock Agents action-group Lambda functions](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-lambda.html)
- [AWS Cost Anomaly Detection](https://docs.aws.amazon.com/cost-management/latest/userguide/manage-ad.html)
