"""Static knowledge base: treatment pricing and FAQ entries.

This is demo content representing typical medical-spa pricing and common
caller questions. A real clinic would replace ``TREATMENT_PRICING`` and
``TREATMENT_FAQ`` with their own data (or front the lookups with a CMS, a
spreadsheet, or a RAG pipeline over the clinic's docs).

The shape of this module is the contract the agent depends on:

- :func:`lookup_price` returns a :class:`PriceQuote` or ``None``.
- :func:`search_faq` returns an :class:`FAQEntry` or ``None``.

Tests pin those signatures so swapping in a real backend later is just a
matter of providing the same return shapes.
"""

from __future__ import annotations

from typing import NamedTuple


class PriceQuote(NamedTuple):
    """A pricing range for a single treatment."""

    treatment: str  # Display name, e.g. "Botox"
    price_range: str  # "$12–$18", "$650–$900", etc.
    unit: str  # "per unit", "per session", "per syringe", "per area"
    notes: str  # Short clarifier for the caller


class FAQEntry(NamedTuple):
    """A canonical FAQ answer keyed by topic."""

    topic: str
    answer: str


# ---- Pricing ---------------------------------------------------------------
#
# Ranges are demo-representative; real clinics vary widely by region and
# provider tier. Keys are normalized lowercase identifiers; aliases route to
# canonical keys via PRICING_ALIASES below.

TREATMENT_PRICING: dict[str, PriceQuote] = {
    "botox": PriceQuote(
        treatment="Botox",
        price_range="$12 to $18",
        unit="per unit",
        notes="Most patients use 20 to 60 units per visit depending on the areas treated.",
    ),
    "filler": PriceQuote(
        treatment="dermal filler",
        price_range="$650 to $900",
        unit="per syringe",
        notes="Lip filler typically uses one syringe; cheek or jawline work often uses two.",
    ),
    "laser_hair_removal": PriceQuote(
        treatment="laser hair removal",
        price_range="$150 to $450",
        unit="per session",
        notes="A full course is usually 6 to 8 sessions for permanent results.",
    ),
    "hydrafacial": PriceQuote(
        treatment="HydraFacial",
        price_range="$175 to $300",
        unit="per session",
        notes="Most patients see best results with a monthly cadence.",
    ),
    "chemical_peel": PriceQuote(
        treatment="chemical peel",
        price_range="$150 to $400",
        unit="per session",
        notes="Light peels are entry-level; medium-depth peels are at the higher end.",
    ),
    "microneedling": PriceQuote(
        treatment="microneedling",
        price_range="$300 to $600",
        unit="per session",
        notes="Often sold as a series of three for $800 to $1500.",
    ),
    "coolsculpting": PriceQuote(
        treatment="CoolSculpting",
        price_range="$700 to $1500",
        unit="per area",
        notes="Most patients treat 2 to 4 areas; multi-area packages bring per-area cost down.",
    ),
}

# Common caller phrasings → canonical pricing key. Lookups normalize the
# query and check this map before falling back to substring matching.
PRICING_ALIASES: dict[str, str] = {
    "botox": "botox",
    "tox": "botox",
    "filler": "filler",
    "lip filler": "filler",
    "cheek filler": "filler",
    "juvederm": "filler",
    "restylane": "filler",
    "laser": "laser_hair_removal",
    "laser hair": "laser_hair_removal",
    "laser hair removal": "laser_hair_removal",
    "hair removal": "laser_hair_removal",
    "hydrafacial": "hydrafacial",
    "hydra facial": "hydrafacial",
    "facial": "hydrafacial",
    "peel": "chemical_peel",
    "chemical peel": "chemical_peel",
    "microneedling": "microneedling",
    "micro needling": "microneedling",
    "rf microneedling": "microneedling",
    "coolsculpting": "coolsculpting",
    "cool sculpting": "coolsculpting",
    "fat freezing": "coolsculpting",
    "body contouring": "coolsculpting",
}


# ---- FAQ -------------------------------------------------------------------
#
# Keys are topic slugs. Each entry's ``answer`` is written to be spoken aloud
# — short, plain language, no markdown. The lookup uses keyword matching on
# the caller's question rather than exact key match.

TREATMENT_FAQ: dict[str, FAQEntry] = {
    "botox_what_is_it": FAQEntry(
        topic="What is Botox?",
        answer=(
            "Botox is a purified protein injected in small amounts to relax "
            "specific facial muscles, which softens the appearance of lines "
            "around the forehead, eyes, and between the brows. Results show "
            "in about 3 to 7 days and typically last 3 to 4 months."
        ),
    ),
    "botox_downtime": FAQEntry(
        topic="Botox downtime",
        answer=(
            "There's essentially no downtime for Botox. Most patients return "
            "to normal activities right away. We do ask that you avoid lying "
            "flat or rubbing the area for about 4 hours after."
        ),
    ),
    "filler_what_is_it": FAQEntry(
        topic="What is dermal filler?",
        answer=(
            "Dermal fillers are gel-based injections — most often hyaluronic "
            "acid — used to restore volume in lips, cheeks, and other areas, "
            "or to smooth deeper lines. Results are typically visible right "
            "after the appointment and last from 6 months to a couple of "
            "years depending on the product and area."
        ),
    ),
    "filler_pain": FAQEntry(
        topic="Does filler hurt?",
        answer=(
            "Most patients describe filler as a quick pinch followed by mild "
            "pressure. We use a topical numbing cream, and most fillers also "
            "contain a small amount of local anesthetic, so discomfort is "
            "minimal."
        ),
    ),
    "laser_pain": FAQEntry(
        topic="Does laser hair removal hurt?",
        answer=(
            "Most patients describe laser hair removal as a quick snap, like "
            "a rubber band. Our devices have built-in cooling to make the "
            "treatment more comfortable. Most sessions for legs or underarms "
            "take 15 to 30 minutes."
        ),
    ),
    "laser_sessions": FAQEntry(
        topic="How many laser sessions are needed?",
        answer=(
            "Most patients need 6 to 8 sessions spaced 4 to 6 weeks apart "
            "for long-lasting results. Hair grows in cycles, so the laser "
            "needs to catch each follicle in its active growth phase."
        ),
    ),
    "consultation_free": FAQEntry(
        topic="Are consultations free?",
        answer=(
            "Yes — initial consultations are complimentary. You'll meet with "
            "a provider who'll review your goals, recommend a treatment plan, "
            "and give you a specific quote."
        ),
    ),
    "hours": FAQEntry(
        topic="Business hours",
        answer=(
            "We're open Monday through Friday, 9 in the morning to 6 in the "
            "evening. You're talking to our after-hours assistant — I'll make "
            "sure someone calls you back during business hours."
        ),
    ),
    "insurance": FAQEntry(
        topic="Does insurance cover treatments?",
        answer=(
            "Aesthetic treatments are typically not covered by insurance. We "
            "do accept HSA and FSA cards for most treatments, and we offer "
            "package pricing on multi-session treatments."
        ),
    ),
}


# Keyword → FAQ key. Used by search_faq for cheap, deterministic matching.
# Order matters: more specific terms first.
FAQ_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    # Botox
    (("botox", "downtime"), "botox_downtime"),
    (("botox", "recovery"), "botox_downtime"),
    (("botox", "what"), "botox_what_is_it"),
    (("botox", "how does"), "botox_what_is_it"),
    (("tox", "what"), "botox_what_is_it"),
    # Filler
    (("filler", "hurt"), "filler_pain"),
    (("filler", "pain"), "filler_pain"),
    (("filler", "what"), "filler_what_is_it"),
    (("filler", "how"), "filler_what_is_it"),
    (("juvederm",), "filler_what_is_it"),
    (("restylane",), "filler_what_is_it"),
    # Laser
    (("laser", "hurt"), "laser_pain"),
    (("laser", "pain"), "laser_pain"),
    (("laser", "session"), "laser_sessions"),
    (("laser", "how many"), "laser_sessions"),
    (("laser", "treatments"), "laser_sessions"),
    # Consultation
    (("consultation", "free"), "consultation_free"),
    (("consult", "free"), "consultation_free"),
    (("consultation", "cost"), "consultation_free"),
    (("free", "consult"), "consultation_free"),
    # Hours
    (("hours",), "hours"),
    (("open",), "hours"),
    (("when", "open"), "hours"),
    # Insurance
    (("insurance",), "insurance"),
    (("hsa",), "insurance"),
    (("fsa",), "insurance"),
    (("cover",), "insurance"),
)


# ---- Lookups ---------------------------------------------------------------


def lookup_price(query: str) -> PriceQuote | None:
    """Find a :class:`PriceQuote` for a free-form treatment query.

    Two-pass match:

    1. Exact alias match after normalization (lowercase, single spaces).
    2. Substring match against alias keys (longest first to prefer specific
       matches like "lip filler" over "filler").

    Returns ``None`` if nothing matches. The agent treats ``None`` as
    "capture the question, follow up offline."
    """
    normalized = " ".join(query.lower().split())
    if not normalized:
        return None

    # Pass 1: exact alias.
    canonical = PRICING_ALIASES.get(normalized)
    if canonical is not None:
        return TREATMENT_PRICING.get(canonical)

    # Pass 2: substring, longest alias first.
    for alias in sorted(PRICING_ALIASES, key=len, reverse=True):
        if alias in normalized:
            return TREATMENT_PRICING.get(PRICING_ALIASES[alias])

    return None


def search_faq(question: str) -> FAQEntry | None:
    """Find an :class:`FAQEntry` matching the caller's question.

    Keyword AND matching: each rule lists the words that must ALL appear in
    the normalized question. Rules are checked in declared order; the first
    rule whose words are all present wins. This is intentionally simple —
    deterministic, fast, easy to test, and avoids LLM-driven hallucination
    on medical content.

    Returns ``None`` if no rule matches.
    """
    normalized = " ".join(question.lower().split())
    if not normalized:
        return None

    for keywords, faq_key in FAQ_KEYWORDS:
        if all(kw in normalized for kw in keywords):
            return TREATMENT_FAQ.get(faq_key)

    return None
