from fastapi import APIRouter, Depends

from cc_crm.api.dependencies import get_current_user
from cc_crm.api.v1.activities import router as activities_router
from cc_crm.api.v1.auth import router as auth_router
from cc_crm.api.v1.candidates import router as candidates_router
from cc_crm.api.v1.clients import router as clients_router
from cc_crm.api.v1.contacts import router as contacts_router
from cc_crm.api.v1.geo import router as geo_router
from cc_crm.api.v1.imports import router as imports_router
from cc_crm.api.v1.jobs import router as jobs_router
from cc_crm.api.v1.mailing_groups import router as mailing_groups_router
from cc_crm.api.v1.matching import router as matching_router
from cc_crm.api.v1.nl_search import router as nl_search_router
from cc_crm.api.v1.notes import router as notes_router
from cc_crm.api.v1.operational import router as operational_router
from cc_crm.api.v1.profile_generator import router as profile_generator_router
from cc_crm.api.v1.recruiting import router as recruiting_router
from cc_crm.api.v1.region_modifiers import router as region_modifiers_router
from cc_crm.api.v1.submissions import router as submissions_router
from cc_crm.api.v1.system import router as system_router
from cc_crm.api.v1.tasks import router as tasks_router

api_router = APIRouter()
api_router.include_router(system_router, tags=["system"])
api_router.include_router(auth_router, tags=["auth"])

protected_router = APIRouter(dependencies=[Depends(get_current_user)])
protected_router.include_router(candidates_router, tags=["candidates"])
protected_router.include_router(clients_router, tags=["clients"])
protected_router.include_router(contacts_router, tags=["contacts"])
protected_router.include_router(jobs_router, tags=["vacancies"])
protected_router.include_router(matching_router, tags=["candidate-matching"])
protected_router.include_router(profile_generator_router, tags=["profile-generator"])
protected_router.include_router(nl_search_router, tags=["nl-search"])
protected_router.include_router(geo_router, tags=["geo-mapping"])
protected_router.include_router(imports_router, tags=["imports"])
protected_router.include_router(submissions_router, tags=["candidate-submissions"])
protected_router.include_router(activities_router, tags=["activities"])
protected_router.include_router(tasks_router, tags=["tasks"])
protected_router.include_router(notes_router, tags=["notes"])
protected_router.include_router(operational_router, tags=["operations"])
protected_router.include_router(recruiting_router, tags=["recruiting-process"])
protected_router.include_router(region_modifiers_router, tags=["region-modifiers"])
protected_router.include_router(mailing_groups_router, tags=["mailing-groups"])
api_router.include_router(protected_router)
