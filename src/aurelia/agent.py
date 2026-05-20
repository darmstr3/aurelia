"""LiveKit Agents entrypoint and call flow.

Wires the OpenAI LLM/TTS, Deepgram STT, and Silero VAD into an
``AgentSession``, exposes a single ``submit_intake`` function tool that the
LLM calls when it has all the required fields, and ties it back to Sheets +
escalation.

Run via :mod:`aurelia.cli` (which delegates to ``livekit.agents.cli``):

.. code-block:: bash

    uv run aurelia dev          # connect to LiveKit and serve calls
    uv run aurelia connect      # join a specific room
"""

from __future__ import annotations

from typing import Annotated

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    RoomInputOptions,
    RunContext,
    WorkerOptions,
    function_tool,
)
from livekit.plugins import deepgram, openai, silero

# NOTE: turn detector is intentionally disabled in production. The
# multilingual model alone adds ~200MB at runtime and OOMs Render's 512MB
# starter plan. Re-enable when on a 2GB+ instance:
#     from livekit.plugins.turn_detector.multilingual import MultilingualModel
#     ...AgentSession(..., turn_detection=MultilingualModel())
from pydantic import Field, ValidationError

from aurelia.config import Settings, get_settings
from aurelia.escalation import EmergencyPager
from aurelia.intake import CallerIntake, PatientStatus, ReasonForCall, Urgency
from aurelia.knowledge import lookup_price, search_faq
from aurelia.logging import configure as configure_logging
from aurelia.logging import get_logger
from aurelia.prompts import greeting, system_prompt
from aurelia.sheets import SheetsAppendError, SheetsClient

_log = get_logger(__name__)


class IntakeAgent(Agent):  # type: ignore[misc]  # livekit Agent isn't typed
    """Voice agent that captures one med-spa intake per call.

    The agent owns its persona (via the system prompt) and the
    side-effecting submit_intake tool. Sheets and pager dependencies are
    injected so tests can swap them out without touching LiveKit.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        sheets: SheetsClient,
        pager: EmergencyPager,
    ) -> None:
        super().__init__(
            instructions=system_prompt(
                company_name=settings.aurelia_company_name,
                business_hours=settings.aurelia_business_hours,
                agent_name=settings.aurelia_agent_name,
            )
        )
        self._settings = settings
        self._sheets = sheets
        self._pager = pager
        self._submitted = False

    @function_tool()
    async def submit_intake(
        self,
        ctx: RunContext,
        caller_name: Annotated[str, Field(description="Caller's full name.")],
        callback_number: Annotated[
            str,
            Field(description="Best phone number to reach the caller, with area code."),
        ],
        patient_status: Annotated[
            str,
            Field(description="One of: new, existing."),
        ],
        reason_for_call: Annotated[
            str,
            Field(
                description=(
                    "One of: post_procedure_concern, new_consult, scheduling, pricing, other."
                )
            ),
        ],
        treatment_of_interest: Annotated[
            str,
            Field(
                description=(
                    "Treatment the caller asked about or recently received "
                    "(e.g. 'Botox', 'lip filler last Tuesday', 'laser hair removal')."
                )
            ),
        ],
        urgency: Annotated[
            str,
            Field(description="One of: emergency, urgent, routine."),
        ],
        callback_window: Annotated[
            str,
            Field(description="When the caller wants to be reached, e.g. 'after 9am tomorrow'."),
        ],
        notes: Annotated[
            str,
            Field(default="", description="Any extra context the caller volunteered."),
        ] = "",
    ) -> str:
        """Validate, persist to Sheets, and (if emergency) page the on-call provider.

        Returns a short status string for the LLM to relay verbally.
        """
        # Note: in livekit-agents 1.5, RunContext does not expose .room directly.
        # The intake's own call_id is the durable identifier we log against.
        log = _log

        if self._submitted:
            log.warning("submit_intake.duplicate_call")
            return "The intake has already been submitted for this call."

        try:
            intake = CallerIntake(
                caller_name=caller_name,
                callback_number=callback_number,
                patient_status=PatientStatus.from_loose(patient_status),
                reason_for_call=ReasonForCall.from_loose(reason_for_call),
                treatment_of_interest=treatment_of_interest,
                urgency=Urgency.from_loose(urgency),
                callback_window=callback_window,
                notes=notes,
            )
        except (ValidationError, ValueError) as exc:
            log.warning("submit_intake.validation_failed", error=str(exc))
            return (
                "I couldn't save that — one of the fields didn't validate "
                f"({exc}). Could you confirm the callback number for me?"
            )

        log = log.bind(intake_call_id=intake.call_id, urgency=intake.urgency.value)
        log.info("submit_intake.received")

        try:
            self._sheets.append_intake(intake)
        except SheetsAppendError as exc:
            log.error("submit_intake.sheets_failed", error=str(exc))
            return (
                "I'm having trouble saving the record on my end. "
                "Please call back during business hours and we'll get you scheduled."
            )

        self._submitted = True

        paged = False
        if intake.is_emergency:
            paged = self._pager.page(intake)
            log.info("submit_intake.emergency_handled", paged=paged)

        if intake.is_emergency and paged:
            return (
                "Got it — I've recorded your information and I'm paging the "
                "on-call provider right now. They'll call you back at "
                f"{intake.callback_number} as soon as they can."
            )
        if intake.is_emergency:
            return (
                "I've recorded your information. I had trouble reaching the "
                "on-call line, but our team will see this first thing. If "
                "anything feels worse — trouble breathing, severe pain, "
                "vision changes — please call 911 right away."
            )
        return (
            f"All set, {intake.caller_name}. We'll call you back at "
            f"{intake.callback_number} {intake.callback_window}."
        )

    @function_tool()
    async def lookup_treatment_price(
        self,
        ctx: RunContext,
        treatment: Annotated[
            str,
            Field(
                description=(
                    "The treatment the caller asked the price of, in their own "
                    "words (e.g. 'Botox', 'lip filler', 'laser hair removal', "
                    "'HydraFacial')."
                )
            ),
        ],
    ) -> str:
        """Return a voice-friendly pricing range for a treatment.

        Returns either a quotable line the agent can read aloud, or a "no
        match" string telling the agent to log the inquiry as an intake
        instead of guessing.
        """
        log = _log.bind(query=treatment)
        quote = lookup_price(treatment)
        if quote is None:
            log.info("lookup_price.no_match")
            return (
                "We don't have a published price for that — capture the "
                "caller's information through submit_intake and our team will "
                "follow up with a quote during business hours. Do not guess "
                "or estimate the price."
            )
        log.info("lookup_price.matched", treatment=quote.treatment)
        # Phrasing guidance for the model — tell it what to say, not the raw fields.
        return (
            f"{quote.treatment} runs {quote.price_range} {quote.unit}. "
            f"{quote.notes} Tell the caller this is general pricing — exact "
            "quotes come from the consultation. Then ask if they'd like to "
            "book a consult so you can submit their intake."
        )

    @function_tool()
    async def answer_treatment_faq(
        self,
        ctx: RunContext,
        question: Annotated[
            str,
            Field(
                description=(
                    "The caller's question in their own words "
                    "(e.g. 'what is Botox?', 'does filler hurt?', "
                    "'are consultations free?')."
                )
            ),
        ],
    ) -> str:
        """Look up a canonical FAQ answer.

        Returns either the canned answer (which the agent should speak
        verbatim or near-verbatim) or a "no match" string telling the agent
        to capture the question as an intake. The agent must not invent an
        answer.
        """
        log = _log.bind(question=question)
        entry = search_faq(question)
        if entry is None:
            log.info("answer_faq.no_match")
            return (
                "We don't have a canned answer for that — tell the caller "
                "you'll have someone with more details follow up during "
                "business hours, then collect their intake via submit_intake. "
                "Do not make up an answer."
            )
        log.info("answer_faq.matched", topic=entry.topic)
        return entry.answer


def _build_session(settings: Settings) -> AgentSession:
    """Compose STT / LLM / TTS / VAD using values from settings.

    Turn detection is currently VAD-only (see note at the top of this file).
    """
    return AgentSession(
        stt=deepgram.STT(model=settings.deepgram_stt_model),
        llm=openai.LLM(model=settings.openai_llm_model),
        tts=openai.TTS(
            model=settings.openai_tts_model,
            voice=settings.openai_tts_voice,
        ),
        vad=silero.VAD.load(),
    )


async def entrypoint(ctx: JobContext) -> None:
    """LiveKit job entrypoint. One invocation per inbound call."""
    settings = get_settings()
    configure_logging(env=settings.aurelia_env, level=settings.aurelia_log_level)

    log = _log.bind(room=ctx.room.name if ctx.room else "unknown")
    log.info("call.start")

    session = _build_session(settings)
    sheets = SheetsClient(settings=settings)
    pager = EmergencyPager(settings=settings)
    agent = IntakeAgent(settings=settings, sheets=sheets, pager=pager)

    await ctx.connect()
    await session.start(
        agent=agent,
        room=ctx.room,
        room_input_options=RoomInputOptions(),
    )
    await session.generate_reply(
        instructions=greeting(
            company_name=settings.aurelia_company_name,
            agent_name=settings.aurelia_agent_name,
        )
    )

    log.info("call.session_started")


def worker_options() -> WorkerOptions:
    """Build the WorkerOptions the CLI hands to ``cli.run_app``."""
    return WorkerOptions(entrypoint_fnc=entrypoint)
