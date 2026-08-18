#!/usr/bin/env python3
"""SkillOpt backend that routes through Switchyard native server.

This replaces the direct Azure OpenAI / OpenAI-compatible backend with
a Switchyard proxy that intelligently routes requests based on task type.

Features:
- Retry logic with exponential backoff
- Configurable timeouts per route
- Telemetry: request/response logging, latency tracking, token counting
- Health monitoring
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Optional
from urllib import error, request

logger = logging.getLogger(__name__)


@dataclass
class SwitchyardTelemetry:
    """Telemetry collector for Switchyard requests."""
    requests: list = field(default_factory=list)
    lock: Lock = field(default_factory=Lock)
    start_time: float = field(default_factory=time.time)
    
    def record_request(
        self,
        route: str,
        messages: list[dict],
        response: Optional[dict] = None,
        error: Optional[str] = None,
        latency_ms: float = 0,
        attempt: int = 1,
        stage: str = "",
    ) -> None:
        """Record a request attempt."""
        record = {
            "timestamp": time.time(),
            "request_id": str(uuid.uuid4())[:8],
            "route": route,
            "model_requested": route,
            "model_selected": response.get("model", "") if response else "",
            "messages_count": len(messages),
            "prompt_chars": sum(len(m.get("content", "")) for m in messages),
            "latency_ms": latency_ms,
            "attempt": attempt,
            "success": error is None,
            "error": error,
            "stage": stage,
            "tokens_prompt": 0,
            "tokens_completion": 0,
            "tokens_total": 0,
            "tokens_cached": 0,
            "cache_hit_ratio": 0.0,
        }
        if response and "usage" in response:
            usage = response["usage"]
            record["tokens_prompt"] = usage.get("prompt_tokens", 0)
            record["tokens_completion"] = usage.get("completion_tokens", 0)
            record["tokens_total"] = usage.get("total_tokens", 0)
            record["model_selected"] = response.get("model", "")
            # NVIDIA (and other OpenAI-compatible providers) expose automatic
            # prefix caching via usage.prompt_tokens_details.cached_tokens.
            # Surface it so we can verify the shared skill/system prompt is
            # being cached across the many per-item target calls.
            details = usage.get("prompt_tokens_details") or {}
            cached = details.get("cached_tokens", 0) if isinstance(details, dict) else 0
            record["tokens_cached"] = cached
            prompt = record["tokens_prompt"]
            record["cache_hit_ratio"] = (cached / prompt) if prompt else 0.0
        
        with self.lock:
            self.requests.append(record)
            logger.debug(f"Telemetry: {record['request_id']} route={route} latency={latency_ms:.0f}ms success={record['success']}")
    
    def get_summary(self) -> dict:
        """Get aggregated telemetry summary."""
        with self.lock:
            if not self.requests:
                return {
                    "total_requests": 0,
                    "successful": 0,
                    "failed": 0,
                    "success_rate": 0.0,
                    "uptime_sec": time.time() - self.start_time,
                    "total_tokens": 0,
                    "total_prompt_chars": 0,
                    "total_tokens_cached": 0,
                    "overall_cache_hit_ratio": 0.0,
                    "by_route": {},
                    "errors": [],
                }
            
            successful = [r for r in self.requests if r["success"]]
            failed = [r for r in self.requests if not r["success"]]
            
            by_route = {}
            for r in successful:
                route = r["route"]
                if route not in by_route:
                    by_route[route] = {"count": 0, "total_latency": 0, "tokens_total": 0, "tokens_cached": 0}
                by_route[route]["count"] += 1
                by_route[route]["total_latency"] += r["latency_ms"]
                by_route[route]["tokens_total"] += r["tokens_total"]
                by_route[route]["tokens_cached"] += r.get("tokens_cached", 0)
            
            total_cached = sum(r.get("tokens_cached", 0) for r in successful)
            total_prompt = sum(r["tokens_prompt"] for r in successful)
            return {
                "total_requests": len(self.requests),
                "successful": len(successful),
                "failed": len(failed),
                "success_rate": len(successful) / len(self.requests) if self.requests else 0,
                "uptime_sec": time.time() - self.start_time,
                "total_tokens": sum(r["tokens_total"] for r in successful),
                "total_prompt_chars": sum(r["prompt_chars"] for r in successful),
                "total_tokens_cached": total_cached,
                "overall_cache_hit_ratio": (total_cached / total_prompt) if total_prompt else 0.0,
                "by_route": {
                    route: {
                        "count": data["count"],
                        "avg_latency_ms": data["total_latency"] / data["count"] if data["count"] else 0,
                        "tokens_total": data["tokens_total"],
                        "tokens_cached": data["tokens_cached"],
                        "cache_hit_ratio": (data["tokens_cached"] / data["tokens_total"]) if data["tokens_total"] else 0.0,
                    }
                    for route, data in by_route.items()
                },
                "errors": [r["error"] for r in failed][-10:],  # Last 10 errors
            }
    
    def export_jsonl(self, path: str) -> None:
        """Export all requests as JSONL."""
        with self.lock:
            with open(path, "w") as f:
                for r in self.requests:
                    f.write(json.dumps(r) + "\n")


class SwitchyardBackend:
    """SkillOpt model backend that routes through Switchyard.
    
    Usage:
        backend = SwitchyardBackend(config_path="configs/switchyard_skillopt.toml")
        backend.start()
        
        # Use for different phases
        response = backend.chat(messages, model="nemotron")  # Analyst/reflect (strong)
        response = backend.chat(messages, model="llama70b")  # Rollout/eval (fast)
        response = backend.chat(messages, model="skillopt")  # Classifier (auto)
        
        # Get telemetry
        stats = backend.get_telemetry()
        backend.export_telemetry("telemetry.jsonl")
    """
    
    # Per-route timeout configs (seconds)
    DEFAULT_TIMEOUTS = {
        "nemotron": 300,      # Strong model - allow more time
        "llama70b": 240,      # Fast model
        "lightning": 60,      # Nemotron 3.5 Lightning 30B - very fast
        "skillopt": 180,      # Classifier + selected model
        "default": 240,
    }
    
    # Retry config
    MAX_RETRIES = 3
    BASE_BACKOFF = 2.0  # seconds
    
    def __init__(
        self,
        config_path: str = "configs/switchyard_skillopt.toml",
        default_route: str = "skillopt",
        optimizer_route: str = "nemotron",
        target_route: str = "llama70b",
        timeouts: Optional[dict[str, int]] = None,
        max_retries: int = 3,
    ):
        self.config_path = Path(config_path).expanduser().resolve()
        self.default_route = default_route
        self.optimizer_route = optimizer_route
        self.target_route = target_route
        self.timeouts = {**self.DEFAULT_TIMEOUTS, **(timeouts or {})}
        self.max_retries = max_retries
        
        self.server = None
        self.base_url = None
        self.port = None
        self.telemetry = SwitchyardTelemetry()
        self._start_time = time.time()
    
    def start(self) -> None:
        """Start the native Switchyard server."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Switchyard config not found: {self.config_path}")
        
        from switchyard_rust.server import Server
        
        self.server = Server(str(self.config_path), port=0)
        self.port = self.server.port
        self.base_url = self.server.base_url
        
        logger.info(f"Switchyard server started on port {self.port}: {self.base_url}")
        
        # Wait for health
        for _ in range(50):
            try:
                with request.urlopen(f"{self.base_url}/health", timeout=1) as resp:
                    if resp.status == 200:
                        logger.info("Switchyard server healthy")
                        return
            except Exception:
                pass
            time.sleep(0.1)
        raise RuntimeError("Switchyard server failed to become healthy")
    
    def close(self) -> None:
        """Stop the native server."""
        if self.server:
            self.server.close()
            self.server = None
            logger.info("Switchyard server stopped")
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def _make_request_with_retry(
        self,
        url: str,
        payload: dict,
        timeout: int,
        route: str,
        messages: list[dict],
        stage: str = "",
    ) -> dict:
        """Make HTTP request with exponential backoff retry."""
        last_error = None
        
        for attempt in range(1, self.max_retries + 1):
            start = time.time()
            try:
                req = request.Request(
                    url,
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with request.urlopen(req, timeout=timeout) as resp:
                    response = json.load(resp)
                latency_ms = (time.time() - start) * 1000
                
                self.telemetry.record_request(
                    route=route,
                    messages=messages,
                    response=response,
                    latency_ms=latency_ms,
                    attempt=attempt,
                    stage=stage,
                )
                return response
                
            except error.HTTPError as e:
                latency_ms = (time.time() - start) * 1000
                error_body = e.read().decode() if e.fp else str(e)
                last_error = f"HTTP {e.code}: {error_body}"
                logger.warning(f"Switchyard HTTP {e.code} (attempt {attempt}/{self.max_retries}): {error_body[:200]}")
                
            except error.URLError as e:
                latency_ms = (time.time() - start) * 1000
                last_error = f"URL Error: {e.reason}"
                logger.warning(f"Switchyard connection error (attempt {attempt}/{self.max_retries}): {e.reason}")
                
            except TimeoutError:
                latency_ms = (time.time() - start) * 1000
                last_error = f"Timeout after {timeout}s"
                logger.warning(f"Switchyard timeout (attempt {attempt}/{self.max_retries})")
                
            except Exception as e:
                latency_ms = (time.time() - start) * 1000
                last_error = f"{type(e).__name__}: {e}"
                logger.warning(f"Switchyard error (attempt {attempt}/{self.max_retries}): {e}")
            
            # Record failed attempt
            self.telemetry.record_request(
                route=route,
                messages=messages,
                error=last_error,
                latency_ms=latency_ms,
                attempt=attempt,
                stage=stage,
            )
            
            # Exponential backoff
            if attempt < self.max_retries:
                backoff = self.BASE_BACKOFF * (2 ** (attempt - 1))
                logger.info(f"Retrying in {backoff}s...")
                time.sleep(backoff)
        
        # All retries exhausted
        raise RuntimeError(f"Switchyard request failed after {self.max_retries} attempts: {last_error}")
    
    def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        stage: str = "",
        **kwargs
    ) -> dict:
        """Send a chat completion request through Switchyard with retry logic.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Route ID to use (nemotron, llama70b, skillopt)
            temperature: Sampling temperature
            max_tokens: Max completion tokens
            stage: Training phase tag (rollout/analyst/reflect/gate/selection)
            
        Returns:
            OpenAI-compatible response dict
        """
        if not self.base_url:
            raise RuntimeError("Switchyard backend not started. Call start() first.")
        
        route = model or self.default_route
        timeout = self.timeouts.get(route, self.timeouts["default"])
        
        payload = {
            "model": route,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        payload.update(kwargs)
        
        url = f"{self.base_url}/v1/chat/completions"
        
        return self._make_request_with_retry(url, payload, timeout, route, messages, stage)
    
    def get_stats(self) -> dict:
        """Get server statistics from Switchyard."""
        if not self.base_url:
            return {}
        try:
            with request.urlopen(f"{self.base_url}/v1/stats", timeout=5) as resp:
                return json.load(resp)
        except Exception as e:
            logger.warning(f"Failed to get stats: {e}")
            return {}
    
    def get_telemetry(self) -> dict:
        """Get client-side telemetry summary."""
        summary = self.telemetry.get_summary()
        summary["server_stats"] = self.get_stats()
        return summary
    
    def export_telemetry(self, path: str) -> None:
        """Export telemetry as JSONL."""
        self.telemetry.export_jsonl(path)
        logger.info(f"Telemetry exported to {path}")
    
    def log_summary(self) -> None:
        """Log a summary of all requests."""
        summary = self.get_telemetry()
        logger.info(f"=== Switchyard Telemetry Summary ===")
        logger.info(f"  Uptime: {summary['uptime_sec']:.1f}s")
        logger.info(f"  Requests: {summary['total_requests']} (success: {summary['successful']}, failed: {summary['failed']})")
        logger.info(f"  Success rate: {summary['success_rate']:.1%}")
        logger.info(f"  Total tokens: {summary['total_tokens']}")
        for route, data in summary.get("by_route", {}).items():
            logger.info(f"  {route}: {data['count']} req, {data['avg_latency_ms']:.0f}ms avg, {data['tokens_total']} tokens")
        if summary.get("errors"):
            logger.info(f"  Recent errors: {summary['errors']}")


# Integration with SkillOpt's model module
def configure_switchyard(
    config_path: str = "configs/switchyard_skillopt.toml",
    optimizer_route: str = "nemotron",
    target_route: str = "llama70b",
    timeouts: Optional[dict[str, int]] = None,
    max_retries: int = 3,
) -> SwitchyardBackend:
    """Configure SkillOpt to use Switchyard backend.
    
    This replaces configure_azure_openai / configure_openai_compatible.
    
    Args:
        config_path: Path to Switchyard TOML deployment
        optimizer_route: Route for optimizer/analyst (strong model)
        target_route: Route for target/rollout (fast model)
        timeouts: Per-route timeout overrides (seconds)
        max_retries: Max retry attempts per request
        
    Returns:
        Started SwitchyardBackend instance
    """
    global _switchyard_backend
    backend = SwitchyardBackend(
        config_path=config_path,
        optimizer_route=optimizer_route,
        target_route=target_route,
        timeouts=timeouts,
        max_retries=max_retries,
    )
    backend.start()
    
    # Update global singleton so chat_optimizer/target_switchyard use it
    _switchyard_backend = backend
    
    # Set environment variables so existing OpenAI-compatible code works
    os.environ["OPENAI_BASE_URL"] = f"{backend.base_url}/v1"
    os.environ["OPENAI_API_KEY"] = "switchyard"  # Dummy key
    
    logger.info(f"Switchyard configured: optimizer→{optimizer_route}, target→{target_route}")
    return backend


# Global Switchyard backend instance (singleton pattern for trainer)
_switchyard_backend: SwitchyardBackend | None = None


def _get_switchyard_backend() -> SwitchyardBackend:
    global _switchyard_backend
    if _switchyard_backend is None:
        # Default config - will be overridden by trainer config
        _switchyard_backend = SwitchyardBackend()
        _switchyard_backend.start()
    return _switchyard_backend


def chat_optimizer_switchyard(
    system: str,
    user: str,
    max_completion_tokens: int = 16384,
    retries: int = 5,
    stage: str = "optimizer",
    reasoning_effort: str | None = None,
    timeout: int | None = None,
) -> tuple[str, dict]:
    """SkillOpt-compatible optimizer chat function with retry support."""
    backend = _get_switchyard_backend()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    
    # Use backend's internal retry logic
    for attempt in range(1, retries + 1):
        try:
            response = backend.chat(
                messages, 
                model=backend.optimizer_route, 
                max_tokens=max_completion_tokens,
                stage=stage,
            )
            content = response["choices"][0]["message"]["content"]
            return content, {
                "prompt_tokens": response.get("usage", {}).get("prompt_tokens", 0),
                "completion_tokens": response.get("usage", {}).get("completion_tokens", 0),
                "total_tokens": response.get("usage", {}).get("total_tokens", 0),
            }
        except Exception as e:
            logger.warning(f"Optimizer chat attempt {attempt}/{retries} failed: {e}")
            if attempt == retries:
                raise
            time.sleep(2 ** attempt)
    
    raise RuntimeError("Unreachable")


def chat_target_switchyard(
    system: str,
    user: str,
    max_completion_tokens: int = 16384,
    retries: int = 5,
    stage: str = "target",
    reasoning_effort: str | None = None,
    timeout: int | None = None,
) -> tuple[str, dict]:
    """SkillOpt-compatible target chat function with retry support."""
    backend = _get_switchyard_backend()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    
    for attempt in range(1, retries + 1):
        try:
            response = backend.chat(
                messages, 
                model=backend.target_route, 
                max_tokens=max_completion_tokens,
                stage=stage,
            )
            content = response["choices"][0]["message"]["content"]
            return content, {
                "prompt_tokens": response.get("usage", {}).get("prompt_tokens", 0),
                "completion_tokens": response.get("usage", {}).get("completion_tokens", 0),
                "total_tokens": response.get("usage", {}).get("total_tokens", 0),
            }
        except Exception as e:
            logger.warning(f"Target chat attempt {attempt}/{retries} failed: {e}")
            if attempt == retries:
                raise
            time.sleep(2 ** attempt)
    
    raise RuntimeError("Unreachable")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    with SwitchyardBackend() as backend:
        # Test strong route
        resp = backend.chat(
            [{"role": "user", "content": "Say 'hello from nemotron'"}],
            model="nemotron",
            max_tokens=20
        )
        print(f"Nemotron: {resp['choices'][0]['message']['content']}")
        
        # Test fast route
        resp = backend.chat(
            [{"role": "user", "content": "Say 'hello from llama'"}],
            model="llama70b",
            max_tokens=20
        )
        print(f"Llama70b: {resp['choices'][0]['message']['content']}")
        
        # Test classifier route
        resp = backend.chat(
            [{"role": "user", "content": "What is 2+2?"}],
            model="skillopt",
            max_tokens=20
        )
        print(f"Classifier: {resp['choices'][0]['message']['content']}")
        
        # Print telemetry
        backend.log_summary()
        print(f"Stats: {backend.get_stats()}")