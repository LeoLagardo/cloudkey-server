import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, func

from app.database import AsyncSessionLocal
from app.models.operation import NightAudit
from app.models.property import Property
from app.models.property_settings import PropertySettings
from app.services.night_audit_service import night_audit_service
from app.utils.enums import EntityStatus, NightAuditStatus

logger = logging.getLogger("cloudkey.scheduler")

scheduler = AsyncIOScheduler()


async def check_and_run_scheduled_night_audits():
    """
    Periodic job executed every 1 minute by APScheduler.
    Finds active properties configured with night_audit_mode == 'AUTO'.
    Evaluates whether the property's local time has reached or passed night_audit_time.
    If today's audit has not run yet, executes the night audit atomically.
    """
    async with AsyncSessionLocal() as db:
        try:
            # Query all active properties with AUTO night audit mode
            stmt = (
                select(Property, PropertySettings)
                .join(PropertySettings, Property.id == PropertySettings.property_id)
                .where(
                    Property.status == EntityStatus.ACTIVE.value,
                    PropertySettings.night_audit_mode == "AUTO",
                )
            )
            result = await db.execute(stmt)
            active_properties = result.all()

            for prop, settings in active_properties:
                try:
                    # 1. Resolve local time in property's timezone
                    tz_name = prop.timezone or "Asia/Kolkata"
                    try:
                        tz = ZoneInfo(tz_name)
                    except Exception:
                        tz = ZoneInfo("UTC")

                    now_local = datetime.now(tz)
                    current_local_time = now_local.time()

                    # 2. Check if property local time has reached scheduled audit time (e.g. 13:00)
                    if current_local_time < settings.night_audit_time:
                        continue

                    # 3. Check if business date has already rolled past today's calendar date
                    if prop.business_date > now_local.date():
                        continue

                    # 4. Check if today's business date is already audited or currently running
                    stmt_audit = select(NightAudit).where(
                        NightAudit.property_id == prop.id,
                        NightAudit.business_date == prop.business_date,
                    )
                    audit_res = await db.execute(stmt_audit)
                    existing_audit = audit_res.scalar_one_or_none()

                    if existing_audit and existing_audit.status in (
                        NightAuditStatus.COMPLETED.value,
                        NightAuditStatus.RUNNING.value,
                    ):
                        continue

                    # 5. Check if an audit was already executed and completed on today's calendar day
                    stmt_today_audit = select(NightAudit).where(
                        NightAudit.property_id == prop.id,
                        NightAudit.status == NightAuditStatus.COMPLETED.value,
                        func.date(NightAudit.completed_at) == now_local.date(),
                    )
                    if (await db.execute(stmt_today_audit)).scalars().first():
                        continue

                    # 4. Trigger Night Audit
                    logger.info(
                        f"[APScheduler] Triggering automated Night Audit for Property '{prop.name}' "
                        f"({prop.id}) on business date {prop.business_date} (local time: {now_local.strftime('%H:%M:%S')} {tz_name})"
                    )
                    config = settings.night_audit_config or {}
                    auto_no_show = config.get("auto_no_show", True)
                    await night_audit_service.execute_night_audit(
                        db=db,
                        property_id=prop.id,
                        run_by=None,
                        trigger_type="SCHEDULED",
                        auto_no_show=auto_no_show,
                    )

                except Exception as prop_err:
                    logger.error(
                        f"[APScheduler] Error during automated Night Audit for Property {prop.id}: {prop_err}",
                        exc_info=True,
                    )
                    continue

        except Exception as global_err:
            logger.error(f"[APScheduler] Global poller error: {global_err}", exc_info=True)


def start_scheduler():
    """Registers the 1-minute poller and starts APScheduler."""
    if not scheduler.running:
        scheduler.add_job(
            check_and_run_scheduled_night_audits,
            trigger=IntervalTrigger(minutes=1),
            id="night_audit_1min_poller",
            name="Night Audit 1-Minute Poller",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()
        logger.info("[APScheduler] Night Audit 1-minute poller started.")


def stop_scheduler():
    """Stops APScheduler on application shutdown."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[APScheduler] Night Audit poller stopped.")
