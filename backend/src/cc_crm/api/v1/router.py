from fastapi import APIRouter, Depends

from cc_crm.api.dependencies import get_current_user
from cc_crm.api.v1.activities import router as activities_router
from cc_crm.api.v1.approvals import router as approvals_router
from cc_crm.api.v1.audit_logs import router as audit_logs_router
from cc_crm.api.v1.auth import router as auth_router
from cc_crm.api.v1.calendar_events import router as calendar_events_router
from cc_crm.api.v1.calendar_feed import router as calendar_feed_router
from cc_crm.api.v1.candidates import router as candidates_router
from cc_crm.api.v1.clients import router as clients_router
from cc_crm.api.v1.contacts import router as contacts_router
from cc_crm.api.v1.deletion_requests import router as deletion_requests_router
from cc_crm.api.v1.geo import router as geo_router
from cc_crm.api.v1.imports import router as imports_router
from cc_crm.api.v1.jobs import router as jobs_router
from cc_crm.api.v1.kpi import router as kpi_router
from cc_crm.api.v1.mail_accounts import public_router as mail_accounts_public_router
from cc_crm.api.v1.mail_accounts import router as mail_accounts_router
from cc_crm.api.v1.mail_send import router as mail_send_router
from cc_crm.api.v1.mailing_groups import router as mailing_groups_router
from cc_crm.api.v1.matching import router as matching_router
from cc_crm.api.v1.nl_search import router as nl_search_router
from cc_crm.api.v1.notes import router as notes_router
from cc_crm.api.v1.operational import router as operational_router
from cc_crm.api.v1.profile_generator import router as profile_generator_router
from cc_crm.api.v1.recruiting import router as recruiting_router
from cc_crm.api.v1.region_modifiers import router as region_modifiers_router
from cc_crm.api.v1.sequences import router as sequences_router
from cc_crm.api.v1.sourcing import router as sourcing_router
from cc_crm.api.v1.submissions import router as submissions_router
from cc_crm.api.v1.system import router as system_router
from cc_crm.api.v1.tasks import router as tasks_router
from cc_crm.api.v1.users import router as users_router

api_router = APIRouter()
api_router.include_router(system_router, tags=["system"])
api_router.include_router(auth_router, tags=["auth"])
# Kein Bearer-Auth moeglich (Outlook-Abo einer Internet-URL) - eigener,
# token-basierter Schutz direkt im Endpunkt (siehe calendar_feed.py).
api_router.include_router(calendar_feed_router, tags=["calendar-feed"])
# Kein Bearer-Auth moeglich (Microsoft leitet den Browser nach dem OAuth-
# Consent direkt hierher zurueck, ohne Authorization-Header) - eigener,
# state-Parameter-basierter Schutz direkt im Endpunkt (siehe
# mail_accounts.py::mail_oauth_callback und integrations/microsoft_graph/
# oauth_state.py). Live-Vorfall: lag zunaechst faelschlich in
# protected_router und lieferte 401 statt den OAuth-Flow abzuschliessen.
api_router.include_router(mail_accounts_public_router, tags=["mail-accounts-oauth-callback"])

protected_router = APIRouter(dependencies=[Depends(get_current_user)])
protected_router.include_router(calendar_events_router, tags=["calendar-events"])
protected_router.include_router(candidates_router, tags=["candidates"])
protected_router.include_router(clients_router, tags=["clients"])
protected_router.include_router(contacts_router, tags=["contacts"])
protected_router.include_router(jobs_router, tags=["vacancies"])
protected_router.include_router(kpi_router, tags=["kpi"])
protected_router.include_router(approvals_router, tags=["approvals"])
protected_router.include_router(matching_router, tags=["candidate-matching"])
protected_router.include_router(profile_generator_router, tags=["profile-generator"])
protected_router.include_router(nl_search_router, tags=["nl-search"])
protected_router.include_router(geo_router, tags=["geo-mapping"])
protected_router.include_router(imports_router, tags=["imports"])
protected_router.include_router(sourcing_router, tags=["sourcing"])
protected_router.include_router(submissions_router, tags=["candidate-submissions"])
protected_router.include_router(activities_router, tags=["activities"])
protected_router.include_router(tasks_router, tags=["tasks"])
protected_router.include_router(mail_accounts_router, tags=["mail-accounts"])
protected_router.include_router(mail_send_router, tags=["mail-send"])
protected_router.include_router(notes_router, tags=["notes"])
protected_router.include_router(operational_router, tags=["operations"])
protected_router.include_router(recruiting_router, tags=["recruiting-process"])
protected_router.include_router(region_modifiers_router, tags=["region-modifiers"])
protected_router.include_router(sequences_router, tags=["outreach-sequences"])
protected_router.include_router(mailing_groups_router, tags=["mailing-groups"])
protected_router.include_router(users_router, tags=["users"])
protected_router.include_router(audit_logs_router, tags=["audit-logs"])
protected_router.include_router(deletion_requests_router, tags=["deletion-requests"])
api_router.include_router(protected_router)
