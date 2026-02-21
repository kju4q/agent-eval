from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .schema import CaseStudy, SchemaError


DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "case_studies"


class CaseStudyLoadError(RuntimeError):
    pass


def iter_case_study_files(fixtures_dir: Path = DEFAULT_FIXTURES_DIR) -> Iterable[Path]:
    if not fixtures_dir.exists():
        return []
    return sorted(p for p in fixtures_dir.glob("*.json") if p.is_file())


def load_case_studies(fixtures_dir: Path = DEFAULT_FIXTURES_DIR) -> list[CaseStudy]:
    case_studies: list[CaseStudy] = []
    for path in iter_case_study_files(fixtures_dir):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CaseStudyLoadError(f"Invalid JSON in {path}: {exc}") from exc
        try:
            case_study = CaseStudy.from_dict(data)
        except SchemaError as exc:
            raise CaseStudyLoadError(f"Schema error in {path}: {exc}") from exc
        case_studies.append(case_study)
    return case_studies
