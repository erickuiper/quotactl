"""Unit tests for Kubernetes client."""

from unittest.mock import MagicMock, patch

import pytest
import yaml

from quotactl.kubernetes_client import (
    KubernetesAPIError,
    KubernetesClient,
    PROJECT_ID_ANNOTATION,
    _parse_kubeconfig,
)
from quotactl.logging import setup_logging


KUBECONFIG_TOKEN = """
apiVersion: v1
kind: Config
clusters:
  - name: cluster
    cluster:
      server: https://k8s.example.com
      insecure-skip-tls-verify: true
users:
  - name: user
    user:
      token: test-token-123
contexts:
  - name: ctx
    context:
      cluster: cluster
      user: user
current-context: ctx
"""

KUBECONFIG_CLIENT_CERT = """
apiVersion: v1
kind: Config
clusters:
  - name: cluster
    cluster:
      server: https://k8s.example.com
users:
  - name: user
    user:
      client-certificate-data: xxx
      client-key-data: yyy
contexts:
  - name: ctx
    context:
      cluster: cluster
      user: user
current-context: ctx
"""


class TestParseKubeconfig:
    """Tests for _parse_kubeconfig."""

    def test_parse_token_auth(self):
        """Test parsing kubeconfig with token auth."""
        server, token, verify = _parse_kubeconfig(KUBECONFIG_TOKEN)
        assert server == "https://k8s.example.com"
        assert token == "test-token-123"
        assert verify is False

    def test_parse_client_cert_raises(self):
        """Test parsing kubeconfig with client-cert auth raises."""
        with pytest.raises(KubernetesAPIError, match="token auth required"):
            _parse_kubeconfig(KUBECONFIG_CLIENT_CERT)

    def test_parse_invalid_kubeconfig(self):
        """Test parsing invalid kubeconfig."""
        with pytest.raises(KubernetesAPIError, match="Invalid kubeconfig"):
            _parse_kubeconfig("not valid yaml")


class TestKubernetesClient:
    """Tests for KubernetesClient."""

    @pytest.fixture
    def logger(self):
        """Create logger for tests."""
        return setup_logging("DEBUG")

    def test_list_namespaces(self, logger):
        """Test listing namespaces."""
        mock_response = {
            "items": [
                {
                    "metadata": {
                        "name": "ns1",
                        "annotations": {PROJECT_ID_ANNOTATION: "local:p-123"},
                    }
                },
            ]
        }
        client = KubernetesClient(
            base_url="https://k8s.example.com",
            token="token",
            logger=logger,
            verify=False,
        )
        with patch.object(client.session, "get") as mock_get:
            mock_get.return_value.json.return_value = mock_response
            mock_get.return_value.raise_for_status = lambda: None
            namespaces = client.list_namespaces_in_project("local:p-123")
        assert len(namespaces) == 1
        assert namespaces[0].name == "ns1"
        assert namespaces[0].project_id == "local:p-123"

    def test_list_namespaces_filters_by_project(self, logger):
        """Test filtering namespaces by project annotation."""
        mock_response = {
            "items": [
                {
                    "metadata": {
                        "name": "ns1",
                        "annotations": {PROJECT_ID_ANNOTATION: "local:p-123"},
                    }
                },
                {
                    "metadata": {
                        "name": "ns2",
                        "annotations": {PROJECT_ID_ANNOTATION: "local:p-456"},
                    }
                },
            ]
        }
        client = KubernetesClient(
            base_url="https://k8s.example.com",
            token="token",
            logger=logger,
            verify=False,
        )
        with patch.object(client.session, "get") as mock_get:
            mock_get.return_value.json.return_value = mock_response
            mock_get.return_value.raise_for_status = lambda: None
            namespaces = client.list_namespaces_in_project("local:p-123")
        assert len(namespaces) == 1
        assert namespaces[0].name == "ns1"

    def test_from_kubeconfig(self, logger):
        """Test creating client from kubeconfig."""
        client = KubernetesClient.from_kubeconfig(KUBECONFIG_TOKEN, logger)
        assert client.base_url == "https://k8s.example.com"
        assert client.token == "test-token-123"
