"""LinkedIn integration boundary.

There is no general-purpose LinkedIn API for pulling recruiter contacts from
an ordinary account, and scraping linkedin.com violates its Terms of Service -
so this package intentionally contains no client. The supported path is a
legitimate CSV export (LinkedIn "Get a copy of your data", or a Sales
Navigator/Recruiter list export) converted via
scripts/convert_linkedin_export.py and then run through the existing,
validated CSV import at POST /api/v1/import/candidates/preview. See
docs/BULLHORN_LINKEDIN_IMPORT.md for the full walkthrough.
"""
