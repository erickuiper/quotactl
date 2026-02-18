# AGENTS.md

## Project: Rancher Quota Automation Tool

---

## Mission

Build a **Python automation tool** that audits and enforces **Rancher quotas** (Rancher 2.13) for:

- **Project-level quotas**
- **Namespace-level quotas**

The tool must enforce:

- CPU reservations
- Memory reservations
- CPU limits
- Memory limits

The tool operates in an **air-gapped on-prem environment** and targets:

- Multiple Rancher instances
- Multiple downstream Kubernetes clusters (Kubernetes 1.33)

The tool must support switching contexts between Rancher instances and clusters via CLI.

---

## Scope

### In Scope
- Rancher project-level quotas
- Rancher namespace-level quotas
- Multi-cluster support
- Multi-Rancher-instance support
- Idempotent quota enforcement
- CLI execution
- Dry-run mode
- Diff output
- Unit tests
- Integration tests

### Out of Scope
- Terraform quota creation
- Kubernetes native objects (`ResourceQuota`, `LimitRange`)
- External SaaS integrations
- Internet connectivity requirements

All quota data must be retrieved from Rancher and/or Kubernetes APIs.

---

## Agent Behavior (Required)

The agent must follow this workflow:

1. **Challenge the plan first**
   - Identify ambiguities
   - Identify edge cases
   - Identify Rancher API uncertainties
   - Identify security concerns
   - Ask clarifying questions only when necessary
   - Document assumptions clearly

2. Produce a short **design document** before implementation including:
   - Architecture
   - Data model
   - API usage
   - Failure modes
   - Testing strategy

3. Implement:
   - Production code
   - Unit tests
   - Integration tests
   - Documentation

4. Deliver a runnable project.

---

## Functional Requirements

### Rancher Connectivity
- Connect to Rancher using configuration file.
- Support multiple Rancher instances.
- Support multiple clusters per instance.
- Use API tokens for authentication.

### Project Targeting
- Apply enforcement by **project name**.
- Project lookup must be scoped by:
  - Rancher instance
  - Cluster
- Must handle potential name collisions safely.

### Read Current State
The system must retrieve:

- Project quota configuration
- Namespace quota configuration
- Project → namespace mappings
- Cluster and project inventory

All state must come from Rancher/Kubernetes APIs.

### Enforce Desired State
- Desired quotas defined in config.
- Must reconcile current vs desired.
- Must be idempotent.
- Must update only when drift exists.

### Dry Run Mode
- `--dry-run` shows planned changes.
- Must display before/after values.
- No changes applied.

### Execution Modes
CLI must support:

- One instance + one cluster
- One instance + multiple clusters
- Explicit project selection
- Optional all-project mode

### Error Handling
- Fail-fast default behavior.
- Optional continue-on-error mode.
- End-of-run summary required.

### Logging
- Structured logs (JSON preferred).
- Include:
  - instance
  - cluster
  - project
  - namespace
- Never log secrets.

---

## Configuration Requirements

### Config Structure
- One config file per Rancher instance.
- Config contains:
  - Rancher base URL
  - API token or token reference
  - Cluster identifiers
  - Quota rules keyed by project name

### Security
- Token may come from:
  - Config file
  - Environment variable (preferred)

---

## Non-Functional Requirements

### Air-Gapped Environment
- No internet access.
- Pin all dependencies.
- Provide offline installation strategy.
- Provide reproducible build instructions.

### Security
- Least-privilege API access.
- Mask sensitive data.
- Document required permissions.

---

## Testing Requirements

### Unit Tests
- Use pytest.
- Mock Rancher API.
- Test:
  - config parsing
  - project lookup
  - diff generation
  - dry-run behavior
  - error handling

### Integration Tests
Must support execution against real on-prem test infrastructure.

Tests should:

- Read current quotas
- Apply safe changes
- Verify results
- Restore original values

Integration test configuration via environment variables:

- `RANCHER_URL`
- `RANCHER_TOKEN`
- `CLUSTER_ID`
- `PROJECT_NAME_TEST`

Write operations must require explicit opt-in:

INTEGRATION_WRITE=1




## Implementation Expectations

### Suggested Repository Structure

```
src/quotactl/
cli.py
config.py
rancher_client.py
models.py
planner.py
executor.py
diff.py
logging.py

tests/unit/
tests/integration/

README.md
pyproject.toml
```

### CLI Interface

Minimum:

```
quotactl --config instance.yaml --cluster <id> --project <name> --dry-run
quotactl --config instance.yaml --cluster <id> --project <name> --apply


Optional:

--projects p1,p2
--all-projects
--continue-on-error
```

### Exit Codes

- `0` success
- `1` fatal error
- `2` partial failure

---

## Required Design Considerations

The design document must explicitly address:

- Mapping project names to Rancher project IDs
- Namespace quota inheritance vs override behavior
- Safe integration test execution
- Air-gapped dependency strategy
- Token security handling
- Multi-cluster orchestration model

---

## Output Expectations

- Human-readable execution summary
- Clear diff output in dry-run
- Structured logs
- Reproducible build instructions
- Complete documentation

---
