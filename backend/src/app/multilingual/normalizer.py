"""Universal Semantic Intent Normalizer for ROXY 2.0.

Translates multilingual natural language requests into language-independent,
strongly typed UniversalSemanticIntent representations.
"""

from __future__ import annotations

import re
from typing import Any

from app.multilingual.detector import MultilingualDetector
from app.multilingual.schemas import IntentCategory, SupportedLanguage, UniversalSemanticIntent


class UniversalIntentNormalizer:
    """Extracts canonical targets, actions, and entities across supported languages."""

    _COMMON_APPS_CANONICAL = {
        "calculator": "Calculator",
        "calc": "Calculator",
        "کیلکولیٹر": "Calculator",
        "कैलकुलेटर": "Calculator",
        "الآلة الحاسبة": "Calculator",
        "calculatrice": "Calculator",
        "rechner": "Calculator",
        "calculadora": "Calculator",

        "chrome": "Google Chrome",
        "google chrome": "Google Chrome",
        "کروم": "Google Chrome",
        "क्रोम": "Google Chrome",

        "spotify": "Spotify",
        "سپوٹیفائی": "Spotify",
        "स्पॉटिफ़ाई": "Spotify",

        "whatsapp": "WhatsApp",
        "واٹس ایپ": "WhatsApp",
        "व्हाट्सएप": "WhatsApp",

        "slack": "Slack",
        "سلاک": "Slack",
        "स्लैक": "Slack",

        "notepad": "Notepad",
        "نوٹ پیڈ": "Notepad",
        "नोटपैड": "Notepad",

        "vscode": "Visual Studio Code",
        "vs code": "Visual Studio Code",

        "terminal": "Terminal",
        "powershell": "powershell",
        "cmd": "cmd",
        "vlc": "VLC",
        "youtube": "YouTube",
    }

    # Multilingual Open / Launch verbs
    _OPEN_VERBS = {
        # English
        "open", "launch", "start", "run",
        # Roman Urdu / Hindi
        "kholo", "khol", "chalao", "shuru karo", "start karo",
        # Urdu Nastaliq
        "کھولو", "کھول", "شروع کرو", "اوپن کرو", "چلاؤ",
        # Hindi Devanagari
        "खोलो", "खोलिए", "शुरू करो", "चलाओ",
        # Arabic
        "افتح", "شغل",
        # Spanish
        "abrir", "abre", "iniciar",
        # French
        "ouvrir", "ouvre", "lancer",
        # German
        "öffnen", "oeffnen", "starten",
    }

    # Multilingual Close / Exit verbs
    _CLOSE_VERBS = {
        "close", "quit", "exit", "terminate", "kill", "stop",
        "band karo", "band", "roko",
        "بند کرو", "روکو", "ختم کرو",
        "बंद करो", "रोको",
        "اغلق", "أغلق", "انهاء",
        "cerrar", "fermer", "schließen",
    }

    # Multilingual Calculation patterns
    _CALC_WORDS = {
        "calculate", "compute", "math", "evaluate",
        "hisab", "hisab karo", "kitna hota hai",
        "حساب کرو", "گنتی کرو", "کتنا ہوتا ہے",
        "हिसाब करो", "गणना करो", "कितना होता है",
        "احسب", "calcular", "calculer", "berechnen",
    }

    # Multilingual File / Folder patterns
    _FILE_FOLDER_WORDS = {
        "folder", "directory", "project", "files", "file", "codebase",
        "فولڈر", "ڈائریکٹری", "پروجیکٹ", "فائلیں", "فائل",
        "फ़ोल्डर", "डायरेक्टरी", "प्रोजेक्ट", "फ़ाइल",
        "مجلد", "ملف", "ملفات",
        "carpeta", "archivo", "dossier", "fichier", "ordner", "datei",
    }

    # Multilingual Read / Inspect verbs
    _READ_INSPECT_VERBS = {
        "read", "inspect", "analyze", "scan", "check", "summarize",
        "parho", "dekho", "analyze karo", "check karo", "samjhao",
        "پڑھو", "دیکھو", "تجزیہ کرو", "خلاصہ کرو",
        "पढ़ो", "देखो", "विश्लेषण करो",
        "اقرأ", "تفحص", "حلل",
        "leer", "analizar", "lire", "analyser", "lesen",
    }

    # Multilingual Coding verbs
    _CODING_WORDS = {
        "code", "coding", "script", "program", "api", "component",
        "banao", "create karo", "develop karo", "write karo",
        "بناؤ", "تیار کرو", "لکھو",
        "बनाओ", "लिखो", "तैयार करो",
        "برمج", "اكتب كود", "انشئ",
        "codificar", "programmer", "programmieren",
    }

    @classmethod
    def _matches_any_keyword(cls, text: str, keywords: set[str] | list[str]) -> bool:
        lower = text.lower()
        for kw in keywords:
            if re.match(r"^[a-zA-Z0-9_\s]+$", kw):
                if re.search(rf"\b{re.escape(kw.lower())}\b", lower):
                    return True
            else:
                if kw in text:
                    return True
        return False

    @classmethod
    def normalize(
        cls,
        text: str,
        input_mode: str = "text",
        user_id: str | None = None,
    ) -> UniversalSemanticIntent:
        """Parse natural language query into a strongly typed language-independent intent."""
        raw = text.strip()
        lower = raw.lower()

        # 0. Cross-Surface Reference Resolution (e.g. 'iska bug fix karo', 'this file')
        resolved_context_val: str | None = None
        resolved_entity_type: str | None = None
        if user_id:
            try:
                from app.session.continuity import CrossSurfaceContinuityEngine
                engine = CrossSurfaceContinuityEngine.get_instance()
                ref = engine.resolve_reference(user_id=user_id, utterance=raw)
                if ref.target_value:
                    resolved_context_val = ref.target_value
                    resolved_entity_type = ref.target_entity_type
            except Exception:
                pass

        # 1. Detect natural language and script
        det = MultilingualDetector.detect(raw)
        lang = det.language
        script = det.script

        # If user refers to anaphoric entity (e.g., 'Ab iska bug fix karo' when folder is active)
        if resolved_context_val and resolved_entity_type in ("folder", "file"):
            if any(w in lower for w in ("bug", "fix", "issue", "error", "کوشش", "خرابی")):
                return UniversalSemanticIntent(
                    detected_language=lang,
                    script=script,
                    input_mode=input_mode,
                    intent_category=IntentCategory.CODING,
                    action="fix_bug",
                    parameters={
                        "target_path": resolved_context_val,
                        "entity_type": resolved_entity_type,
                        "task_prompt": raw,
                    },
                    confidence=0.96,
                    raw_input=raw,
                    normalized_query=f"fix_bug in {resolved_context_val}",
                    is_mixed_language=det.is_mixed,
                )

        # ---------------------------------------------------------------------
        # 2. Calculation Intent (e.g. 125 * 8 or 'calculate 25 + 5')
        # ---------------------------------------------------------------------
        norm_calc_text = raw.replace("×", "*").replace("÷", "/").replace("ضرب", "*").replace("تقسیم", "/").replace("جمع", "+").replace("منفی", "-").replace("गुना", "*").replace("भाग", "/")
        math_expr_match = re.search(r"(\d+(?:\.\d+)?\s*[\+\-\*\/\^]\s*\d+(?:\.\d+)?(?:\s*[\+\-\*\/\^]\s*\d+(?:\.\d+)?)*)", norm_calc_text)
        is_calc_intent = any(w in lower for w in cls._CALC_WORDS) or any(w in raw for w in cls._CALC_WORDS) or any(w in norm_calc_text for w in ("*", "/", "+", "-"))
        if math_expr_match and is_calc_intent:
            clean_expr = math_expr_match.group(1).strip()
            return UniversalSemanticIntent(
                detected_language=lang,
                script=script,
                input_mode=input_mode,
                intent_category=IntentCategory.CALCULATION,
                action="calculate",
                parameters={"expression": clean_expr},
                confidence=0.98,
                raw_input=raw,
                normalized_query=f"calculate {clean_expr}",
                is_mixed_language=det.is_mixed,
            )

        # ---------------------------------------------------------------------
        # 3. File & Folder Operations (e.g. 'read this project folder', 'ye folder read karo')
        # ---------------------------------------------------------------------
        has_file_kw = cls._matches_any_keyword(lower, cls._FILE_FOLDER_WORDS)
        has_read_kw = cls._matches_any_keyword(lower, cls._READ_INSPECT_VERBS)

        if has_file_kw and has_read_kw:
            target_type = "folder" if any(w in lower or w in raw for w in ("folder", "فولڈر", "फ़ोल्डर", "مجلد", "dossier", "ordner", "project", "پروجیکٹ")) else "file"
            action = "analyze_folder" if target_type == "folder" else "read_file"
            return UniversalSemanticIntent(
                detected_language=lang,
                script=script,
                input_mode=input_mode,
                intent_category=IntentCategory.FILE_OPERATION,
                action=action,
                parameters={"target_type": target_type, "depth": 3},
                confidence=0.95,
                raw_input=raw,
                normalized_query=f"{action} {target_type}",
                is_mixed_language=det.is_mixed,
            )

        # ---------------------------------------------------------------------
        # 4. Coding Agent Intent (e.g. 'Python mein FastAPI API bana do')
        # ---------------------------------------------------------------------
        has_code_kw = any(w in lower for w in cls._CODING_WORDS) or any(w in raw for w in cls._CODING_WORDS)
        found_matches: list[tuple[int, str]] = []
        for l in ("python", "javascript", "typescript", "golang", "go", "rust", "c++", "cpp", "c#", "java", "react", "fastapi", "django", "node", "html", "css", "sql", "c"):
            m = re.search(rf"\b{re.escape(l)}\b", lower)
            if m:
                found_matches.append((m.start(), l))
        found_code_lang = min(found_matches, key=lambda x: x[0])[1] if found_matches else None

        if has_code_kw and found_code_lang:
            return UniversalSemanticIntent(
                detected_language=lang,
                script=script,
                input_mode=input_mode,
                intent_category=IntentCategory.CODING,
                action="generate_code",
                parameters={"programming_language": found_code_lang, "task_prompt": raw},
                confidence=0.94,
                raw_input=raw,
                normalized_query=f"generate_code in {found_code_lang}",
                is_mixed_language=det.is_mixed,
            )

        # ---------------------------------------------------------------------
        # 4.5 Conversational Messaging & WhatsApp Intent
        # (e.g. 'Mere test contact ke liye message draft karo', 'Message bhejne se pehle mujhe dikhao',
        #       'Pehle recipient verify karo', 'Abhi message send mat karna', 'Message ka status check karo',
        #       'Use my configured business messaging API')
        # ---------------------------------------------------------------------
        has_msg_tokens = any(w in lower or w in raw for w in ("message", "msg", "میسج", "پیغام", "संदेश", "contact", "recipient", "messaging api", "whatsapp", "واٹس ایپ"))
        if has_msg_tokens:
            detected_route = "auto"
            if any(w in lower for w in ("desktop", "ڈیسک ٹاپ", "डेस्कटॉप")):
                detected_route = "desktop"
            elif any(w in lower for w in ("web", "ویب", "वेब", "browser")):
                detected_route = "web"
            elif any(w in lower for w in ("business messaging api", "business", "cloud api", "api", "کلاؤڈ", "بزنس")):
                detected_route = "cloud_api"

            is_status = any(w in lower or w in raw for w in ("status", "connected", "حالت", "کنکشن", "status check", "status check karo", "whether whatsapp is connected"))
            is_cancel_send = any(w in lower or w in raw for w in ("mat karna", "mat bhejo", "cancel", "cancel karo", "روکو", "نہ بھیجو", "منسوخ", "send mat"))
            is_verify_rcpt = any(w in lower or w in raw for w in ("verify", "recipient verify", "verify karo", "تصدیق کرو"))
            is_preview = any(w in lower or w in raw for w in ("show me", "dikhao", "دکھاؤ", "preview", "pehle dikhao", "pehle mujhe dikhao"))
            is_draft = any(w in lower or w in raw for w in ("draft", "ڈرافٹ", "draft karo"))
            is_route_choice = any(w in lower for w in ("use my configured", "use whatsapp web", "use whatsapp desktop", "through whatsapp desktop"))

            if is_status:
                return UniversalSemanticIntent(
                    detected_language=lang,
                    script=script,
                    input_mode=input_mode,
                    intent_category=IntentCategory.APP_CONTROL,
                    target_app="WhatsApp",
                    action="check_status",
                    parameters={"app_name": "WhatsApp", "route": detected_route},
                    confidence=0.96,
                    raw_input=raw,
                    normalized_query=f"check_status for WhatsApp ({detected_route})",
                    is_mixed_language=det.is_mixed,
                )
            elif is_cancel_send:
                return UniversalSemanticIntent(
                    detected_language=lang,
                    script=script,
                    input_mode=input_mode,
                    intent_category=IntentCategory.APP_CONTROL,
                    target_app="WhatsApp",
                    action="cancel_send",
                    parameters={"app_name": "WhatsApp", "route": detected_route},
                    confidence=0.96,
                    raw_input=raw,
                    normalized_query=f"cancel_send for WhatsApp",
                    is_mixed_language=det.is_mixed,
                )
            elif is_verify_rcpt:
                return UniversalSemanticIntent(
                    detected_language=lang,
                    script=script,
                    input_mode=input_mode,
                    intent_category=IntentCategory.APP_CONTROL,
                    target_app="WhatsApp",
                    action="verify_recipient",
                    parameters={"app_name": "WhatsApp", "route": detected_route},
                    confidence=0.96,
                    raw_input=raw,
                    normalized_query=f"verify_recipient for WhatsApp",
                    is_mixed_language=det.is_mixed,
                )
            elif is_preview:
                return UniversalSemanticIntent(
                    detected_language=lang,
                    script=script,
                    input_mode=input_mode,
                    intent_category=IntentCategory.APP_CONTROL,
                    target_app="WhatsApp",
                    action="preview_message",
                    parameters={"app_name": "WhatsApp", "route": detected_route, "prompt": raw},
                    confidence=0.96,
                    raw_input=raw,
                    normalized_query=f"preview_message for WhatsApp",
                    is_mixed_language=det.is_mixed,
                )
            elif is_draft:
                return UniversalSemanticIntent(
                    detected_language=lang,
                    script=script,
                    input_mode=input_mode,
                    intent_category=IntentCategory.APP_CONTROL,
                    target_app="WhatsApp",
                    action="draft_message",
                    parameters={"app_name": "WhatsApp", "route": detected_route, "prompt": raw},
                    confidence=0.96,
                    raw_input=raw,
                    normalized_query=f"draft_message via WhatsApp ({detected_route})",
                    is_mixed_language=det.is_mixed,
                )
            elif is_route_choice and not any(v in lower for v in ("send", "bhejo")):
                return UniversalSemanticIntent(
                    detected_language=lang,
                    script=script,
                    input_mode=input_mode,
                    intent_category=IntentCategory.APP_CONTROL,
                    target_app="WhatsApp",
                    action="select_route",
                    parameters={"app_name": "WhatsApp", "route": detected_route},
                    confidence=0.95,
                    raw_input=raw,
                    normalized_query=f"select_route {detected_route} for WhatsApp",
                    is_mixed_language=det.is_mixed,
                )

        # ---------------------------------------------------------------------
        # 5. App Launch / Open Control (e.g. 'calculator kholo', 'open chrome', 'کیلکولیٹر کھولو')
        # ---------------------------------------------------------------------
        # Check known canonical apps
        for app_alias, canonical_name in cls._COMMON_APPS_CANONICAL.items():
            if re.search(rf"\b{re.escape(app_alias)}\b", lower) or app_alias in raw:
                # Check for open/launch, close, or send message verbs
                is_open = any(v in lower or v in raw for v in cls._OPEN_VERBS)
                is_close = any(v in lower or v in raw for v in cls._CLOSE_VERBS)
                is_message = any(v in lower or v in raw for v in ("message", "msg", "bhejo", "send", "میسج", "پیغام", "संदेश"))

                # Check for specific WhatsApp / messaging actions
                if canonical_name == "WhatsApp":
                    # Route detection if explicitly mentioned
                    detected_route = "auto"
                    if any(w in lower for w in ("desktop", "ڈیسک ٹاپ", "डेस्कटॉप")):
                        detected_route = "desktop"
                    elif any(w in lower for w in ("web", "ویب", "वेब", "browser")):
                        detected_route = "web"
                    elif any(w in lower for w in ("api", "cloud", "business", "کلاؤڈ", "بزنس")):
                        detected_route = "cloud_api"

                    is_status = any(w in lower or w in raw for w in ("connected", "status", "کنیکٹڈ", "حالت", "کنکشن", "status check", "status check karo"))
                    is_preview = any(w in lower or w in raw for w in ("show me", "dikhao", "دکھاؤ", "preview", "pehle dikhao", "pehle mujhe dikhao"))
                    is_verify_rcpt = any(w in lower or w in raw for w in ("verify", "recipient verify", "verify karo", "تصدیق کرو"))
                    is_cancel_send = any(w in lower or w in raw for w in ("mat karna", "mat bhejo", "cancel", "cancel karo", "روکو", "نہ بھیجو", "منسوخ"))
                    is_draft = any(w in lower or w in raw for w in ("draft", "ڈرافٹ", "draft karo"))

                    if is_status:
                        return UniversalSemanticIntent(
                            detected_language=lang,
                            script=script,
                            input_mode=input_mode,
                            intent_category=IntentCategory.APP_CONTROL,
                            target_app="WhatsApp",
                            action="check_status",
                            parameters={"app_name": "WhatsApp", "route": detected_route},
                            confidence=0.96,
                            raw_input=raw,
                            normalized_query=f"check_status for WhatsApp ({detected_route})",
                            is_mixed_language=det.is_mixed,
                        )
                    elif is_cancel_send:
                        return UniversalSemanticIntent(
                            detected_language=lang,
                            script=script,
                            input_mode=input_mode,
                            intent_category=IntentCategory.APP_CONTROL,
                            target_app="WhatsApp",
                            action="cancel_send",
                            parameters={"app_name": "WhatsApp", "route": detected_route},
                            confidence=0.96,
                            raw_input=raw,
                            normalized_query=f"cancel_send for WhatsApp",
                            is_mixed_language=det.is_mixed,
                        )
                    elif is_verify_rcpt:
                        return UniversalSemanticIntent(
                            detected_language=lang,
                            script=script,
                            input_mode=input_mode,
                            intent_category=IntentCategory.APP_CONTROL,
                            target_app="WhatsApp",
                            action="verify_recipient",
                            parameters={"app_name": "WhatsApp", "route": detected_route},
                            confidence=0.96,
                            raw_input=raw,
                            normalized_query=f"verify_recipient for WhatsApp",
                            is_mixed_language=det.is_mixed,
                        )
                    elif is_preview:
                        return UniversalSemanticIntent(
                            detected_language=lang,
                            script=script,
                            input_mode=input_mode,
                            intent_category=IntentCategory.APP_CONTROL,
                            target_app="WhatsApp",
                            action="preview_message",
                            parameters={"app_name": "WhatsApp", "route": detected_route, "prompt": raw},
                            confidence=0.96,
                            raw_input=raw,
                            normalized_query=f"preview_message for WhatsApp",
                            is_mixed_language=det.is_mixed,
                        )
                    elif is_draft:
                        return UniversalSemanticIntent(
                            detected_language=lang,
                            script=script,
                            input_mode=input_mode,
                            intent_category=IntentCategory.APP_CONTROL,
                            target_app="WhatsApp",
                            action="draft_message",
                            parameters={"app_name": "WhatsApp", "route": detected_route, "prompt": raw},
                            confidence=0.96,
                            raw_input=raw,
                            normalized_query=f"draft_message via WhatsApp ({detected_route})",
                            is_mixed_language=det.is_mixed,
                        )

                if is_close:
                    return UniversalSemanticIntent(
                        detected_language=lang,
                        script=script,
                        input_mode=input_mode,
                        intent_category=IntentCategory.APP_CONTROL,
                        target_app=canonical_name,
                        action="close",
                        parameters={"app_name": canonical_name},
                        confidence=0.96,
                        raw_input=raw,
                        normalized_query=f"close {canonical_name}",
                        is_mixed_language=det.is_mixed,
                    )
                elif is_message:
                    # Detect route for send_message if mentioned
                    route_opt = "auto"
                    if canonical_name == "WhatsApp":
                        if "desktop" in lower:
                            route_opt = "desktop"
                        elif "web" in lower:
                            route_opt = "web"
                        elif any(w in lower for w in ("api", "cloud", "business")):
                            route_opt = "cloud_api"

                    return UniversalSemanticIntent(
                        detected_language=lang,
                        script=script,
                        input_mode=input_mode,
                        intent_category=IntentCategory.APP_CONTROL,
                        target_app=canonical_name,
                        action="send_message",
                        parameters={"app_name": canonical_name, "message": raw, "route": route_opt},
                        confidence=0.95,
                        raw_input=raw,
                        normalized_query=f"send_message via {canonical_name} ({route_opt})",
                        is_mixed_language=det.is_mixed,
                    )
                else:
                    # Default to open if app is mentioned with open verb or standalone
                    return UniversalSemanticIntent(
                        detected_language=lang,
                        script=script,
                        input_mode=input_mode,
                        intent_category=IntentCategory.APP_CONTROL,
                        target_app=canonical_name,
                        action="open",
                        parameters={"app_name": canonical_name},
                        confidence=0.95 if is_open else 0.85,
                        raw_input=raw,
                        normalized_query=f"open {canonical_name}",
                        is_mixed_language=det.is_mixed,
                    )

        # ---------------------------------------------------------------------
        # 6. Fallback General Question or Task
        # ---------------------------------------------------------------------
        return UniversalSemanticIntent(
            detected_language=lang,
            script=script,
            input_mode=input_mode,
            intent_category=IntentCategory.QUESTION,
            action="answer",
            parameters={"query": raw},
            confidence=0.75,
            raw_input=raw,
            normalized_query=raw,
            is_mixed_language=det.is_mixed,
        )
