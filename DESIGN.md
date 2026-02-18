# Design Document: Rancher Quota Automation Tool

## 1. Requirements Analysis

### Ambiguities and Assumptions

#### Rancher API Uncertainties
1. **API Version**: Rancher 2.13 uses v3 API. Assumed endpoints:
   - Projects: `/v3/projects/{id}`
   - Namespaces: `/v3/namespaces/{id}`
   - Clusters: `/v3/clusters/{id}`
   - Project listing: `/v3/projects?clusterId={clusterId}`

2. **Quota Field Structure**: Assumed quota fields in Rancher API:
   - Project quotas: `resourceQuota.limit.cpu`, `resourceQuota.limit.memory`, `resourceQuota.reservation.cpu`, `resourceQuota.reservation.memory`
   - Namespace quotas: Similar structure under namespace resource
   - Values as strings: "1000m" for CPU, "2Gi" for memory

3. **Project Name Resolution**: 
   - Projects have both `name` and `id` fields
   - Name lookup must be scoped to cluster to avoid collisions
   - Assumption: Project names are unique within a cluster

4. **Namespace Quota Inheritance**:
   - Assumption: Namespace quotas are independent but must not exceed project quotas
   - Tool will enforce both project and namespace quotas as specified in config

#### Security Concerns
1. **Token Storage**: Tokens in config files are less secure. Prefer environment variables.
2. **Token Masking**: All token values must be masked in logs and output.
3. **API Permissions**: Required permissions:
   - Read: `projects.get`, `namespaces.get`, `clusters.get`
   - Write: `projects.update`, `namespaces.update`
   - Document minimum required roles (likely "Project Owner" or "Cluster Admin")

#### Edge Cases
1. **Project Not Found**: Fail-fast unless `--continue-on-error` is set
2. **Namespace Not Found**: Log warning, skip namespace quota enforcement
3. **Invalid Quota Values**: Validate format before API calls
4. **Concurrent Modifications**: No locking mechanism - last write wins (document limitation)
5. **Partial Cluster Failures**: With `--continue-on-error`, continue to next cluster/project
6. **Empty Config**: Validate config has at least one cluster and project definition

#### Configuration Format Assumptions
1. **Config File Format**: YAML (human-readable, supports comments)
2. **Cluster ID Format**: String (Rancher cluster IDs are typically alphanumeric)
3. **Token Reference**: Environment variable name (e.g., `RANCHER_TOKEN_PROD`)

---

## 2. Architecture

### High-Level Design

```
┌─────────────┐
│   CLI       │
│  (cli.py)   │
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌──────────────┐
│   Config    │────▶│   Models     │
│ (config.py) │     │ (models.py)  │
└──────┬──────┘     └──────────────┘
       │
       ▼
┌─────────────────┐
│ Rancher Client  │
│(rancher_client) │
└──────┬──────────┘
       │
       ▼
┌─────────────┐     ┌─────────────┐
│   Planner   │────▶│    Diff     │
│(planner.py) │     │  (diff.py)  │
└──────┬──────┘     └─────────────┘
       │
       ▼
┌─────────────┐
│  Executor   │
│(executor.py)│
└─────────────┘
```

### Component Responsibilities

1. **CLI (`cli.py`)**: 
   - Parse command-line arguments
   - Orchestrate workflow
   - Handle exit codes
   - Format output

2. **Config (`config.py`)**:
   - Load and validate YAML config files
   - Resolve token from env vars or config
   - Provide typed config objects

3. **Models (`models.py`)**:
   - Data classes for quotas, projects, namespaces
   - Type-safe quota value handling
   - Comparison and validation logic

4. **Rancher Client (`rancher_client.py`)**:
   - HTTP client for Rancher API
   - Authentication handling
   - API endpoint abstraction
   - Error handling and retries

5. **Planner (`planner.py`)**:
   - Read current state from Rancher
   - Compare current vs desired
   - Generate execution plan
   - Filter by project/cluster selection

6. **Diff (`diff.py`)**:
   - Generate human-readable diffs
   - Format before/after comparisons
   - Support dry-run output

7. **Executor (`executor.py`)**:
   - Apply quota changes via API
   - Track success/failure
   - Generate execution summary

8. **Logging (`logging.py`)**:
   - Structured JSON logging
   - Context injection (instance, cluster, project, namespace)
   - Secret masking

---

## 3. Data Model

### Configuration Model

```python
@dataclass
class RancherInstanceConfig:
    url: str
    token: str  # or token_ref for env var
    clusters: Dict[str, ClusterConfig]

@dataclass
class ClusterConfig:
    cluster_id: str
    projects: Dict[str, ProjectQuotaConfig]

@dataclass
class ProjectQuotaConfig:
    project_quota: QuotaSpec
    namespace_quotas: Dict[str, QuotaSpec]  # namespace name -> quota

@dataclass
class QuotaSpec:
    cpu_limit: Optional[str]  # e.g., "2000m"
    memory_limit: Optional[str]  # e.g., "4Gi"
    cpu_reservation: Optional[str]
    memory_reservation: Optional[str]
```

### API Model

```python
@dataclass
class Project:
    id: str
    name: str
    cluster_id: str
    quota: QuotaSpec

@dataclass
class Namespace:
    id: str
    name: str
    project_id: str
    quota: QuotaSpec
```

### Execution Model

```python
@dataclass
class PlanItem:
    resource_type: Literal["project", "namespace"]
    resource_id: str
    resource_name: str
    cluster_id: str
    current: QuotaSpec
    desired: QuotaSpec
    diff: QuotaDiff

@dataclass
class ExecutionResult:
    success: bool
    plan_item: PlanItem
    error: Optional[str]
```

---

## 4. API Usage

### Rancher v3 API Endpoints

#### Authentication
- Bearer token in `Authorization` header
- Token from config or environment variable

#### Read Operations
1. **List Projects**: `GET /v3/projects?clusterId={clusterId}`
2. **Get Project**: `GET /v3/projects/{projectId}`
3. **List Namespaces**: `GET /v3/namespaces?projectId={projectId}`
4. **Get Namespace**: `GET /v3/namespaces/{namespaceId}`
5. **Get Cluster**: `GET /v3/clusters/{clusterId}` (for validation)

#### Write Operations
1. **Update Project**: `PUT /v3/projects/{projectId}` (with quota fields)
2. **Update Namespace**: `PUT /v3/namespaces/{namespaceId}` (with quota fields)

### Quota Field Mapping

Rancher API quota structure (assumed):
```json
{
  "resourceQuota": {
    "limit": {
      "cpu": "2000m",
      "memory": "4Gi"
    },
    "reservation": {
      "cpu": "1000m",
      "memory": "2Gi"
    }
  }
}
```

### Error Handling
- 401/403: Authentication/authorization failure → fatal error
- 404: Resource not found → fail-fast or skip (based on mode)
- 409: Conflict → retry once, then fail
- 5xx: Server error → retry with exponential backoff (3 attempts)

---

## 5. Failure Modes

### Fatal Errors (Exit Code 1)
- Invalid configuration file
- Authentication failure
- Network connectivity issues
- Invalid CLI arguments
- Missing required environment variables

### Partial Failures (Exit Code 2)
- Some projects/clusters succeed, others fail
- Only occurs with `--continue-on-error`
- Summary report shows success/failure counts

### Recoverable Errors
- Temporary API unavailability → retry with backoff
- Rate limiting → retry with backoff
- Invalid quota values → skip with warning

### Error Recovery Strategy
1. **Retry Logic**: Exponential backoff (1s, 2s, 4s) for transient errors
2. **Continue-on-Error**: Process remaining items after failure
3. **Validation First**: Validate all quota values before any API calls
4. **Atomic Updates**: Each quota update is independent (no rollback needed)

---

## 6. Testing Strategy

### Unit Tests

**Test Coverage Targets:**
- Config parsing: 100%
- Quota comparison logic: 100%
- Diff generation: 100%
- Error handling: 90%+

**Mock Strategy:**
- Mock `requests` library for HTTP calls
- Mock Rancher API responses
- Test all error paths (401, 404, 409, 500)

**Key Test Cases:**
1. Config loading with env var token resolution
2. Project name → ID resolution with collisions
3. Quota diff calculation (all combinations)
4. Dry-run mode (no API writes)
5. Continue-on-error behavior
6. Invalid quota format validation

### Integration Tests

**Test Infrastructure Requirements:**
- Real Rancher 2.13 instance (test environment)
- Test cluster with test project
- API token with write permissions
- Isolated test namespace

**Test Flow:**
1. Read current quota state
2. Apply test quota change
3. Verify change via API read
4. Restore original quota
5. Verify restoration

**Safety Measures:**
- Require `INTEGRATION_WRITE=1` environment variable
- Only modify test project/namespace (from env vars)
- Always restore original state
- Timeout protection (max 5 minutes per test)

**Integration Test Cases:**
1. Project quota enforcement
2. Namespace quota enforcement
3. Multi-namespace project handling
4. Error recovery (simulate API failure)

---

## 7. Air-Gapped Dependency Strategy

### Dependency Pinning
- Use `requirements.txt` with exact versions
- Use `pyproject.toml` for build metadata
- Document all transitive dependencies

### Offline Installation
1. **Dependency Bundle**: Create `requirements-bundle.txt` with all dependencies
2. **Wheel Cache**: Pre-download wheels to `wheels/` directory
3. **Installation Script**: `install-offline.sh` that installs from local cache

### Build Instructions
- Document Python version requirement (3.9+)
- Provide `pip install --no-index --find-links wheels/ -r requirements.txt` command
- Include checksum verification for security

---

## 8. Security Considerations

### Token Handling
- Never log token values (mask as `***`)
- Prefer environment variables over config files
- Support token rotation (update env var, no code change)

### API Permissions
- Document minimum required Rancher roles
- Recommend "Project Owner" or "Cluster Admin" roles
- Principle of least privilege: only quota update permissions

### Input Validation
- Validate quota format (CPU: "\\d+m" or "\\d+", Memory: "\\d+[KMGT]i?")
- Sanitize project/namespace names
- Validate URLs and cluster IDs

---

## 9. Implementation Plan

### Phase 1: Core Infrastructure
1. Project structure setup
2. Dependency management (pyproject.toml, requirements.txt)
3. Models and data classes
4. Logging infrastructure

### Phase 2: Rancher Integration
1. Config loading and validation
2. Rancher API client
3. Project/namespace discovery
4. Quota read operations

### Phase 3: Enforcement Logic
1. Planner (current vs desired comparison)
2. Diff generation
3. Executor (quota updates)
4. Error handling and retries

### Phase 4: CLI and Polish
1. CLI argument parsing
2. Dry-run mode
3. Output formatting
4. Exit code handling

### Phase 5: Testing
1. Unit tests
2. Integration tests
3. Documentation

---

## 10. Open Questions / Assumptions Summary

### Assumptions Made
1. Rancher 2.13 uses v3 API with REST endpoints
2. Quota fields are nested under `resourceQuota.limit` and `resourceQuota.reservation`
3. Quota values are strings (CPU: "1000m", Memory: "2Gi")
4. Project names are unique within a cluster
5. Namespace quotas are independent of project quotas (but tool enforces both)
6. YAML config format
7. Python 3.9+ required

### Areas Requiring Verification
1. Exact Rancher API quota field structure (may need adjustment after testing)
2. Namespace quota inheritance behavior (if any)
3. API rate limits and best practices
4. Required Rancher RBAC permissions (to be documented after testing)

---

## 11. Success Criteria

1. ✅ Can read current quotas from Rancher
2. ✅ Can enforce project-level quotas
3. ✅ Can enforce namespace-level quotas
4. ✅ Dry-run shows accurate diffs
5. ✅ Idempotent execution (no changes if already correct)
6. ✅ Multi-cluster support
7. ✅ Multi-instance support
8. ✅ Comprehensive error handling
9. ✅ Unit test coverage > 90%
10. ✅ Integration tests pass against real Rancher
11. ✅ Offline installation works
12. ✅ Documentation complete

