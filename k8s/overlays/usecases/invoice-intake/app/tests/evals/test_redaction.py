"""Redaction (G-AI-3): no bank account number in the seeded formats reaches a prompt, a trace or a log."""

from __future__ import annotations

import json

import pytest

from invoice_intake import logs
from invoice_intake.domain import MASK, bank_account_on, iban_valid, mask_bank_numbers, salted_bank_hash
from invoice_intake.generator import SUPPLIERS, known_bank_strings, verify_set
from invoice_intake.model import ModelReply, build_messages
from invoice_intake.pipeline import run_pass

IBAN = next(s.bank for s in SUPPLIERS if s.bank_is_iban)
SPACED = " ".join(IBAN[i:i + 4] for i in range(0, len(IBAN), 4))
ACCOUNT = next(s.bank for s in SUPPLIERS if not s.bank_is_iban)


@pytest.mark.redaction
def test_the_seeded_ibans_pass_mod_97() -> None:
    assert iban_valid(IBAN) and iban_valid(SPACED) and not iban_valid(IBAN[:-1] + ("0" if IBAN[-1] != "0" else "1"))


@pytest.mark.redaction
@pytest.mark.parametrize("text,number", [
    (f"IBAN: {SPACED}", SPACED), (f"IBAN {IBAN}", IBAN), (f"pay to {SPACED} BIC ABCDEF", SPACED),
    (f"Account number: {ACCOUNT}", ACCOUNT), (f"Account No. {ACCOUNT}", ACCOUNT), (f"bank account: {ACCOUNT}", ACCOUNT), (f"Konto {ACCOUNT}", ACCOUNT),
])
def test_masking_in_iban_and_non_iban_formats(text: str, number: str) -> None:
    masked = mask_bank_numbers(text)
    assert number not in masked and MASK in masked


@pytest.mark.redaction
def test_a_checksum_broken_by_ocr_is_masked_all_the_same_and_reads_as_unknown() -> None:
    broken = SPACED[:-1] + ("0" if SPACED[-1] != "0" else "1")
    assert broken not in mask_bank_numbers(f"IBAN: {broken}")
    assert bank_account_on(f"IBAN: {broken}") is None


@pytest.mark.redaction
def test_masking_leaves_the_invoice_fields_alone() -> None:
    text = "VAT ID: DE810000000\nInvoice number: INV-2026-1000\nDate: 2026-10-14\nPO number: PUR-50001\nTotal: 1,234.56 EUR"
    assert mask_bank_numbers(text) == text


@pytest.mark.redaction
def test_the_same_account_hashes_the_same_in_either_format() -> None:
    assert salted_bank_hash(bank_account_on(f"IBAN: {SPACED}") or "", "s") == salted_bank_hash(IBAN, "s")
    assert salted_bank_hash(bank_account_on(f"Account number: {ACCOUNT}") or "", "s") == salted_bank_hash(ACCOUNT, "s")


class Recording:
    """Captures every text a model would receive, built the way the live client builds it."""

    name = "recording"

    def __init__(self, labels: dict) -> None:
        self.labels = labels
        self.prompts: list[str] = []

    def extract(self, prompt_name, document_text, *, source_sha256, repair_hint=None):
        messages, _ = build_messages(prompt_name, document_text, 8000, repair_hint)
        self.prompts.append(json.dumps(messages))
        return ModelReply(json.dumps(self.labels[source_sha256]))


@pytest.mark.redaction
def test_no_seeded_bank_number_reaches_a_prompt_a_trace_or_a_log(seeded, capsys) -> None:
    model = Recording({i.sha256: i.label for i in verify_set().items if i.label})
    lines: list[str] = []
    logs.add_sink(lines.append)
    ctx = seeded.ctx()
    ctx.model = model
    run_pass(ctx, from_start=True)
    logs.remove_sink(lines.append)
    assert len(model.prompts) == 11 and any(MASK in prompt for prompt in model.prompts)
    surfaces = model.prompts + lines + seeded.store.trace(seeded.settings.scope) + [capsys.readouterr().out]
    stored = json.dumps(seeded.store.review(seeded.settings.scope), default=str) + json.dumps(seeded.store.events(seeded.settings.scope), default=str)
    for number in known_bank_strings():
        assert not [s for s in surfaces if number in s], number
        assert number not in stored, number
