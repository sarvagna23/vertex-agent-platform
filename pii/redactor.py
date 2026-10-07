"""PII redaction. Runs on the user's question BEFORE it reaches any model.

Two layers:
  1. Regex for emails, SSNs, card numbers, phone numbers and a few name patterns (always on, no cost).
  2. Cloud DLP for names and other infoTypes (opt in with USE_DLP=true).

CFPB narratives are already masked at the source (XXXX), so the main exposure is what a
user types into the question box.
"""
import re
from dataclasses import dataclass, field

import config

# Order matters: SSN and card numbers must run before the looser phone pattern.
REGEX_RULES = [
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("PHONE", re.compile(r"(?<!\w)(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(?!\w)")),
]

# Names are the hard part for regex. These patterns are deliberately narrow to avoid
# masking company names ("this is Citibank"). Cloud DLP covers the wider case.
NAME_RULES = [
    # "my name is Jane Doe", "name is Jane", "call me Jane Smith"
    re.compile(r"(?i:\b(?:my name is|name is|call me))\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})"),
    # "Mr. Smith", "Dr Jane Doe"
    re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Dr)\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)"),
    # sign-offs: "Sincerely, Jane Doe"
    re.compile(r"(?i:\b(?:sincerely|regards|thanks),)\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})"),
]

DLP_INFO_TYPES = [
    "PERSON_NAME", "EMAIL_ADDRESS", "PHONE_NUMBER",
    "US_SOCIAL_SECURITY_NUMBER", "CREDIT_CARD_NUMBER", "STREET_ADDRESS",
]


@dataclass
class RedactionResult:
    text: str
    counts: dict = field(default_factory=dict)  # e.g. {"EMAIL": 1, "NAME": 2}

    @property
    def found_pii(self) -> bool:
        return bool(self.counts)


def _redact_with_regex(text: str) -> RedactionResult:
    """Apply the regex rules in order and count what was masked."""
    counts: dict[str, int] = {}

    for label, pattern in REGEX_RULES:
        text, hits = pattern.subn(f"[{label}]", text)
        if hits:
            counts[label] = counts.get(label, 0) + hits

    for pattern in NAME_RULES:
        # Replace only the captured name, keep the lead-in words ("my name is [NAME]").
        def mask_name(match: re.Match) -> str:
            full = match.group(0)
            name = match.group(1)
            return full.replace(name, "[NAME]")

        text, hits = pattern.subn(mask_name, text)
        if hits:
            counts["NAME"] = counts.get("NAME", 0) + hits

    return RedactionResult(text=text, counts=counts)


def _redact_with_dlp(text: str) -> str:
    """Ask Cloud DLP to replace sensitive spans with their infoType, e.g. [PERSON_NAME]."""
    from google.cloud import dlp_v2

    client = dlp_v2.DlpServiceClient()
    request = {
        "parent": f"projects/{config.PROJECT_ID}/locations/global",
        "inspect_config": {"info_types": [{"name": name} for name in DLP_INFO_TYPES]},
        "deidentify_config": {
            "info_type_transformations": {
                "transformations": [{"primitive_transformation": {"replace_with_info_type_config": {}}}]
            }
        },
        "item": {"value": text},
    }
    return client.deidentify_content(request=request).item.value


def redact_pii(text: str) -> RedactionResult:
    """Mask PII in text. Regex always runs, DLP runs on top when USE_DLP=true."""
    result = _redact_with_regex(text)

    if config.USE_DLP:
        try:
            dlp_text = _redact_with_dlp(result.text)
            if dlp_text != result.text:
                result.counts["DLP"] = result.counts.get("DLP", 0) + 1
                result.text = dlp_text
        except Exception as error:  # never block a request because DLP is down, regex already ran
            print(f"[pii] DLP unavailable, regex only: {error}")

    return result
