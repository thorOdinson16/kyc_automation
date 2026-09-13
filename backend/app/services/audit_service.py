from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit_log import AuditLog
from typing import Dict, Any
from uuid import UUID
from datetime import datetime
from app.database import AsyncSessionLocal
import numpy as np


class AuditService:

    @staticmethod
    def _sanitize_json(data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert numpy types -> native Python for JSONB."""
        def convert(v):
            if isinstance(v, np.bool_):
                return bool(v)
            if isinstance(v, (np.float32, np.float64)):
                return float(v)
            if isinstance(v, (np.int32, np.int64)):
                return int(v)
            if isinstance(v, dict):
                return {k: convert(vv) for k, vv in v.items()}
            if isinstance(v, list):
                return [convert(x) for x in v]
            return v

        return {k: convert(v) for k, v in data.items()}

    @staticmethod
    async def log_action(
        db: AsyncSession | None,
        application_id: UUID,
        action_type: str,
        action_details: Dict,
        actor: str = "system"
    ):
        """Create immutable audit log entry safely."""

        # 🔥 Sanitize JSON before inserting
        action_details = AuditService._sanitize_json(action_details)

        if db is None:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    log = AuditLog(
                        application_id=application_id,
                        action_type=action_type,
                        action_details=action_details,
                        timestamp=datetime.utcnow(),
                        actor=actor,
                    )
                    session.add(log)
            return log

        log = AuditLog(
            application_id=application_id,
            action_type=action_type,
            action_details=action_details,
            timestamp=datetime.utcnow(),
            actor=actor,
        )

        db.add(log)
        await db.flush()  # safe in open tx
        return log

    @staticmethod
    async def get_application_audit_trail(
        db: AsyncSession,
        application_id: UUID
    ):
        from sqlalchemy import select

        query = (
            select(AuditLog)
            .where(AuditLog.application_id == application_id)
            .order_by(AuditLog.timestamp)
        )

        result = await db.execute(query)
        return result.scalars().all()


audit_service = AuditService()