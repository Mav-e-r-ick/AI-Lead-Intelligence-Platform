"""Repository *interfaces* (contracts) for loading/saving entities.

The concrete implementations (e.g. a SQLAlchemy-backed repository) belong in
infrastructure/database/, not here. Every interface here is generic over a
placeholder TypeVar entity type — the concrete domain entities (DigitalTwin,
Observation, Snapshot, ...) are a future task; these contracts are honest
about that instead of being bound to fabricated placeholder classes.

See ../README.md and docs/ for the approved Persistence Architecture this
module implements.
"""

from __future__ import annotations

from lead_intelligence.domain.repositories.ai_insight_repository import (
    AIInsightRepository,
)
from lead_intelligence.domain.repositories.audit_log_repository import (
    AuditLogRepository,
)
from lead_intelligence.domain.repositories.base_repository import (
    AppendOnlyRepository,
    MutableRepository,
    Repository,
)
from lead_intelligence.domain.repositories.company_repository import CompanyRepository
from lead_intelligence.domain.repositories.digital_twin_repository import (
    DigitalTwinRepository,
)
from lead_intelligence.domain.repositories.lead_repository import LeadRepository
from lead_intelligence.domain.repositories.observation_repository import (
    ObservationRepository,
)
from lead_intelligence.domain.repositories.outreach_history_repository import (
    OutreachHistoryRepository,
)
from lead_intelligence.domain.repositories.relationship_repository import (
    RelationshipRepository,
)
from lead_intelligence.domain.repositories.snapshot_repository import SnapshotRepository
from lead_intelligence.domain.repositories.unit_of_work import UnitOfWork
from lead_intelligence.domain.repositories.verification_repository import (
    VerificationRepository,
)

__all__ = [
    "Repository",
    "AppendOnlyRepository",
    "MutableRepository",
    "UnitOfWork",
    "DigitalTwinRepository",
    "CompanyRepository",
    "ObservationRepository",
    "SnapshotRepository",
    "RelationshipRepository",
    "VerificationRepository",
    "AIInsightRepository",
    "LeadRepository",
    "OutreachHistoryRepository",
    "AuditLogRepository",
]
