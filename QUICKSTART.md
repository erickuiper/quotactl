# Quick Start Guide

## Installation

### Standard Installation (Internet Connected)

```bash
# Install dependencies and package
pip install -e .
```

### Air-Gapped Installation

1. **On internet-connected machine:**
   ```bash
   ./download-dependencies.sh
   ```

2. **Transfer `wheels/` directory to air-gapped machine**

3. **On air-gapped machine:**
   ```bash
   ./install-offline.sh
   ```

## Configuration

1. Copy `example-config.yaml` to your config file:
   ```bash
   cp example-config.yaml my-rancher-config.yaml
   ```

2. Edit the config file with your Rancher instance details:
   - Set `url` to your Rancher instance URL
   - Set `token_ref` to an environment variable name (or use `token` directly)
   - Configure clusters and projects

3. Set the API token environment variable:
   ```bash
   export RANCHER_TOKEN="your-token-here"
   ```

## Usage

### Preview Changes (Dry Run)

```bash
quotactl --config my-rancher-config.yaml \
  --cluster c-abc123 \
  --project my-project \
  --dry-run
```

### Apply Changes

```bash
quotactl --config my-rancher-config.yaml \
  --cluster c-abc123 \
  --project my-project \
  --apply
```

## Testing

### Run Unit Tests

```bash
# Install dev dependencies first
pip install -e ".[dev]"

# Run tests
pytest tests/unit/
```

### Run Integration Tests

```bash
# Set environment variables
export RANCHER_URL="https://rancher.example.com"
export RANCHER_TOKEN="your-token"
export CLUSTER_ID="c-abc123"
export PROJECT_NAME_TEST="test-project"
export INTEGRATION_WRITE=1

# Run integration tests
pytest tests/integration/ -m integration
```

## Project Structure

```
rancher-quota/
├── src/quotactl/          # Main package
│   ├── cli.py             # CLI interface
│   ├── config.py          # Configuration
│   ├── diff.py            # Diff formatting
│   ├── executor.py        # Quota enforcement
│   ├── logging.py         # Structured logging
│   ├── models.py          # Data models
│   ├── planner.py         # Execution planning
│   └── rancher_client.py  # Rancher API client
├── tests/                 # Test suite
│   ├── unit/              # Unit tests
│   └── integration/       # Integration tests
├── DESIGN.md              # Design document
├── README.md              # Full documentation
└── example-config.yaml    # Example configuration
```

## Next Steps

1. Read [README.md](README.md) for detailed documentation
2. Review [DESIGN.md](DESIGN.md) for architecture details
3. Customize `example-config.yaml` for your environment
4. Test with `--dry-run` before applying changes

