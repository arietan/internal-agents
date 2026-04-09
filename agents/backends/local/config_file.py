"""Local config backend — env vars + YAML files on disk / K8s ConfigMaps."""

import logging
import os
from pathlib import Path
from typing import Any

import yaml

from agents.core.config import ConfigLoader

log = logging.getLogger("backends.local.config")

_YAML_PATHS = {
    "skills": os.environ.get("SKILLS_PATH", "/etc/agent/skills.yaml"),
    "rules": os.environ.get("RULES_PATH", "/etc/agent/rules.yaml"),
    "reviewers": os.environ.get("REVIEWERS_PATH", "/etc/agent/reviewers.yaml"),
}


class FileConfigLoader(ConfigLoader):
    """Reads scalar config from env vars and YAML from filesystem."""

    def get_parameter(self, key: str) -> str:
        return os.environ.get(key, "")

    def load_yaml(self, name: str) -> dict:
        path_str = _YAML_PATHS.get(name) or os.environ.get(f"{name.upper()}_PATH", "")
        if not path_str:
            return {}
        p = Path(path_str)
        if p.exists():
            data = yaml.safe_load(p.read_text())
            return data if isinstance(data, dict) else {}
        log.warning("YAML config '%s' not found at %s", name, path_str)
        return {}

    def get_all(self) -> dict[str, Any]:
        return dict(os.environ)
