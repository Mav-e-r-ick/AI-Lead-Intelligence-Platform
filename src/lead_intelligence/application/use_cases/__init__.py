"""One module per user-facing action (e.g. import a dataset, clean a dataset)."""

from lead_intelligence.application.use_cases.clean_dataset import CleanDatasetUseCase
from lead_intelligence.application.use_cases.compare_executive import (
    CompareExecutiveUseCase,
)
from lead_intelligence.application.use_cases.detect_inflections import (
    DetectInflectionsUseCase,
)
from lead_intelligence.application.use_cases.enrich_subject import EnrichSubjectUseCase
from lead_intelligence.application.use_cases.import_dataset import ImportDatasetUseCase
from lead_intelligence.application.use_cases.process_executive import (
    ProcessExecutiveUseCase,
)
from lead_intelligence.application.use_cases.resolve_identity import (
    ResolveIdentityUseCase,
)
from lead_intelligence.application.use_cases.verify_contact import (
    VerifyContactUseCase,
)

__all__ = [
    "ImportDatasetUseCase",
    "CleanDatasetUseCase",
    "ResolveIdentityUseCase",
    "EnrichSubjectUseCase",
    "CompareExecutiveUseCase",
    "DetectInflectionsUseCase",
    "VerifyContactUseCase",
    "ProcessExecutiveUseCase",
]
