from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import structlog

from vigia_ai.detection.engine import recommend_state

from .config import FusionConfig
from .engine import fuse_observations
from .models import FusionRunSummary
from .repository import FusionRepository, PersistedFusionResult

logger = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class FusionExecution:
    summary: FusionRunSummary
    persistence: PersistedFusionResult


class FusionService:
    def __init__(self, repository: FusionRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        *,
        config: FusionConfig,
        observed_from: datetime,
        observed_to: datetime,
        as_of: datetime,
        software_version: str,
        code_commit: str,
    ) -> FusionExecution:
        observations = await self._repository.load_observations(
            config=config,
            observed_from=observed_from,
            observed_to=observed_to,
            as_of=as_of,
        )
        started_at = datetime.now(UTC)
        request_id = str(uuid4())
        run = await self._repository.begin_run(
            started_at=started_at,
            as_of=as_of,
            observed_from=observed_from,
            observed_to=observed_to,
            software_version=software_version,
            code_commit=code_commit,
            request_id=request_id,
            config=config,
        )
        logger.info(
            "fusion_started",
            fusion_run_id=str(run.id),
            request_id=request_id,
            as_of=as_of.isoformat(),
        )
        try:
            summary = fuse_observations(observations, config=config, as_of=as_of)
            recommendations = {
                candidate.candidate_id: recommend_state(
                    candidate, config=config, as_of=as_of
                )
                for candidate in summary.candidates
            }
            persisted = await self._repository.persist(
                run,
                summary,
                recommendations,
                config=config,
                code_commit=code_commit,
                software_version=software_version,
                completed_at=datetime.now(UTC),
            )
        except Exception:
            with suppress(Exception):
                await self._repository.fail_run(
                    run,
                    error_code="FUSION_EXECUTION_FAILED",
                    completed_at=datetime.now(UTC),
                )
            logger.error(
                "fusion_failed",
                fusion_run_id=str(run.id),
                request_id=request_id,
                error_code="FUSION_EXECUTION_FAILED",
            )
            raise
        logger.info(
            "fusion_completed",
            fusion_run_id=str(run.id),
            request_id=request_id,
            observations=summary.eligible_observation_count,
            candidates=summary.candidate_count,
            incidents_created=persisted.incidents_created,
            incidents_updated=persisted.incidents_updated,
        )
        return FusionExecution(summary=summary, persistence=persisted)
