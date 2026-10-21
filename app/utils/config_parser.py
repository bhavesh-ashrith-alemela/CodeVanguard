import os
import logging
from typing import Optional, List
from dataclasses import dataclass, field

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    yaml = None

logger = logging.getLogger(__name__)

@dataclass
class CodeVanguardConfig:
    enabled: bool = True
    scan_on_pr: bool = True
    scan_on_push: bool = True
    fail_on: str = "high"  # critical | high | medium | none
    ignore_globs: List[str] = field(default_factory=list)
    pr_comment_enabled: bool = True
    sarif_upload_enabled: bool = True
    scan_drafts: bool = False

def parse_simple_yaml(text: str) -> dict:
    """Safe minimal key-value YAML parser fallback when PyYAML is not installed."""
    data = {}
    current_list_key = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("- ") and current_list_key:
            item = line[2:].strip().strip('"').strip("'")
            data.setdefault(current_list_key, []).append(item)
            continue

        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()

            if not val:
                current_list_key = key
                data[key] = []
                continue

            current_list_key = None
            clean_val = val.strip('"').strip("'")
            if clean_val.lower() == "true":
                data[key] = True
            elif clean_val.lower() == "false":
                data[key] = False
            elif clean_val.isdigit():
                data[key] = int(clean_val)
            else:
                data[key] = clean_val

    return data

def parse_codevanguard_config(repo_dir: str, default_settings: Optional[dict] = None) -> CodeVanguardConfig:
    """
    Parses and validates .codevanguard.yml from the scanned repository workspace.
    If absent or invalid, safely falls back to default database settings without crashing.
    """
    config = CodeVanguardConfig()
    
    # Seed with DB defaults if provided
    if default_settings:
        if "scan_enabled" in default_settings:
            config.enabled = bool(default_settings["scan_enabled"])
        if "scan_on_pr" in default_settings:
            config.scan_on_pr = bool(default_settings["scan_on_pr"])
        if "scan_on_push" in default_settings:
            config.scan_on_push = bool(default_settings["scan_on_push"])
        if "fail_on" in default_settings and default_settings["fail_on"]:
            config.fail_on = str(default_settings["fail_on"]).lower()
        if "pr_comment_enabled" in default_settings:
            config.pr_comment_enabled = bool(default_settings["pr_comment_enabled"])
        if "sarif_upload_enabled" in default_settings:
            config.sarif_upload_enabled = bool(default_settings["sarif_upload_enabled"])
        if "scan_drafts" in default_settings:
            config.scan_drafts = bool(default_settings["scan_drafts"])
        if "ignore_globs" in default_settings:
            globs = default_settings["ignore_globs"]
            if isinstance(globs, str) and globs.strip():
                config.ignore_globs = [g.strip() for g in globs.splitlines() if g.strip()]
            elif isinstance(globs, list):
                config.ignore_globs = globs

    config_paths = [
        os.path.join(repo_dir, ".codevanguard.yml"),
        os.path.join(repo_dir, ".codevanguard.yaml")
    ]

    target_file = None
    for p in config_paths:
        if os.path.isfile(p) and not os.path.islink(p):
            try:
                if os.path.getsize(p) <= 256 * 1024:  # 256 KB max config size
                    target_file = p
                    break
                else:
                    logger.warning(f"Skipping .codevanguard.yml: file size exceeds 256KB cap ({p})")
            except OSError:
                pass

    if not target_file:
        return config

    try:
        with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
            raw_text = f.read(256 * 1024)

        raw_data = None
        if HAS_YAML and yaml:
            raw_data = yaml.safe_load(raw_text)
        else:
            raw_data = parse_simple_yaml(raw_text)

        if not isinstance(raw_data, dict):
            logger.warning(f"Invalid .codevanguard.yml root structure (expected dictionary): {target_file}")
            return config

        # Map and sanitize fields
        if "enabled" in raw_data and isinstance(raw_data["enabled"], bool):
            config.enabled = raw_data["enabled"]
        if "scan_on_pr" in raw_data and isinstance(raw_data["scan_on_pr"], bool):
            config.scan_on_pr = raw_data["scan_on_pr"]
        if "scan_on_push" in raw_data and isinstance(raw_data["scan_on_push"], bool):
            config.scan_on_push = raw_data["scan_on_push"]
        if "fail_on" in raw_data:
            val = str(raw_data["fail_on"]).lower()
            if val in ("critical", "high", "medium", "none"):
                config.fail_on = val
        if "ignore_globs" in raw_data:
            globs = raw_data["ignore_globs"]
            if isinstance(globs, list):
                config.ignore_globs.extend([str(g).strip() for g in globs if str(g).strip()])
            elif isinstance(globs, str):
                config.ignore_globs.extend([g.strip() for g in globs.splitlines() if g.strip()])
            # Cap maximum ignore patterns to 200
            config.ignore_globs = config.ignore_globs[:200]
        if "pr_comment" in raw_data and isinstance(raw_data["pr_comment"], bool):
            config.pr_comment_enabled = raw_data["pr_comment"]
        if "sarif_upload" in raw_data and isinstance(raw_data["sarif_upload"], bool):
            config.sarif_upload_enabled = raw_data["sarif_upload"]
        if "scan_drafts" in raw_data and isinstance(raw_data["scan_drafts"], bool):
            config.scan_drafts = raw_data["scan_drafts"]

    except Exception as e:
        logger.warning(f"Error parsing .codevanguard.yml: {e}. Falling back to default settings.")

    return config
