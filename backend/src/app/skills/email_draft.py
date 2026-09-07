"""email_draft skill — compose a MIME email message (does not send)."""

from __future__ import annotations

import base64
import json
import os
from email.message import EmailMessage
from email.policy import EmailPolicy

from app.skills.base import SkillExecutor
from app.skills.schemas import EmailDraftRequest, EmailDraftResponse


class EmailDraftSkill(SkillExecutor[EmailDraftRequest, EmailDraftResponse]):
    slug = "email_draft"

    async def execute(self, input_data: EmailDraftRequest) -> EmailDraftResponse:
        msg = EmailMessage()

        msg["To"] = input_data.to
        msg["Subject"] = input_data.subject
        if input_data.cc:
            msg["Cc"] = ", ".join(input_data.cc)
        if input_data.bcc:
            msg["Bcc"] = ", ".join(input_data.bcc)

        msg.set_content(input_data.body)

        # Serialize to RFC 2822 string
        raw = msg.as_bytes()
        # Try UTF-8, fall back to encoded-word style
        try:
            raw_str = raw.decode("utf-8")
        except UnicodeDecodeError:
            raw_str = base64.b64encode(raw).decode("ascii")

        return EmailDraftResponse(
            to=input_data.to,
            cc=list(input_data.cc),
            bcc=list(input_data.bcc),
            subject=input_data.subject,
            body=input_data.body,
            raw_mime=raw_str,
        )


def get_executor() -> EmailDraftSkill:
    return EmailDraftSkill()
