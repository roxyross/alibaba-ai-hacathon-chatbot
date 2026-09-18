"""EmailService — AI smart drafting, tone polishing, templates, and dispatch.

Provides intelligence and delivery coordination for the Phase 12 Email Engine.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import structlog

from app.emails.repository import EmailRepository
from app.skills.email_send import EmailSendSkill
from app.skills.schemas import EmailSendRequest

log = structlog.get_logger()

# Curated high-value templates library
_EMAIL_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "meeting_followup",
        "title": "Meeting Follow-Up & Action Items",
        "category": "work",
        "subject": "Follow-up: {Topic} — Action Items & Next Steps",
        "body": (
            "Hi {Name},\n\n"
            "Thank you for your time during our discussion today regarding {Topic}. "
            "It was great aligning on our key goals.\n\n"
            "Key Takeaways & Next Steps:\n"
            "• [Key Decision 1]\n"
            "• [Action Item for Owner by Target Date]\n"
            "• [Upcoming Milestone or Review Date]\n\n"
            "Please let me know if there are any points I missed or anything you would like to adjust. "
            "Looking forward to our continued progress!\n\n"
            "Best regards,\n"
            "{Sender}"
        ),
    },
    {
        "id": "status_update",
        "title": "Weekly Sprint & Milestone Update",
        "category": "work",
        "subject": "Sprint Progress & Milestone Update — {Project}",
        "body": (
            "Hi Team,\n\n"
            "Here is the latest status update for {Project}:\n\n"
            "✅ Completed Highlights:\n"
            "• [Milestone/Feature delivered]\n"
            "• [Resolved blocker or completed test suite]\n\n"
            "🔄 In Progress:\n"
            "• [Current workstream]\n\n"
            "⚠️ Blockers / Needs Attention:\n"
            "• [None or specific assistance required]\n\n"
            "Feel free to reach out if you have any questions or feedback.\n\n"
            "Thanks,\n"
            "{Sender}"
        ),
    },
    {
        "id": "invoice_notice",
        "title": "Invoice & Payment Notification",
        "category": "finance",
        "subject": "Invoice Notice: {Service} — Invoice #{Number}",
        "body": (
            "Dear {Name},\n\n"
            "I hope this note finds you well.\n\n"
            "Please find attached the invoice for {Service} covering our recent deliverables. "
            "The total amount due is {Amount}, with payment due by {DueDate}.\n\n"
            "Payment instructions and bank details are noted directly on the invoice. "
            "Please confirm receipt of this email.\n\n"
            "Thank you for your continued partnership,\n"
            "{Sender}"
        ),
    },
    {
        "id": "introduction",
        "title": "Professional Introduction & Collaboration",
        "category": "networking",
        "subject": "Introduction: {YourCompany} & {TheirCompany} — Exploring Collaboration",
        "body": (
            "Hello {Name},\n\n"
            "I have been following your work at {TheirCompany} with great admiration, "
            "particularly regarding {FocusArea}.\n\n"
            "At {YourCompany}, we are building intelligent automation tools and I believe "
            "there is strong synergy between our teams. Would you be open to a brief 15-minute "
            "introductory conversation next week?\n\n"
            "Looking forward to connecting,\n"
            "{Sender}"
        ),
    },
    {
        "id": "out_of_office",
        "title": "Out of Office / Vacation Notice",
        "category": "personal",
        "subject": "Out of Office: {Sender} through {ReturnDate}",
        "body": (
            "Hello,\n\n"
            "Thank you for getting in touch. I am currently out of the office starting "
            "{StartDate} and will return on {ReturnDate} with limited access to email.\n\n"
            "For urgent inquiries regarding ongoing operations, please contact {ContactPerson} at {ContactEmail}.\n\n"
            "I will reply to your message as soon as possible upon my return.\n\n"
            "Warm regards,\n"
            "{Sender}"
        ),
    },
    {
        "id": "reschedule_request",
        "title": "Meeting Reschedule Request",
        "category": "coordination",
        "subject": "Reschedule Request: {MeetingTitle}",
        "body": (
            "Hi {Name},\n\n"
            "I apologize for the short notice, but due to an unexpected conflict, "
            "I will need to reschedule our upcoming meeting ({MeetingTitle}) originally planned for {OriginalTime}.\n\n"
            "Would any of the following alternative times work on your end?\n"
            "• [Option 1: Day & Time]\n"
            "• [Option 2: Day & Time]\n\n"
            "Thank you very much for your understanding, and I apologize for any inconvenience.\n\n"
            "Best,\n"
            "{Sender}"
        ),
    },
]


class EmailService:
    """Core domain service for AI drafting, tone rephrasing, templates, and dispatch."""

    def __init__(self, repository: EmailRepository | None = None) -> None:
        self._repo = repository or EmailRepository()
        self._send_skill = EmailSendSkill()

    def get_templates(self) -> list[dict[str, Any]]:
        """Return the curated library of email templates."""
        return _EMAIL_TEMPLATES

    def compose_with_ai(
        self,
        prompt: str,
        tone: str = "professional",
        recipient_name: str | None = None,
    ) -> dict[str, str]:
        """Generate structured email subject and body from a natural language prompt.

        Supports tones: professional, casual, executive, persuasive, friendly, apologetic.
        """
        cleaned_prompt = prompt.strip()
        recipient = recipient_name or "Colleague"

        # Determine subject from prompt
        subject = self._extract_subject_from_prompt(cleaned_prompt)

        # Build tone-adjusted body
        body = self._build_body_for_tone(cleaned_prompt, tone, recipient)

        return {
            "subject": subject,
            "body": body,
            "tone": tone,
        }

    def polish_email(
        self,
        subject: str,
        body: str,
        tone: str = "professional",
    ) -> dict[str, str]:
        """Polish and elevate existing draft copy for enhanced clarity and tone."""
        clean_subj = subject.strip()
        clean_body = body.strip()

        # Refine subject
        polished_subject = clean_subj
        if not clean_subj.startswith(("[", "Re:", "Fwd:")) and tone == "executive":
            polished_subject = f"[Action Required] {clean_subj}" if "action" in clean_subj.lower() else clean_subj

        # Refine body according to tone
        lines = [line.strip() for line in clean_body.split("\n") if line.strip()]
        if not lines:
            polished_body = f"I am writing to follow up on {clean_subj.lower()}."
        else:
            polished_body = self._format_polished_body(lines, tone)

        return {
            "subject": polished_subject,
            "body": polished_body,
            "tone": tone,
        }

    async def send_email_message(
        self,
        user_id: str,
        message_id: str,
        smtp_user: str | None = None,
        smtp_pass: str | None = None,
        smtp_host: str | None = None,
        smtp_port: int | None = None,
        smtp_from: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch a persisted draft message and record execution outcome."""
        msg = await self._repo.get_message(user_id, message_id)
        if not msg:
            raise ValueError(f"Email message with ID '{message_id}' not found for user.")

        to_addr = msg.get("to") or ""
        subject = msg.get("subject") or ""
        body = msg.get("body") or ""
        cc = msg.get("cc") or []
        bcc = msg.get("bcc") or []

        # Invoke delivery skill
        req = EmailSendRequest(
            to=to_addr,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            confirm=True,
            user_id=user_id,
            smtp_user=smtp_user,
            smtp_pass=smtp_pass,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_from=smtp_from,
        )

        res = await self._send_skill.execute(req)

        now = datetime.now(UTC)
        if res.success:
            updated = await self._repo.update_message(
                user_id=user_id,
                message_id=message_id,
                status="sent",
                delivery_error=None,
                message_id_str=res.message_id,
                sent_at=now,
            )
            return {
                "success": True,
                "delivery_status": "sent",
                "message_id": res.message_id,
                "sent_at": now.isoformat(),
                "record": updated,
            }
        else:
            updated = await self._repo.update_message(
                user_id=user_id,
                message_id=message_id,
                status="failed",
                delivery_error=res.error,
            )
            return {
                "success": False,
                "delivery_status": "failed",
                "error": res.error,
                "record": updated,
            }

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------

    def _extract_subject_from_prompt(self, prompt: str) -> str:
        # Check if user specified subject directly, e.g. "subject: ..."
        match = re.search(r"subject\s*[:=]\s*([^\n\r]+)", prompt, re.I)
        if match:
            return match.group(1).strip()

        # Heuristic title extraction
        first_line = prompt.split("\n")[0].strip()
        first_line = re.sub(
            r"^(draft|write|compose|send)\s+(an?\s+)?(email|mail|message)\s+(to|about|regarding)?\s*",
            "",
            first_line,
            flags=re.I,
        ).strip()
        if first_line:
            clean = first_line[:60].capitalize()
            return clean if clean.endswith((".", "!", "?")) else clean
        return "Important Discussion & Follow-Up"

    def _build_body_for_tone(self, prompt: str, tone: str, recipient: str) -> str:
        tone_lower = tone.lower()

        if tone_lower == "casual":
            greeting = f"Hey {recipient},"
            sign_off = "Cheers,\nRoxy AI Team"
            opening = "Hope you're having a great week! Just wanted to reach out regarding:"
        elif tone_lower == "executive":
            greeting = f"{recipient} —"
            sign_off = "Regards,\nExecutive Office"
            opening = "BLUF (Bottom Line Up Front): Please review the following key summary and decisions:"
        elif tone_lower == "persuasive":
            greeting = f"Dear {recipient},"
            sign_off = "Looking forward to partnering with you,\nWarmest regards"
            opening = "I wanted to share an exciting opportunity and perspective that directly aligns with our goals:"
        elif tone_lower == "friendly":
            greeting = f"Hi {recipient}!"
            sign_off = "Warmly,\nYour Team"
            opening = "Hope all is going well on your end! Dropping a quick note about:"
        elif tone_lower == "apologetic":
            greeting = f"Dear {recipient},"
            sign_off = "Sincerely and with gratitude,\nSupport Team"
            opening = "Please accept our sincere apologies for the inconvenience. We wanted to provide full transparency on:"
        else:  # professional default
            greeting = f"Dear {recipient},"
            sign_off = "Kind regards,\nProfessional Services"
            opening = "I am writing to touch base with you regarding:"

        points = [p.strip("-*• \t") for p in prompt.split("\n") if p.strip("-*• \t")]
        if not points:
            points = ["Review the attached project details and next steps."]

        formatted_points = "\n".join(f"• {p}" for p in points)

        return (
            f"{greeting}\n\n"
            f"{opening}\n\n"
            f"{formatted_points}\n\n"
            f"Please let me know if you have any questions or when you would be free to connect.\n\n"
            f"{sign_off}"
        )

    def _format_polished_body(self, lines: list[str], tone: str) -> str:
        body_content = "\n".join(lines)
        templates = {
            "executive": (
                "Executive Summary:\n"
                f"{body_content}\n\n"
                "Next Steps:\n"
                "• Awaiting confirmation and approvals to proceed.\n\n"
                "Regards,\nExecutive Lead"
            ),
            "casual": (
                "Hey there,\n\n"
                f"{body_content}\n\n"
                "Let me know what you think when you get a chance!\n\n"
                "Cheers"
            ),
            "persuasive": (
                "Hello,\n\n"
                f"{body_content}\n\n"
                "I am confident this approach will deliver measurable impact. Let's schedule a call to finalize.\n\n"
                "Best regards"
            ),
        }
        return templates.get(
            tone,
            (
                "Hello,\n\n"
                f"{body_content}\n\n"
                "Please let me know if you require any additional information.\n\n"
                "Kind regards"
            ),
        )

