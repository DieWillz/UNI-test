# UNI Development Coordinator

The Development Coordination Layer automates task and context handoff between
AI participants without granting them access to UNI product tools.

## Setup

The CLI uses the example configuration by default, so the local LM Studio
provider works immediately when its server is available. For custom providers,
copy the example and pass the copy with `--config`:

```powershell
Copy-Item .uni-dev\coordination\providers.example.yaml .uni-dev\coordination\providers.yaml
```

Providers are explicit:

- a free local/OpenAI-compatible endpoint uses `transport: api` and
  `api_cost: free`;
- a provider with a paid API may use `transport: browser` in a dedicated
  profile, after the user logs in and configures current selectors;
- paid or unknown APIs remain blocked unless `allow_paid_api: true` is set.

Browser adapters do not bypass authentication, CAPTCHA, subscriptions, rate
limits, or provider terms.

## Create a task

```powershell
py -3 scripts\uni_dev_coordinator.py create `
  --title "Review router design" `
  --goal "Produce an independent architecture review" `
  --instructions "Find contract and termination defects; do not edit files" `
  --providers local_lm_studio `
  --file docs/decisions/ADR-0005-capability-router.md
```

The command prints the task ID. Then run or inspect it:

```powershell
py -3 scripts\uni_dev_coordinator.py run TASK_ID
py -3 scripts\uni_dev_coordinator.py show TASK_ID
py -3 scripts\uni_dev_coordinator.py list
```

Multiple provider IDs form a deterministic handoff sequence:

```text
--providers researcher,critic,implementer,reviewer
```

Alternatively, let the registry select enabled providers by capability and
priority:

```text
--capability review --provider-count 2
```

Each next provider receives the task, bounded artifact excerpts, constraints,
and previous results. Outputs are proposals awaiting coordinator review; they
never apply patches or mark their own work accepted.
