"""Unit tests for config."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from quotactl.config import RancherInstanceConfig
from quotactl.models import QuotaSpec


class TestRancherInstanceConfig:
    """Tests for RancherInstanceConfig."""

    def test_load_config_with_token(self):
        """Test loading config with token in file."""
        config_data = {
            "url": "https://rancher.example.com",
            "token": "test-token-123",
            "clusters": {
                "cluster1": {
                    "cluster_id": "c-abc123",
                    "projects": {
                        "project1": {
                            "project_quota": {
                                "cpu_limit": "2000m",
                                "memory_limit": "4Gi",
                            }
                        }
                    },
                }
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = Path(f.name)

        try:
            config = RancherInstanceConfig.from_file(config_path)
            assert config.url == "https://rancher.example.com"
            assert config.token == "test-token-123"
            assert "cluster1" in config.clusters
            assert config.clusters["cluster1"].cluster_id == "c-abc123"
            assert "project1" in config.clusters["cluster1"].projects
        finally:
            config_path.unlink()

    def test_load_config_with_token_env_var(self):
        """Test loading config with token from environment variable."""
        config_data = {
            "url": "https://rancher.example.com",
            "token_ref": "RANCHER_TOKEN",
            "clusters": {},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = Path(f.name)

        try:
            os.environ["RANCHER_TOKEN"] = "env-token-456"
            config = RancherInstanceConfig.from_file(config_path)
            assert config.token == "env-token-456"
        finally:
            config_path.unlink()
            if "RANCHER_TOKEN" in os.environ:
                del os.environ["RANCHER_TOKEN"]

    def test_load_config_with_explicit_token_env_var(self):
        """Test loading config with explicit token environment variable."""
        config_data = {
            "url": "https://rancher.example.com",
            "token": "file-token",
            "clusters": {},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = Path(f.name)

        try:
            os.environ["CUSTOM_TOKEN"] = "env-token-789"
            config = RancherInstanceConfig.from_file(config_path, token_env_var="CUSTOM_TOKEN")
            assert config.token == "env-token-789"
        finally:
            config_path.unlink()
            if "CUSTOM_TOKEN" in os.environ:
                del os.environ["CUSTOM_TOKEN"]

    def test_load_config_with_namespace_quotas(self):
        """Test loading config with namespace quotas."""
        config_data = {
            "url": "https://rancher.example.com",
            "token": "test-token",
            "clusters": {
                "cluster1": {
                    "cluster_id": "c-abc123",
                    "projects": {
                        "project1": {
                            "project_quota": {
                                "cpu_limit": "2000m",
                            },
                            "namespace_quotas": {
                                "ns1": {
                                    "cpu_limit": "1000m",
                                    "memory_limit": "2Gi",
                                },
                                "ns2": {
                                    "cpu_reservation": "500m",
                                },
                            },
                        }
                    },
                }
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = Path(f.name)

        try:
            config = RancherInstanceConfig.from_file(config_path)
            project_config = config.clusters["cluster1"].projects["project1"]
            assert "ns1" in project_config.namespace_quotas
            assert project_config.namespace_quotas["ns1"].cpu_limit == "1000m"
            assert project_config.namespace_quotas["ns1"].memory_limit == "2Gi"
            assert "ns2" in project_config.namespace_quotas
            assert project_config.namespace_quotas["ns2"].cpu_reservation == "500m"
        finally:
            config_path.unlink()

    def test_load_config_missing_url(self):
        """Test loading config without URL raises error."""
        config_data = {"token": "test-token", "clusters": {}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = Path(f.name)

        try:
            # Unset RANCHER_URL so config file is the only source
            orig = os.environ.pop("RANCHER_URL", None)
            try:
                with pytest.raises(ValueError, match="url"):
                    RancherInstanceConfig.from_file(config_path)
            finally:
                if orig is not None:
                    os.environ["RANCHER_URL"] = orig
        finally:
            config_path.unlink()

    def test_load_config_missing_token(self):
        """Test loading config without token raises error."""
        config_data = {"url": "https://rancher.example.com", "clusters": {}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="Token"):
                RancherInstanceConfig.from_file(config_path)
        finally:
            config_path.unlink()

    def test_load_config_file_not_found(self):
        """Test loading non-existent config file raises error."""
        config_path = Path("/nonexistent/config.yaml")
        with pytest.raises(FileNotFoundError):
            RancherInstanceConfig.from_file(config_path)

    def test_load_config_insecure_skip_tls_verify(self):
        """Test loading config with insecure_skip_tls_verify disables SSL verification."""
        config_data = {
            "url": "https://rancher.example.com",
            "token": "test-token",
            "insecure_skip_tls_verify": True,
            "clusters": {},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = Path(f.name)

        try:
            config = RancherInstanceConfig.from_file(config_path)
            assert config.verify_ssl is False
        finally:
            config_path.unlink()

    def test_load_config_default_verify_ssl_true(self):
        """Test verify_ssl is True when insecure_skip_tls_verify is absent."""
        config_data = {
            "url": "https://rancher.example.com",
            "token": "test-token",
            "clusters": {},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = Path(f.name)

        try:
            config = RancherInstanceConfig.from_file(config_path)
            assert config.verify_ssl is True
        finally:
            config_path.unlink()

