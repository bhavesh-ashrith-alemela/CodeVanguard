from typing import List, Optional
try:
    from pydantic import BaseModel, Field
except ImportError:
    # Minimal fallback if pydantic is unavailable
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
        def dict(self):
            return self.__dict__

class RepoScanRequest(BaseModel):
    url: str
    branch: Optional[str] = None

class IssueModel(BaseModel):
    id: Optional[int] = None
    scan_id: str
    scanner: str
    rule_id: str
    severity: str
    message: str
    filepath: str
    line_number: int
    col_number: int
    code_snippet: str
    fingerprint: Optional[str] = None
    state: Optional[str] = "open"

class ScanStats(BaseModel):
    total: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0

class ScanDetailModel(BaseModel):
    id: str
    timestamp: str
    filename: str
    file_size: int
    status: str
    error_message: Optional[str] = None
    total_issues: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    source_type: Optional[str] = "paste"
    source_url: Optional[str] = None
    branch: Optional[str] = None
    commit_sha: Optional[str] = None
    duration_ms: Optional[int] = 0
    files_scanned: Optional[int] = 0
    files_skipped: Optional[int] = 0
    progress: Optional[str] = "queued"

class ScanResponse(BaseModel):
    scan: ScanDetailModel
    issues: List[IssueModel]
