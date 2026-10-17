from cc_crm.models.access_views import UserViewAccess, UserViewSettings  # NOMICON
from cc_crm.models.activity import Activity
from cc_crm.models.ai_proposal import AiProposal
from cc_crm.models.api_key import ApiKey
from cc_crm.models.app_setting import AppSetting
from cc_crm.models.approval_request import ApprovalRequest
from cc_crm.models.auth import AuthSession
from cc_crm.models.background_job import BackgroundJob
from cc_crm.models.base import Base
from cc_crm.models.calendar_event import CalendarEvent
from cc_crm.models.candidate import Candidate
from cc_crm.models.candidate_pitch_log import CandidatePitchLog
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.commission import CommissionUserRank  # NOMICON
from cc_crm.models.contact_person import ContactPerson
from cc_crm.models.custom_field import CustomFieldDefinition
from cc_crm.models.cv_extraction_job import CvExtractionJob
from cc_crm.models.deletion_request import DeletionRequest
from cc_crm.models.email_template import EmailTemplate
from cc_crm.models.engagement import CandidateEngagementPrefs  # NOMICON
from cc_crm.models.event_outbox import EventOutbox
from cc_crm.models.job_mandate import JobMandate
from cc_crm.models.kpi_point_rule import KpiPointRule
from cc_crm.models.login_challenge import LoginChallenge
from cc_crm.models.mail import MailAccount, MailMessage
from cc_crm.models.mailing_group import MailingGroup
from cc_crm.models.note import Note
from cc_crm.models.oauth import OAuthAuthorization, OAuthClient, OAuthToken
from cc_crm.models.operational import Document, EmailDraftLog, SourcingMetric
from cc_crm.models.outreach import OutreachSequence, OutreachSequenceStep, SequenceEnrollment
from cc_crm.models.postal_locality import PostalLocality
from cc_crm.models.presentation_record import PresentationRecord, PresentationRemovalRequest
from cc_crm.models.rate_limit_attempt import RateLimitAttempt
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
from cc_crm.models.staffing import (  # NOMICON
    StaffingAssignment,
    StaffingAssignmentExtension,
    StaffingChecklistItem,
    StaffingContract,
    StaffingInvoice,
    StaffingInvoiceLine,
    StaffingLicense,
    StaffingPriorPeriod,
    StaffingTimesheet,
    StaffingTimesheetEntry,
    StaffingWorker,
)
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.submission_share import SubmissionShare
from cc_crm.models.task import Task
from cc_crm.models.trusted_device import TrustedDevice
from cc_crm.models.user import User
from cc_crm.models.webhook import WebhookDelivery, WebhookEndpoint

__all__ = [
    "CandidateEngagementPrefs",  # NOMICON
    "UserViewAccess",  # NOMICON
    "UserViewSettings",  # NOMICON
    "Activity",
    "AiProposal",
    "ApiKey",
    "AppSetting",
    "ApprovalRequest",
    "AuditLog",
    "AuthSession",
    "BackgroundJob",
    "Base",
    "CalendarEvent",
    "Candidate",
    "CandidatePitchLog",
    "CandidateSubmission",
    "ClientCompany",
    "CommissionUserRank",  # NOMICON
    "ContactPerson",
    "CustomFieldDefinition",
    "CvExtractionJob",
    "DeletionRequest",
    "Document",
    "EmailDraftLog",
    "EmailTemplate",
    "EventOutbox",
    "Fee",
    "Interview",
    "JobMandate",
    "KpiPointRule",
    "LoginChallenge",
    "MailAccount",
    "MailMessage",
    "MailingGroup",
    "PresentationRecord",
    "PresentationRemovalRequest",
    "Note",
    "OAuthAuthorization",
    "OAuthClient",
    "OAuthToken",
    "OutreachSequence",
    "OutreachSequenceStep",
    "Offer",
    "Placement",
    "PostalLocality",
    "RateLimitAttempt",
    "RegionModifier",
    "SubmissionFeedback",
    "SequenceEnrollment",
    "SourcingLead",
    "SourcingMetric",
    "SourcingRun",
    "StaffingAssignment",  # NOMICON
    "StaffingAssignmentExtension",  # NOMICON
    "StaffingChecklistItem",
    "StaffingContract",
    "StaffingInvoice",
    "StaffingInvoiceLine",
    "StaffingLicense",
    "StaffingPriorPeriod",  # NOMICON
    "StaffingTimesheet",
    "StaffingTimesheetEntry",
    "StaffingWorker",
    "SubmissionShare",
    "Task",
    "TrustedDevice",
    "User",
    "WebhookDelivery",
    "WebhookEndpoint",
]
