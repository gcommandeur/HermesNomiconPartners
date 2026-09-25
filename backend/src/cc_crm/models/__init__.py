from cc_crm.models.activity import Activity
from cc_crm.models.api_key import ApiKey
from cc_crm.models.auth import AuthSession
from cc_crm.models.base import Base
from cc_crm.models.calendar_event import CalendarEvent
from cc_crm.models.candidate import Candidate
from cc_crm.models.candidate_pitch_log import CandidatePitchLog
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.contact_person import ContactPerson
from cc_crm.models.cv_extraction_job import CvExtractionJob
from cc_crm.models.deletion_request import DeletionRequest
from cc_crm.models.email_template import EmailTemplate
from cc_crm.models.job_mandate import JobMandate
from cc_crm.models.login_challenge import LoginChallenge
from cc_crm.models.mail import MailAccount, MailMessage
from cc_crm.models.mailing_group import MailingGroup
from cc_crm.models.note import Note
from cc_crm.models.operational import Document, EmailDraftLog, SourcingMetric
from cc_crm.models.postal_locality import PostalLocality
from cc_crm.models.recruiting import (
    AuditLog,
    Fee,
    Interview,
    Offer,
    Placement,
    SubmissionFeedback,
)
from cc_crm.models.region_modifier import RegionModifier
from cc_crm.models.sourcing_lead import SourcingLead
from cc_crm.models.sourcing_run import SourcingRun
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.task import Task
from cc_crm.models.trusted_device import TrustedDevice
from cc_crm.models.user import User

__all__ = [
    "Activity",
    "ApiKey",
    "AuditLog",
    "AuthSession",
    "Base",
    "CalendarEvent",
    "Candidate",
    "CandidatePitchLog",
    "CandidateSubmission",
    "ClientCompany",
    "ContactPerson",
    "CvExtractionJob",
    "DeletionRequest",
    "Document",
    "EmailDraftLog",
    "EmailTemplate",
    "Fee",
    "Interview",
    "JobMandate",
    "LoginChallenge",
    "MailAccount",
    "MailMessage",
    "MailingGroup",
    "Note",
    "Offer",
    "Placement",
    "PostalLocality",
    "RegionModifier",
    "SubmissionFeedback",
    "SourcingLead",
    "SourcingMetric",
    "SourcingRun",
    "Task",
    "TrustedDevice",
    "User",
]
