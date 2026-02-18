"""Unit tests for Rancher client."""

from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

from quotactl.logging import setup_logging
from quotactl.models import Namespace, Project
from quotactl.rancher_client import RancherAPIError, RancherClient


class TestRancherClient:
    """Tests for RancherClient."""

    @pytest.fixture
    def logger(self):
        """Create logger for tests."""
        return setup_logging("DEBUG")

    @pytest.fixture
    def client(self, logger):
        """Create Rancher client for tests."""
        return RancherClient("https://rancher.example.com", "test-token", logger)

    def test_get_cluster(self, client):
        """Test getting cluster."""
        mock_response = Mock()
        mock_response.json.return_value = {"id": "c-123", "name": "test-cluster"}
        mock_response.raise_for_status = Mock()

        with patch.object(client.session, "get", return_value=mock_response):
            result = client.get_cluster("c-123")
            assert result["id"] == "c-123"
            assert result["name"] == "test-cluster"

    def test_list_projects(self, client):
        """Test listing projects."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "p-123",
                    "name": "project1",
                    "clusterId": "c-456",
                    "resourceQuota": {"limit": {"cpu": "2000m"}},
                }
            ]
        }
        mock_response.raise_for_status = Mock()

        with patch.object(client.session, "get", return_value=mock_response):
            projects = client.list_projects("c-456")
            assert len(projects) == 1
            assert projects[0].id == "p-123"
            assert projects[0].name == "project1"

    def test_get_project(self, client):
        """Test getting project."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "p-123",
            "name": "project1",
            "clusterId": "c-456",
            "resourceQuota": {"limit": {"cpu": "2000m"}},
        }
        mock_response.raise_for_status = Mock()

        with patch.object(client.session, "get", return_value=mock_response):
            project = client.get_project("p-123")
            assert project.id == "p-123"
            assert project.name == "project1"

    def test_update_project(self, client):
        """Test updating project."""
        get_response = Mock()
        get_response.json.return_value = {
            "id": "p-123",
            "name": "project1",
            "clusterId": "c-456",
            "resourceQuota": {"limit": {"cpu": "2000m"}},
        }
        get_response.raise_for_status = Mock()

        put_response = Mock()
        put_response.json.return_value = {
            "id": "p-123",
            "name": "project1",
            "clusterId": "c-456",
            "resourceQuota": {"limit": {"cpu": "3000m"}},
        }
        put_response.raise_for_status = Mock()

        with patch.object(
            client.session, "get", return_value=get_response
        ), patch.object(client.session, "put", return_value=put_response):
            quota_data = {"resourceQuota": {"limit": {"cpu": "3000m"}}}
            project = client.update_project("p-123", quota_data)
            assert project.quota.cpu_limit == "3000m"

    def test_list_namespaces(self, client):
        """Test listing namespaces via Kubernetes API (field.cattle.io/projectId)."""
        kubeconfig = """
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
      token: token
contexts:
  - name: ctx
    context:
      cluster: cluster
      user: user
current-context: ctx
"""
        expected_namespaces = [
            Namespace(id="local:namespace1", name="namespace1", project_id="local:p-456")
        ]

        with patch.object(client, "generate_kubeconfig", return_value=kubeconfig):
            with patch(
                "quotactl.rancher_client.KubernetesClient"
            ) as mock_k8s_cls:
                mock_k8s = Mock()
                mock_k8s.list_namespaces_in_project.return_value = expected_namespaces
                mock_k8s_cls.from_kubeconfig.return_value = mock_k8s

                namespaces = client.list_namespaces("local:p-456")
                assert len(namespaces) == 1
                assert namespaces[0].name == "namespace1"

    def test_find_project_by_name(self, client):
        """Test finding project by name."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "p-123",
                    "name": "project1",
                    "clusterId": "c-456",
                    "resourceQuota": {},
                },
                {
                    "id": "p-789",
                    "name": "project2",
                    "clusterId": "c-456",
                    "resourceQuota": {},
                },
            ]
        }
        mock_response.raise_for_status = Mock()

        with patch.object(client.session, "get", return_value=mock_response):
            project = client.find_project_by_name("c-456", "project1")
            assert project is not None
            assert project.id == "p-123"
            assert project.name == "project1"

            project = client.find_project_by_name("c-456", "nonexistent")
            assert project is None

    def test_authentication_error(self, client):
        """Test handling authentication error."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )

        with patch.object(client.session, "get", return_value=mock_response):
            with pytest.raises(RancherAPIError, match="Authentication failed"):
                client.get_cluster("c-123")

    def test_not_found_error(self, client):
        """Test handling not found error."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )

        with patch.object(client.session, "get", return_value=mock_response):
            with pytest.raises(RancherAPIError, match="Resource not found"):
                client.get_cluster("c-123")

    def test_retry_on_server_error(self, client):
        """Test retry logic on server errors."""
        mock_response_500 = Mock()
        mock_response_500.status_code = 500
        mock_response_500.text = "Internal Server Error"
        mock_response_500.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response_500
        )

        mock_response_200 = Mock()
        mock_response_200.json.return_value = {"id": "c-123"}
        mock_response_200.raise_for_status = Mock()

        with patch.object(
            client.session, "get", side_effect=[mock_response_500, mock_response_200]
        ), patch("time.sleep"):  # Mock sleep to speed up test
            result = client.get_cluster("c-123")
            assert result["id"] == "c-123"

