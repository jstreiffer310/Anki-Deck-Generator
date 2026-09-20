"""
Ollama Runtime Manager: Docker Desktop Container Auto-Initialization & Zero-Dependency HTTP Client
Part of AnkiDeckCreator semantic knowledge formulation pipeline.

Features:
- Auto-initialization of Docker container 'anki-ollama' (with persistent named volume anki-ollama-models).
- Automatic health checking against localhost:11434 (/api/tags).
- Zero external dependencies: implemented exclusively via Python standard library (urllib, json, subprocess).
- Model availability verification and auto-pulling (/api/pull).
- Structured JSON generation via Ollama's grammar-constrained sampling (/api/generate).
- Graceful offline error handling: returns False/None on failure without crashing or throwing uncaught exceptions.
"""

import json
import logging
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ollama_runtime")


class OllamaRuntimeManager:
    """
    Manages Docker Desktop lifecycle and HTTP REST interactions for Ollama.
    Enforces isolated containerization using Docker Desktop without external dependencies.
    """

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "llama3.2:1b",
        timeout: float = 20.0,
        container_name: str = "anki-ollama",
    ):
        """
        Initialize the OllamaRuntimeManager.

        Args:
            host: Base URL of the Ollama HTTP daemon (default: http://localhost:11434).
            model: Default model identifier (default: llama3.2:1b).
            timeout: Readiness check timeout in seconds (default: 20.0).
            container_name: Name of the Docker container (default: anki-ollama).
        """
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = float(timeout)
        self.container_name = container_name

    def is_service_ready(self, timeout: float = 3.0) -> bool:
        """
        Pings Ollama /api/tags endpoint to check whether the HTTP API is responsive.

        Args:
            timeout: Maximum seconds to wait for ping response.

        Returns:
            True if HTTP status is 200, False otherwise.
        """
        try:
            req = urllib.request.Request(f"{self.host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status == 200
        except Exception as e:
            logger.debug("Ollama ping failed at %s/api/tags: %s", self.host, e)
            return False

    def list_models(self, timeout: float = 5.0) -> List[str]:
        """
        Retrieves list of installed model tags and base names from Ollama.

        Args:
            timeout: Maximum seconds to wait for /api/tags response.

        Returns:
            List of model names/tags available in the Ollama instance.
        """
        try:
            req = urllib.request.Request(f"{self.host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    return []
                data = json.loads(resp.read().decode("utf-8"))
                models = data.get("models", [])
                names: List[str] = []
                for m in models:
                    name = m.get("name")
                    if name:
                        names.append(name)
                        if ":" in name:
                            base = name.split(":", 1)[0]
                            if base not in names:
                                names.append(base)
                return names
        except Exception as e:
            logger.debug("Failed to list models from %s: %s", self.host, e)
            return []

    def ensure_docker_container(self, poll_timeout: Optional[float] = None) -> bool:
        """
        Inspects Docker container state and starts or runs the container if needed.
        Polls for HTTP readiness up to poll_timeout seconds.

        Args:
            poll_timeout: Max seconds to wait for readiness. Defaults to self.timeout.

        Returns:
            True if container is running and service is ready, False otherwise.
        """
        max_wait = poll_timeout if poll_timeout is not None else self.timeout

        # Verify docker CLI exists on PATH
        if not shutil.which("docker"):
            logger.warning("[OLLAMA] 'docker' CLI not found on PATH.")
            return False

        try:
            # Query container presence and status
            cmd = [
                "docker", "ps", "-a",
                "--filter", f"name={self.container_name}",
                "--format", "{{.Names}}\t{{.Status}}"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode != 0:
                logger.warning(
                    "[OLLAMA] Docker daemon query failed (exit %d): %s",
                    res.returncode, res.stderr.strip() or res.stdout.strip()
                )
                return False

            lines = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
            container_found = False
            is_running = False

            for line in lines:
                parts = line.split("\t", 1)
                name = parts[0].strip()
                status = parts[1].strip() if len(parts) > 1 else ""

                if name == self.container_name or name == f"/{self.container_name}":
                    container_found = True
                    if "Up" in status:
                        is_running = True
                    break

            if not container_found:
                logger.info(
                    "[OLLAMA] Container '%s' not found. Creating container with persistent volume...",
                    self.container_name
                )
                run_cmd = [
                    "docker", "run", "-d",
                    "-p", "11434:11434",
                    "-v", "anki-ollama-models:/root/.ollama",
                    "--name", self.container_name,
                    "ollama/ollama"
                ]
                run_res = subprocess.run(run_cmd, capture_output=True, text=True, timeout=30)
                if run_res.returncode != 0:
                    logger.warning(
                        "[OLLAMA] Failed to create container '%s': %s",
                        self.container_name, run_res.stderr.strip() or run_res.stdout.strip()
                    )
                    return False
            elif not is_running:
                logger.info("[OLLAMA] Container '%s' is stopped. Starting...", self.container_name)
                start_res = subprocess.run(
                    ["docker", "start", self.container_name],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                if start_res.returncode != 0:
                    logger.warning(
                        "[OLLAMA] Failed to start container '%s': %s",
                        self.container_name, start_res.stderr.strip() or start_res.stdout.strip()
                    )
                    return False
            else:
                logger.info("[OLLAMA] Container '%s' is already running.", self.container_name)

            # Poll for HTTP readiness
            logger.info("[OLLAMA] Waiting up to %.1fs for Ollama daemon readiness...", max_wait)
            start_time = time.time()
            while time.time() - start_time < max_wait:
                if self.is_service_ready():
                    logger.info("[OLLAMA] Service is ready on %s.", self.host)
                    return True
                time.sleep(0.5)

            logger.warning("[OLLAMA] Timed out waiting for Ollama service to become ready.")
            return False

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.warning("[OLLAMA] Docker execution error: %s", e)
            return False
        except Exception as e:
            logger.warning("[OLLAMA] Unexpected error managing Docker container: %s", e)
            return False

    def ensure_service_ready(self, auto_start_docker: bool = True) -> bool:
        """
        Ensures Ollama service is available. If not currently responding and
        auto_start_docker is True, attempts to launch/start the container.

        Args:
            auto_start_docker: Whether to invoke Docker if service is not responding.

        Returns:
            True if service is ready, False otherwise.
        """
        if self.is_service_ready():
            return True

        if auto_start_docker:
            return self.ensure_docker_container()

        return False

    def ensure_model_available(
        self,
        model: Optional[str] = None,
        pull_timeout: float = 300.0
    ) -> bool:
        """
        Verifies that the target model is installed locally. If not found,
        triggers an auto-pull via Ollama's /api/pull endpoint.

        Args:
            model: Specific model name to verify. Defaults to self.model.
            pull_timeout: Maximum seconds to allow for pulling model weights.

        Returns:
            True if model is available or successfully pulled, False otherwise.
        """
        target_model = model or self.model
        installed = self.list_models()

        # Check exact or prefix match
        if (
            target_model in installed
            or f"{target_model}:latest" in installed
            or any(m == target_model or m.startswith(f"{target_model}:") for m in installed)
        ):
            return True

        logger.info(
            "[OLLAMA] Model '%s' not found locally. Initiating pull (timeout: %.0fs)...",
            target_model, pull_timeout
        )

        try:
            payload = json.dumps({"name": target_model, "stream": False}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.host}/api/pull",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=pull_timeout) as resp:
                if resp.status == 200:
                    body = json.loads(resp.read().decode("utf-8"))
                    if body.get("status") == "success":
                        logger.info("[OLLAMA] Model '%s' pulled successfully.", target_model)
                        return True
                    # Some Ollama versions return status like "pulling manifest", "verifying sha256 digest"
                    # If stream is false and HTTP 200 returned without error key, verify presence
                    if "error" not in body:
                        return True
                logger.warning("[OLLAMA] Pull request returned status %d", resp.status)
                return False
        except Exception as e:
            logger.warning("[OLLAMA] Failed to pull model '%s': %s", target_model, e)
            return False

    def generate_json(
        self,
        prompt: str,
        system_prompt: str = "",
        model: Optional[str] = None,
        timeout: float = 30.0,
        temperature: float = 0.1,
    ) -> Optional[Dict[str, Any]]:
        """
        Invokes Ollama's /api/generate endpoint with format="json" and returns
        the parsed Python dictionary.

        Args:
            prompt: User/input prompt for the LLM.
            system_prompt: Optional system prompt to steer formulation.
            model: Specific model identifier. Defaults to self.model.
            timeout: Maximum seconds to wait for generation.
            temperature: Sampling temperature (default: 0.1 for deterministic extraction).

        Returns:
            Parsed JSON dictionary, or None if generation/parsing failed.
        """
        target_model = model or self.model
        payload: Dict[str, Any] = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": temperature
            }
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.host}/api/generate",
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    logger.warning("[OLLAMA] Generation failed with HTTP status %d", resp.status)
                    return None

                raw_body = resp.read().decode("utf-8")
                envelope = json.loads(raw_body)
                content = envelope.get("response", "").strip()

                # Clean optional markdown encapsulation
                if content.startswith("```json"):
                    content = content[7:]
                elif content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    return parsed
                logger.warning("[OLLAMA] Model response is not a JSON object: %s", type(parsed))
                return None

        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
            logger.warning("[OLLAMA] HTTP / Network error during generation: %s", e)
            return None
        except json.JSONDecodeError as e:
            logger.warning("[OLLAMA] Failed to decode JSON from model response: %s", e)
            return None
        except Exception as e:
            logger.warning("[OLLAMA] Unexpected error during JSON generation: %s", e)
            return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ollama Runtime Manager CLI Probe")
    parser.add_argument("--check", action="store_true", help="Check if Ollama service is responsive")
    parser.add_argument("--init", action="store_true", help="Ensure container is running and service is ready")
    parser.add_argument("--list-models", action="store_true", help="List installed models")
    parser.add_argument("--model", type=str, default="llama3.2:1b", help="Model name to check/pull")
    parser.add_argument("--pull", action="store_true", help="Pull target model if missing")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    mgr = OllamaRuntimeManager(model=args.model)

    if args.check:
        ready = mgr.is_service_ready()
        print(f"Service ready: {ready}")
    elif args.init:
        ready = mgr.ensure_service_ready(auto_start_docker=True)
        print(f"Service initialized: {ready}")
    elif args.list_models:
        print("Installed models:", mgr.list_models())
    elif args.pull:
        available = mgr.ensure_model_available(args.model)
        print(f"Model '{args.model}' available: {available}")
    else:
        ready = mgr.is_service_ready()
        print(f"Ollama status at {mgr.host}: {'Online' if ready else 'Offline'}")
