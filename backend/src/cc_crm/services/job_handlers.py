"""Handler der Job-Warteschlange (siehe services/job_queue.py). Jeder Handler
liest seine Parameter aus `job.payload` (nur IDs/technische Werte)."""

from __future__ import annotations

import uuid

from cc_crm.models.background_job import BackgroundJob
from cc_crm.models.enums import SourcingSourceType
from cc_crm.services.job_queue import register_handler


@register_handler("security_alert")
def _security_alert(job: BackgroundJob) -> None:
    from cc_crm.services.security_alerts import send_security_alert

    send_security_alert(job.payload["subject"], job.payload["body"])


@register_handler("sourcing.team_pages")
def _sourcing_team_pages(job: BackgroundJob) -> None:
    from cc_crm.services.sourcing import scan_team_pages_in_background

    scan_team_pages_in_background(
        [uuid.UUID(value) for value in job.payload["company_ids"]],
        uuid.UUID(job.payload["run_id"]),
    )


@register_handler("sourcing.areas")
def _sourcing_areas(job: BackgroundJob) -> None:
    from cc_crm.services.sourcing import search_areas_in_background

    search_areas_in_background(
        SourcingSourceType(job.payload["source_type"]),
        list(job.payload["postal_codes"]),
        uuid.UUID(job.payload["run_id"]),
    )


@register_handler("cv.scan")
def _cv_scan(job: BackgroundJob) -> None:
    from cc_crm.services.cv_extraction_jobs import run_scan_job_in_background

    run_scan_job_in_background(
        uuid.UUID(job.payload["job_id"]), job.payload["filename"], job.payload_blob or b""
    )


@register_handler("webhook.deliver")
def _webhook_deliver(job: BackgroundJob) -> None:
    from cc_crm.services.webhooks import deliver

    deliver(job)
