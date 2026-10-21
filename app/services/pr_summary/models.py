from typing import List, Optional, Literal, Dict, Any

try:
    from pydantic import BaseModel, Field
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False

    def Field(default=None, default_factory=None, **kwargs):
        if default_factory is not None:
            return default_factory()
        return default

    class BaseModel:
        def __init__(self, **kwargs):
            # Initialize annotations and defaults
            for cls in reversed(self.__class__.__mro__):
                for key, val in cls.__dict__.items():
                    if not key.startswith("_") and not callable(val):
                        setattr(self, key, val() if callable(val) else val)
            for k, v in kwargs.items():
                setattr(self, k, v)

        def dict(self):
            def _to_dict(obj):
                if isinstance(obj, BaseModel):
                    return {k: _to_dict(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
                elif isinstance(obj, list):
                    return [_to_dict(item) for item in obj]
                elif isinstance(obj, dict):
                    return {k: _to_dict(v) for k, v in obj.items()}
                return obj
            return _to_dict(self)

        def model_dump(self):
            return self.dict()

        def model_dump_json(self, **kwargs):
            import json
            indent = kwargs.get("indent")
            return json.dumps(self.dict(), indent=indent)

class PRDetails(BaseModel):
    number: int
    head_sha: str
    base_sha: str
    title: str
    author: str
    files_changed: int
    additions: int
    deletions: int

class FindingSummaryItem(BaseModel):
    finding_id: Optional[str] = None
    fingerprint: str
    severity: str  # critical | high | medium | low
    rule_id: str
    message: str
    file: str
    line: int
    has_verified_fix: Optional[bool] = None
    fix_attempt_id: Optional[str] = None

class FindingsGroup(BaseModel):
    new: List[FindingSummaryItem] = Field(default_factory=list)
    fixed: List[FindingSummaryItem] = Field(default_factory=list)
    existing_touched: List[FindingSummaryItem] = Field(default_factory=list)
    hidden_existing_count: int = 0

class DependencyChange(BaseModel):
    ecosystem: str  # pip | npm | go
    name: str
    change_type: str  # added | removed | updated
    version: Optional[str] = None
    previous_version: Optional[str] = None
    manifest_file: str

class PushDelta(BaseModel):
    new_count: int = 0
    fixed_count: int = 0
    delta_new: int = 0
    delta_fixed: int = 0
    previous_head_sha: Optional[str] = None

class ActionItem(BaseModel):
    priority: int  # 1 (Critical), 2 (Secrets rotate first), 3 (High), 4 (Workflow/Dependency), 5 (Medium)
    category: str
    title: str
    description: str
    finding_id: Optional[str] = None
    fingerprint: Optional[str] = None
    file: Optional[str] = None
    line: Optional[int] = None

class PRSummaryFacts(BaseModel):
    version: int = 1
    pr: PRDetails
    categories_touched: List[str] = Field(default_factory=list)
    findings: FindingsGroup
    dependency_changes: List[DependencyChange] = Field(default_factory=list)
    delta_since_previous_push: PushDelta
    verdict: Literal["block", "attention", "safe"]
    reasons: List[str] = Field(default_factory=list)
    actions: List[ActionItem] = Field(default_factory=list)
    omitted_actions_count: int = 0
