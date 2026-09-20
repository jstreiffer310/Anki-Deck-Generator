"""
Unit tests for OllamaRuntimeManager (Milestone 1).
Verifies Docker Desktop lifecycle management, zero-dependency REST client,
model pulling, structured JSON generation, and defensive offline fallback.
"""

import io
import json
import socket
import subprocess
import urllib.error
from unittest.mock import MagicMock, call, patch
import pytest

from scripts.ollama_runtime import OllamaRuntimeManager


class TestOllamaRuntimeManagerInit:
    """Tests initialization and configuration of OllamaRuntimeManager."""

    def test_default_initialization(self):
        mgr = OllamaRuntimeManager()
        assert mgr.host == "http://localhost:11434"
        assert mgr.model == "llama3.2:1b"
        assert mgr.timeout == 20.0
        assert mgr.container_name == "anki-ollama"

    def test_custom_initialization_and_host_normalization(self):
        mgr = OllamaRuntimeManager(
            host="http://localhost:11434///",
            model="qwen2.5:1.5b",
            timeout=15.0,
            container_name="custom-ollama",
        )
        assert mgr.host == "http://localhost:11434"
        assert mgr.model == "qwen2.5:1.5b"
        assert mgr.timeout == 15.0
        assert mgr.container_name == "custom-ollama"


class TestServiceReady:
    """Tests is_service_ready HTTP ping functionality."""

    @patch("urllib.request.urlopen")
    def test_is_service_ready_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        mgr = OllamaRuntimeManager()
        assert mgr.is_service_ready() is True
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://localhost:11434/api/tags"
        assert req.get_method() == "GET"

    @patch("urllib.request.urlopen")
    def test_is_service_ready_connection_refused(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError(ConnectionRefusedError("Connection refused"))
        mgr = OllamaRuntimeManager()
        assert mgr.is_service_ready() is False

    @patch("urllib.request.urlopen")
    def test_is_service_ready_timeout(self, mock_urlopen):
        mock_urlopen.side_effect = TimeoutError("Request timed out")
        mgr = OllamaRuntimeManager()
        assert mgr.is_service_ready() is False

    @patch("urllib.request.urlopen")
    def test_is_service_ready_socket_timeout(self, mock_urlopen):
        mock_urlopen.side_effect = socket.timeout("Socket timed out")
        mgr = OllamaRuntimeManager()
        assert mgr.is_service_ready() is False

    @patch("urllib.request.urlopen")
    def test_is_service_ready_http_error(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 503
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        mgr = OllamaRuntimeManager()
        assert mgr.is_service_ready() is False


class TestListModels:
    """Tests list_models method."""

    @patch("urllib.request.urlopen")
    def test_list_models_success(self, mock_urlopen):
        payload = {
            "models": [
                {"name": "llama3.2:1b", "size": 1321098240},
                {"name": "deepseek-r1:1.5b", "size": 1100000000},
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(payload).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        mgr = OllamaRuntimeManager()
        models = mgr.list_models()
        assert "llama3.2:1b" in models
        assert "llama3.2" in models
        assert "deepseek-r1:1.5b" in models
        assert "deepseek-r1" in models

    @patch("urllib.request.urlopen")
    def test_list_models_network_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Network unreachable")
        mgr = OllamaRuntimeManager()
        models = mgr.list_models()
        assert models == []


class TestDockerContainerManagement:
    """Tests ensure_docker_container and ensure_service_ready."""

    @patch.object(OllamaRuntimeManager, "is_service_ready")
    def test_ensure_service_ready_when_already_up(self, mock_ready):
        mock_ready.return_value = True
        mgr = OllamaRuntimeManager()
        assert mgr.ensure_service_ready() is True

    @patch("shutil.which")
    def test_ensure_docker_container_docker_not_on_path(self, mock_which):
        mock_which.return_value = None
        mgr = OllamaRuntimeManager()
        assert mgr.ensure_docker_container() is False

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_ensure_docker_container_daemon_offline(self, mock_which, mock_run):
        mock_which.return_value = "C:\\Program Files\\Docker\\Docker\\resources\\bin\\docker.exe"
        # Simulate Docker daemon offline error
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="error during connect: open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified."
        )

        mgr = OllamaRuntimeManager()
        # Must return False gracefully without raising exceptions
        assert mgr.ensure_docker_container() is False

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_ensure_docker_container_daemon_timeout(self, mock_which, mock_run):
        mock_which.return_value = "docker"
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["docker", "ps"], timeout=10)

        mgr = OllamaRuntimeManager()
        assert mgr.ensure_docker_container() is False

    @patch("time.sleep")
    @patch.object(OllamaRuntimeManager, "is_service_ready")
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_ensure_docker_container_already_running(self, mock_which, mock_run, mock_ready, mock_sleep):
        mock_which.return_value = "docker"
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="anki-ollama\tUp 2 hours\n",
            stderr=""
        )
        mock_ready.return_value = True

        mgr = OllamaRuntimeManager()
        assert mgr.ensure_docker_container(poll_timeout=5.0) is True

        # Should NOT invoke docker run or docker start
        assert mock_run.call_count == 1
        assert "ps" in mock_run.call_args[0][0]

    @patch("time.sleep")
    @patch.object(OllamaRuntimeManager, "is_service_ready")
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_ensure_docker_container_stopped_invokes_start(self, mock_which, mock_run, mock_ready, mock_sleep):
        mock_which.return_value = "docker"
        # 1st call: docker ps (shows Exited)
        # 2nd call: docker start
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="anki-ollama\tExited (0) 10 minutes ago\n", stderr=""),
            MagicMock(returncode=0, stdout="anki-ollama\n", stderr=""),
        ]
        mock_ready.side_effect = [False, True]

        mgr = OllamaRuntimeManager()
        assert mgr.ensure_docker_container(poll_timeout=5.0) is True

        assert mock_run.call_count == 2
        start_call = mock_run.call_args_list[1]
        assert start_call[0][0] == ["docker", "start", "anki-ollama"]

    @patch("time.sleep")
    @patch.object(OllamaRuntimeManager, "is_service_ready")
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_ensure_docker_container_missing_invokes_run_with_named_volume(
        self, mock_which, mock_run, mock_ready, mock_sleep
    ):
        mock_which.return_value = "docker"
        # 1st call: docker ps (empty - container not found)
        # 2nd call: docker run
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="container-hash-123\n", stderr=""),
        ]
        mock_ready.side_effect = [False, True]

        mgr = OllamaRuntimeManager()
        assert mgr.ensure_docker_container(poll_timeout=5.0) is True

        assert mock_run.call_count == 2
        run_cmd = mock_run.call_args_list[1][0][0]
        assert run_cmd[0:3] == ["docker", "run", "-d"]
        assert "-p" in run_cmd and "11434:11434" in run_cmd
        assert "-v" in run_cmd and "anki-ollama-models:/root/.ollama" in run_cmd
        assert "--name" in run_cmd and "anki-ollama" in run_cmd
        assert "ollama/ollama" in run_cmd

    @patch("time.sleep")
    @patch.object(OllamaRuntimeManager, "is_service_ready")
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_ensure_docker_container_poll_readiness_timeout(
        self, mock_which, mock_run, mock_ready, mock_sleep
    ):
        mock_which.return_value = "docker"
        mock_run.return_value = MagicMock(returncode=0, stdout="anki-ollama\tUp 1 second\n", stderr="")
        mock_ready.return_value = False

        mgr = OllamaRuntimeManager()
        # Max wait 0.5s -> should poll and return False
        assert mgr.ensure_docker_container(poll_timeout=0.2) is False

    @patch.object(OllamaRuntimeManager, "ensure_docker_container")
    @patch.object(OllamaRuntimeManager, "is_service_ready")
    def test_ensure_service_ready_auto_start_disabled(self, mock_ready, mock_docker):
        mock_ready.return_value = False
        mgr = OllamaRuntimeManager()
        assert mgr.ensure_service_ready(auto_start_docker=False) is False
        mock_docker.assert_not_called()


class TestModelManagement:
    """Tests ensure_model_available."""

    @patch.object(OllamaRuntimeManager, "list_models")
    def test_ensure_model_available_already_installed(self, mock_list):
        mock_list.return_value = ["llama3.2:1b", "llama3.2"]
        mgr = OllamaRuntimeManager(model="llama3.2:1b")
        assert mgr.ensure_model_available() is True

    @patch("urllib.request.urlopen")
    @patch.object(OllamaRuntimeManager, "list_models")
    def test_ensure_model_available_triggers_pull(self, mock_list, mock_urlopen):
        mock_list.return_value = []
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"status": "success"}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        mgr = OllamaRuntimeManager(model="llama3.2:1b")
        assert mgr.ensure_model_available() is True

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://localhost:11434/api/pull"
        assert req.get_method() == "POST"
        body = json.loads(req.data.decode("utf-8"))
        assert body == {"name": "llama3.2:1b", "stream": False}

    @patch("urllib.request.urlopen")
    @patch.object(OllamaRuntimeManager, "list_models")
    def test_ensure_model_available_pull_fails(self, mock_list, mock_urlopen):
        mock_list.return_value = []
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="http://localhost:11434/api/pull",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=io.BytesIO(b'{"error": "pull failed"}')
        )

        mgr = OllamaRuntimeManager(model="llama3.2:1b")
        assert mgr.ensure_model_available() is False


class TestGenerateJson:
    """Tests generate_json parsing and error handling."""

    @patch("urllib.request.urlopen")
    def test_generate_json_success(self, mock_urlopen):
        card_content = {
            "keyword": "Tolerance",
            "descriptor": "A state of progressively decreasing responsiveness to a drug.",
            "card_type": "definition",
            "bidirectional": True
        }
        ollama_envelope = {
            "model": "llama3.2:1b",
            "response": json.dumps(card_content),
            "done": True
        }
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(ollama_envelope).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        mgr = OllamaRuntimeManager()
        result = mgr.generate_json(
            prompt="Extract keyword and descriptor",
            system_prompt="SuperMemo 20 Rules Knowledge Engineer",
            temperature=0.1
        )

        assert result == card_content
        assert result["keyword"] == "Tolerance"

        # Verify request details
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://localhost:11434/api/generate"
        sent_payload = json.loads(req.data.decode("utf-8"))
        assert sent_payload["model"] == "llama3.2:1b"
        assert sent_payload["format"] == "json"
        assert sent_payload["system"] == "SuperMemo 20 Rules Knowledge Engineer"
        assert sent_payload["options"]["temperature"] == 0.1

    @patch("urllib.request.urlopen")
    def test_generate_json_markdown_wrapped_response(self, mock_urlopen):
        card_content = {
            "keyword": "Sensitization",
            "descriptor": "An increase in effectiveness with repeated administration."
        }
        markdown_wrapped = f"```json\n{json.dumps(card_content)}\n```"
        ollama_envelope = {
            "model": "llama3.2:1b",
            "response": markdown_wrapped,
            "done": True
        }
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(ollama_envelope).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        mgr = OllamaRuntimeManager()
        result = mgr.generate_json(prompt="Extract concept")
        assert result == card_content

    @patch("urllib.request.urlopen")
    def test_generate_json_malformed_json_response(self, mock_urlopen):
        ollama_envelope = {
            "model": "llama3.2:1b",
            "response": "This is raw unstructured text without JSON brackets.",
            "done": True
        }
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(ollama_envelope).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        mgr = OllamaRuntimeManager()
        result = mgr.generate_json(prompt="Extract concept")
        assert result is None

    @patch("urllib.request.urlopen")
    def test_generate_json_non_dict_json(self, mock_urlopen):
        ollama_envelope = {
            "model": "llama3.2:1b",
            "response": '["array", "of", "items"]',
            "done": True
        }
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(ollama_envelope).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        mgr = OllamaRuntimeManager()
        result = mgr.generate_json(prompt="Extract concept")
        assert result is None

    @patch("urllib.request.urlopen")
    def test_generate_json_http_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="http://localhost:11434/api/generate",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=io.BytesIO(b'{"error": "model crashed"}')
        )
        mgr = OllamaRuntimeManager()
        result = mgr.generate_json(prompt="Extract concept")
        assert result is None

    @patch("urllib.request.urlopen")
    def test_generate_json_timeout(self, mock_urlopen):
        mock_urlopen.side_effect = TimeoutError("Request timed out")
        mgr = OllamaRuntimeManager()
        result = mgr.generate_json(prompt="Extract concept")
        assert result is None

    @patch("urllib.request.urlopen")
    def test_generate_json_connection_refused(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError(ConnectionRefusedError())
        mgr = OllamaRuntimeManager()
        result = mgr.generate_json(prompt="Extract concept")
        assert result is None
