"""Builds the ElevenLabs agent definition (prompt, first message, data collection)."""
import os

PROMPT = """You are the Hoitovirta phone line for cancer care in Finland. You are an AI assistant, not a nurse or a doctor. Say so in your first sentence.

WHO CALLS
1. A patient or a relative who has a symptom or a worry, or is waiting.
2. A member of staff (admin, nurse, coordinator, surgeon, oncologist) who needs the next step for a situation.

SAFETY (always first)
- If the caller describes chest pain, trouble breathing, heavy bleeding, sudden weakness, confusion or thoughts of self-harm: tell them to call 112 now. Stay on the line if they ask. Do not continue the intake.
- Never diagnose, never say it is or is not cancer, never advise on treatment or medicines. Say a nurse or doctor decides that.
- If asked about something you do not know, say so. Never guess a date, a result or a name.

STYLE
- Plain, warm, short sentences. One question at a time. Use the caller's language (Finnish, Swedish, English, or Arabic). If they switch, switch.
- Name feelings once, without drama. Fear, delay and hesitation are normal. Do not pressure. Do not use jargon.
- Fix common myths gently and briefly, then ask a question. Example myths: "it is probably nothing so I should wait", "I do not want to be a bother", "a test means it is serious", "I will be told if something is wrong". Say: waiting does not make it safer; checking is what the service is for; a test is how we find out, not a verdict.

PATIENT CALL, in this order
1. Say you are an AI, that the call is recorded to help the care team, and ask if they are happy to go on.
2. Ask what has been going on, in their words. Listen.
3. Ask when they first noticed it (this is the start date). Accept "about three weeks ago" and turn it into a date.
4. Ask how many times they have already been in touch with care about it.
5. Ask how worried they are, 0 to 10.
6. Ask if they know what happens next and who to call.
7. If they have a pathway code from their SMS or letter, ask for it and their birth year, then call patient_status to tell them their next step, date, place and nurse.
8. Read back a two-sentence summary. Ask "Is that right?". Fix it if not.
9. Explain what happens: a nurse reviews this and calls within one working day. If they mentioned a warning sign, say a clinician will look at it today. If worry is 4 or more, say a nurse will call.
10. Ask if they want a callback in another language or an interpreter.

PULSE MODE
- Read the runtime values pathway_id={{pathway_id}} and moment={{moment}}. If both are non-empty, call pulse_questions with the moment and caller language before asking survey questions.
- Ask only the returned two items, one at a time, in the returned order. Read each answer back and ask if it is right; accept a correction before moving on.
- Set pulse_answer_1 and pulse_answer_2 only to the confirmed option keys from pulse_questions. Do not collect the normal intake fields in Pulse mode.
- If one returned item is PU7 and its confirmed answer is 4 or more, explain that a nurse will call and leave the decision to the care team.

JOURNEY GUIDE
- When asked what to expect, call journey_guide for the caller's pathway and language. Read only the returned example text, including its review label when relevant.
- Do not add diagnosis, treatment, timing, or outcome advice. If the guide does not answer, say you do not know and refer to the coordinator.

STAFF CALL
1. Ask for staff ID and code. Call verify_staff. Do not say anything about patients before it returns verified.
2. If not verified after two tries, give the switchboard number and end the call. Never reveal which part was wrong.
3. When verified, greet by name and role. Only give what the tool says they may hear.
4. For "what do I do when...": call sop_lookup, read out the step, the owner and the deadline, and say it is the procedure, not a clinical decision. If sop_lookup finds nothing, say so and name the coordinator or medical lead.
5. For a patient's status, call patient_status with the session token and the pathway code. Never read out more than the tool returns.

Never ask for or repeat personal identity numbers, addresses or card numbers. Keep the call under five minutes."""

PROMPT += "\nWhen the caller says goodbye, or all questions are done, say a short goodbye and end the call with the End conversation tool."

FIRST_MESSAGE = ("Hello, this is the Hoitovirta phone line. I am an AI assistant, not a nurse or doctor. "
                 "This call is recorded to help the care team. Are you happy to continue?")

LANGUAGE_PRESETS = {
    "fi": {"overrides": {"agent": {"first_message": "Hei, tässä on Hoitovirran puhelinlinja. Olen tekoälyavustaja, en hoitaja tai lääkäri. Tämä puhelu tallennetaan hoitotiimin avuksi. Haluatko jatkaa?"}}},
    "sv": {"overrides": {"agent": {"first_message": "Hej, du har kommit till Hoitovirta. Jag är en AI-assistent, inte en sjuksköterska eller läkare. Samtalet spelas in för att hjälpa vårdteamet. Vill du fortsätta?"}}},
    "ar": {"overrides": {"agent": {"first_message": "مرحبًا، هذه خدمة هاتف Hoitovirta. أنا مساعد ذكاء اصطناعي، ولست ممرضًا أو طبيبًا. تُسجَّل هذه المكالمة لمساعدة فريق الرعاية. هل ترغب في المتابعة؟"}}},
    "hi": {"overrides": {"agent": {"first_message": "नमस्ते, यह होइटोविर्ता फोन लाइन है। मैं एक AI सहायक हूँ, नर्स या डॉक्टर नहीं। देखभाल टीम की सहायता के लिए यह कॉल रिकॉर्ड की जा रही है। क्या आप जारी रखने के लिए तैयार हैं?"}}},
    "no": {"overrides": {"agent": {"first_message": "Hei, dette er Hoitovirta-telefonlinjen. Jeg er en KI-assistent, ikke sykepleier eller lege. Denne samtalen tas opp for å hjelpe behandlingsteamet. Ønsker du å fortsette?"}}},
}

DEFAULT_VOICE_ID = "cjVigY5qzO86Huf0OWal"  # Eric, as reported by the sanitized live snapshot.
DEFAULT_TTS_MODEL = "eleven_v4_turbo"
DEFAULT_LLM = "nemotron-35-super-vl-nvfp4"

WIDGET = {
    "variant": "full", "placement": "bottom-right", "expandable": "never",
    "avatar": {"type": "orb", "color_1": "#2792dc", "color_2": "#9ce6e6"},
    "feedback_mode": "none", "end_feedback": {"type": "rating"},
    "bg_color": "#ffffff", "text_color": "#000000", "btn_color": "#000000",
    "btn_text_color": "#ffffff", "border_color": "#e1e1e1", "focus_color": "#000000",
    "show_avatar_when_collapsed": False, "disable_banner": False,
    "mic_muting_enabled": True, "transcript_enabled": True, "text_input_enabled": True,
    "conversation_mode_toggle_enabled": False, "default_expanded": False,
    "always_expanded": False, "dismissible": False, "show_agent_status": False,
    "show_conversation_id": True, "strip_audio_tags": True,
    "show_resize_button": True, "end_confirmation_enabled": False,
    "mobile_fullscreen": True, "transcript_speech_sync_enabled": True,
    "language_selector": False, "supports_text_only": True,
}

OVERRIDES = {
    "conversation_config_override": {
        "asr": {"keywords": False},
        "turn": {"soft_timeout_config": {"message": False, "additional_soft_timeout_messages": False},
                 "noisy_environment_message": False},
        "tts": {"model_id": False, "voice_id": False, "supported_voices": False,
                "stability": False, "speed": False, "similarity_boost": False,
                "clone_strength": False, "pronunciation_dictionary_locators": False},
        "conversation": {"text_only": True, "max_duration_seconds": False},
        "agent": {"first_message": False, "language": True,
                   "max_conversation_duration_message": False, "silence_end_call_message": False,
                   "prompt": {"prompt": False, "llm": False, "reasoning_effort": False,
                              "tool_ids": False, "tool_ids_strict": False,
                              "native_mcp_server_ids": False, "knowledge_base": False}},
    },
    "custom_llm_extra_body": False,
    "enable_conversation_initiation_client_data_from_webhook": False,
    "enable_starting_workflow_node_id_from_client": False,
    "enable_procedure_ids_from_client": False,
}

DATA_COLLECTION = {
    "caller_type": {"type": "string", "description": "One of: patient, relative, staff, unknown."},
    "language": {"type": "string", "description": "Language the caller used, ISO code (fi, sv, en, ar, hi, no, so, ru)."},
    "symptom_summary": {"type": "string", "description": "One neutral sentence in the caller's own words. No diagnosis."},
    "symptom_onset_date": {"type": "string", "description": "When the caller first noticed the symptom, as YYYY-MM-DD. Empty if unknown."},
    "contacts_so_far": {"type": "integer", "description": "How many times the caller has already contacted care about this."},
    "red_flags_mentioned": {"type": "string", "description": "Any warning signs the caller named (for example blood in stool, lump, weight loss, cough over 3 weeks). Empty if none."},
    "worry_0_10": {"type": "integer", "description": "The caller's worry, 0 to 10."},
    "knows_next_step": {"type": "boolean", "description": "True if the caller said they know what happens next and who to call."},
    "wants_callback": {"type": "boolean", "description": "True if the caller asked for a call back or an interpreter."},
    "pathway_code": {"type": "string", "description": "Pathway code like PW-D1 if the caller gave one."},
    "caller_confirmed_summary": {"type": "boolean", "description": "True if the caller agreed with the read-back summary."},
    "call_summary": {"type": "string", "description": "Two sentences: why they called and what was agreed. No names."},
    "pathway_id": {"type": "string", "description": "Dynamic pathway id for Pulse mode (PW-D1 etc). Empty for intake."},
    "moment": {"type": "string", "description": "Dynamic Pulse moment key (handover, diagnosis, treatment, suspicion, first_contact). Empty for intake."},
    "pulse_answer_1": {"type": "string", "description": "Confirmed option key for the first item returned by pulse_questions, or empty."},
    "pulse_answer_2": {"type": "string", "description": "Confirmed option key for the second item returned by pulse_questions, or empty."},
}


def tools(base_url, tool_secret):
    h = {"x-tool-secret": tool_secret}

    def hook(name, desc, props, required, path):
        return {"type": "webhook", "name": name, "description": desc,
                "api_schema": {"url": f"{base_url}{path}", "method": "POST", "request_headers": h,
                               "request_body_schema": {"type": "object", "properties": props, "required": required}}}
    s = lambda d: {"type": "string", "description": d}
    return [
        hook("pulse_questions", "Return the existing two Pulse questions and answer options for this moment. Ask only these questions.",
             {"moment": s("Pulse moment key"), "language": s("Language code fi, sv, en, ar, hi, no, ru")}, ["moment", "language"], "/tool/pulse_questions"),
        hook("journey_guide", "Read the sourced example guidance for this patient's current journey stage. Do not add advice.",
             {"pathway_id": s("Synthetic pathway id"), "language": s("Language code fi, sv, en, ar, so, ru")}, ["pathway_id", "language"], "/tool/journey_guide"),
        hook("verify_staff", "Check a staff member's ID and code. Call before sharing anything.",
             {"staff_id": s("Staff ID, for example L-1042"), "pin": s("The four-digit code")}, ["staff_id", "pin"], "/tool/verify_staff"),
        hook("patient_status", "Get the next step, date, place and nurse for a pathway. Staff pass session_token; patients pass birth_year.",
             {"pathway_code": s("Pathway id like PW-D1 (demo pathways are PW-D1 to PW-D5 and PW-0001 style)"), "session_token": s("From verify_staff (staff only)"),
              "birth_year": s("Four-digit birth year (patients only)")}, ["pathway_code"], "/tool/patient_status"),
        hook("sop_lookup", "Find the procedure for a situation. Returns the step, owner and deadline.",
             {"situation": s("Plain description of the situation")}, ["situation"], "/tool/sop_lookup"),
    ]


def build(base_url, tool_secret, language="en", voice_id=None, llm=DEFAULT_LLM):
    prompt = {"prompt": PROMPT, "llm": llm, "tools": tools(base_url, tool_secret),
              "built_in_tools": {"end_call": {"type": "system", "name": "end_call",
                  "description": "", "params": {"system_tool_type": "end_call"}}}}
    cfg = {
        "name": "Hoitovirta phone line",
        "tags": ["hoitovirta", "junction2026", "synthetic"],
        "conversation_config": {
            "agent": {"first_message": FIRST_MESSAGE, "language": language, "prompt": prompt},
            "tts": {"model_id": DEFAULT_TTS_MODEL, "voice_id": voice_id or DEFAULT_VOICE_ID},
            "language_presets": LANGUAGE_PRESETS,
            "turn": {"turn_timeout": 7, "silence_end_call_timeout": 20},
            "conversation": {"max_duration_seconds": 300},
        },
        "platform_settings": {"data_collection": DATA_COLLECTION, "widget": WIDGET, "overrides": OVERRIDES},
    }
    return cfg
