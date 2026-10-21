import json
import gzip
import base64
import logging
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional
from app.utils.github import get_safe_opener

logger = logging.getLogger(__name__)

SARIF_SCHEMA = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
SARIF_VERSION = "2.1.0"

def generate_sarif_report(
    scan_metadata: dict,
    issues: List[dict]
) -> dict:
    """
    Generates a valid SARIF 2.1.0 object complying with the OASIS SARIF specification.
    Includes rules, results, locations, and deterministic partialFingerprints.
    """
    level_map = {
        "critical": "error",
        "high": "error",
        "medium": "warning",
        "low": "note"
    }

    rules_dict: Dict[str, dict] = {}
    results_list: List[dict] = []

    for iss in issues:
        rule_id = iss.get("rule_id", "CV-UNKNOWN")
        sev = (iss.get("severity") or "medium").lower()
        level = level_map.get(sev, "warning")

        # Collect rule metadata
        if rule_id not in rules_dict:
            title = iss.get("fix_title") or rule_id
            desc = iss.get("fix_description") or iss.get("message") or title
            rule_entry = {
                "id": rule_id,
                "name": title.replace(" ", ""),
                "shortDescription": {"text": title},
                "fullDescription": {"text": desc},
                "defaultConfiguration": {"level": level}
            }
            if iss.get("doc_url"):
                rule_entry["helpUri"] = iss["doc_url"]
            rules_dict[rule_id] = rule_entry

        # Format location
        filepath = iss.get("filepath", "code").replace("\\", "/").strip().lstrip("/")
        line_num = int(iss.get("line_number") or 1)
        col_num = int(iss.get("col_number") or 1)

        result_item = {
            "ruleId": rule_id,
            "level": level,
            "message": {
                "text": iss.get("message", "Static security finding.")
            },
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {
                            "uri": filepath,
                            "uriBaseId": "%SRCROOT%"
                        },
                        "region": {
                            "startLine": line_num,
                            "startColumn": col_num
                        }
                    }
                }
            ]
        }

        # Embed deterministic fingerprint
        fp = iss.get("fingerprint")
        if fp:
            result_item["partialFingerprints"] = {
                "codevanguard/v1": fp
            }

        results_list.append(result_item)

    sarif_doc = {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "CodeVanguard",
                        "organization": "CodeVanguard SAST",
                        "semanticVersion": "1.0.0",
                        "informationUri": "https://github.com/codevanguard/codevanguard",
                        "rules": list(rules_dict.values())
                    }
                },
                "results": results_list
            }
        ]
    }

    return sarif_doc

def upload_sarif_to_github(
    owner: str,
    repo: str,
    commit_sha: str,
    ref: str,
    sarif_data: dict,
    auth_token: str
) -> bool:
    """
    Compresses SARIF using gzip, encodes in base64, and uploads to GitHub Code Scanning API.
    Gracefully catches cases where GitHub Advanced Security is not enabled (e.g. private repos)
    without interrupting the scan pipeline.
    """
    api_url = f"https://api.github.com/repos/{owner}/{repo}/code-scanning/sarifs"
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "CodeVanguard-SAST/1.0",
        "Content-Type": "application/json"
    }

    try:
        json_bytes = json.dumps(sarif_data).encode("utf-8")
        compressed = gzip.compress(json_bytes)
        b64_sarif = base64.b64encode(compressed).decode("ascii")

        clean_ref = ref if ref.startswith("refs/") else f"refs/heads/{ref}"

        payload = {
            "commit_sha": commit_sha,
            "ref": clean_ref,
            "sarif": b64_sarif
        }

        req = urllib.request.Request(api_url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        opener = get_safe_opener()

        with opener.open(req, timeout=20) as resp:
            data = json.loads(resp.read(10 * 1024 * 1024).decode("utf-8"))
            sarif_id = data.get("id")
            logger.info(f"Successfully uploaded SARIF to GitHub Code Scanning (job: {sarif_id})")
            return True

    except urllib.error.HTTPError as he:
        if he.code in (403, 404):
            # 403 or 404 typically occurs on private repositories without GitHub Advanced Security license
            logger.info(f"GitHub Code Scanning SARIF upload skipped ({he.code}): GitHub Advanced Security may not be enabled on this repo.")
        else:
            logger.warning(f"GitHub Code Scanning SARIF upload error ({he.code}): {he.reason}")
        return False
    except Exception as e:
        logger.warning(f"Failed to upload SARIF report to GitHub: {e}")
        return False
