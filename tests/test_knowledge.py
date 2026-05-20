"""Tests for the static pricing + FAQ knowledge base.

Pin both the lookup behaviors (so the agent's tool wrappers can trust them)
and the data shape (so swapping in a real backend later is a known refactor).
"""

from __future__ import annotations

import pytest

from aurelia.knowledge import (
    FAQ_KEYWORDS,
    PRICING_ALIASES,
    TREATMENT_FAQ,
    TREATMENT_PRICING,
    FAQEntry,
    PriceQuote,
    lookup_price,
    search_faq,
)


class TestLookupPrice:
    @pytest.mark.parametrize(
        ("query", "expected_treatment"),
        [
            ("botox", "Botox"),
            ("Botox", "Botox"),
            ("  BOTOX  ", "Botox"),
            ("tox", "Botox"),
            ("lip filler", "dermal filler"),
            ("Juvederm please", "dermal filler"),
            ("how much is laser hair removal", "laser hair removal"),
            ("HydraFacial", "HydraFacial"),
            ("a hydra facial", "HydraFacial"),
            ("chemical peel", "chemical peel"),
            ("cool sculpting", "CoolSculpting"),
            ("body contouring quote", "CoolSculpting"),
        ],
    )
    def test_known_treatments_return_quote(self, query: str, expected_treatment: str) -> None:
        quote = lookup_price(query)
        assert quote is not None
        assert quote.treatment == expected_treatment

    @pytest.mark.parametrize("query", ["", "   ", "tummy tuck", "rhinoplasty", "asdf"])
    def test_unknown_treatments_return_none(self, query: str) -> None:
        assert lookup_price(query) is None

    def test_substring_prefers_specific_alias(self) -> None:
        # "lip filler" should resolve as filler even though "filler" alone also
        # matches — the longest-alias-first pass guarantees specificity wins.
        quote = lookup_price("can I get a lip filler price")
        assert quote is not None
        assert quote.treatment == "dermal filler"

    def test_returned_quote_has_required_fields(self) -> None:
        quote = lookup_price("botox")
        assert quote is not None
        assert quote.price_range
        assert quote.unit
        assert quote.notes


class TestSearchFAQ:
    @pytest.mark.parametrize(
        ("question", "expected_topic_keyword"),
        [
            ("what is Botox?", "What is Botox"),
            ("how does botox work", "What is Botox"),
            ("is there downtime for botox?", "Botox downtime"),
            ("does filler hurt", "Does filler hurt"),
            ("what is filler made of", "What is dermal filler"),
            ("does laser hurt", "Does laser hair removal hurt"),
            ("how many laser sessions do I need", "How many laser sessions"),
            ("are consultations free?", "Are consultations free"),
            ("when are you open", "Business hours"),
            ("what are your hours", "Business hours"),
            ("do you take insurance", "Does insurance cover"),
            ("can I use my HSA", "Does insurance cover"),
        ],
    )
    def test_keyword_match(self, question: str, expected_topic_keyword: str) -> None:
        entry = search_faq(question)
        assert entry is not None
        assert expected_topic_keyword.lower() in entry.topic.lower()

    @pytest.mark.parametrize(
        "question",
        [
            "",
            "tell me about quantum physics",
            "do you have any cats",
            "where's the bathroom",
        ],
    )
    def test_no_match_returns_none(self, question: str) -> None:
        assert search_faq(question) is None

    def test_returned_entry_has_speakable_answer(self) -> None:
        entry = search_faq("what is botox?")
        assert entry is not None
        # Should NOT contain markdown or list characters that would be read aloud weirdly.
        forbidden = ["**", "##", "- ", " * ", "`"]
        for ch in forbidden:
            assert ch not in entry.answer, f"FAQ answer contains {ch!r} — not voice-safe"


class TestDataShape:
    def test_every_pricing_alias_resolves(self) -> None:
        # If an alias points to a key that doesn't exist in TREATMENT_PRICING,
        # the agent will return a confusing None at runtime. Catch it here.
        for alias, canonical in PRICING_ALIASES.items():
            assert canonical in TREATMENT_PRICING, (
                f"PRICING_ALIASES[{alias!r}] = {canonical!r} but no such key in TREATMENT_PRICING"
            )

    def test_every_faq_keyword_rule_resolves(self) -> None:
        for keywords, faq_key in FAQ_KEYWORDS:
            assert faq_key in TREATMENT_FAQ, (
                f"FAQ_KEYWORDS rule for {keywords!r} points at {faq_key!r} which has no entry"
            )

    def test_quotes_and_entries_are_named_tuples(self) -> None:
        # Pin the public types so a future refactor can't silently break callers.
        for quote in TREATMENT_PRICING.values():
            assert isinstance(quote, PriceQuote)
        for entry in TREATMENT_FAQ.values():
            assert isinstance(entry, FAQEntry)
