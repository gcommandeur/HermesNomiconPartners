import uuid

from fastapi import APIRouter, Response

from cc_crm.api.dependencies import DatabaseSession
from cc_crm.schemas.profile import AnonymousProfileResponse
from cc_crm.services.candidates import CandidateService
from cc_crm.services.profile_docx_export import build_export_filename, generate_profile_docx
from cc_crm.services.profile_generator import ProfileGeneratorService

router = APIRouter(prefix="/candidates")


@router.post("/{candidate_id}/anonymous-profile", response_model=AnonymousProfileResponse)
def generate_anonymous_profile(
    candidate_id: uuid.UUID,
    session: DatabaseSession,
) -> AnonymousProfileResponse:
    profile_text = ProfileGeneratorService(session).generate_anonymous_profile(candidate_id)
    return AnonymousProfileResponse(profile_text=profile_text)


@router.get("/{candidate_id}/anonymous-profile.docx")
def download_anonymous_profile_docx(candidate_id: uuid.UUID, session: DatabaseSession) -> Response:
    candidate = CandidateService(session).get(candidate_id)
    docx_bytes = generate_profile_docx(candidate)
    filename = build_export_filename(candidate)
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
