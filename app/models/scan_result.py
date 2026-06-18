from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

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

class ScanResponse(BaseModel):
    scan: ScanDetailModel
    issues: List[IssueModel]
