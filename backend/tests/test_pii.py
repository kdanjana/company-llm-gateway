"""Personal-data masking: unit tests for pii.py, plus one end-to-end request."""
from gateway import pii
from gateway.models import UsageLog

from .conftest import chat_body, post_chat


def valid_aadhaar(base="23456789012") -> str:
    """12 digits that pass the Verhoeff check (made up, not a real person's number)."""
    return next(base + d for d in "0123456789" if pii._verhoeff_ok(base + d))


def invalid_aadhaar(base="23456789012") -> str:
    return next(base + d for d in "0123456789" if not pii._verhoeff_ok(base + d))


def test_email_is_masked():
    text, counts = pii.mask_text("Write to ravi.k@quickbite.in today")
    assert text == "Write to [EMAIL] today"
    assert counts["EMAIL"] == 1


def test_indian_phone_numbers_are_masked():
    text, counts = pii.mask_text("Call 9876543210 or +91 98765 43210.")
    assert text == "Call [PHONE] or [PHONE]."
    assert counts["PHONE"] == 2


def test_card_number_passing_luhn_is_masked():
    text, _ = pii.mask_text("Card: 4111 1111 1111 1111")
    assert text == "Card: [CARD]"


def test_card_like_number_failing_luhn_is_not_masked_as_card():
    text, counts = pii.mask_text("Order 4111 1111 1111 1112")
    assert counts["CARD"] == 0
    assert "[CARD]" not in text


def test_pan_is_masked():
    text, _ = pii.mask_text("PAN ABCDE1234F on file")
    assert text == "PAN [PAN] on file"


def test_valid_aadhaar_is_masked_even_with_spaces():
    n = valid_aadhaar()
    text, counts = pii.mask_text(f"Aadhaar {n[:4]} {n[4:8]} {n[8:]}")
    assert text == "Aadhaar [AADHAAR]"
    assert counts["AADHAAR"] == 1


def test_twelve_digits_failing_verhoeff_are_left_alone():
    n = invalid_aadhaar()
    text, counts = pii.mask_text(f"Ticket {n}")
    assert text == f"Ticket {n}"
    assert sum(counts.values()) == 0


def test_normal_text_is_unchanged():
    sentence = "Our refund window is 30 days and the office opens at 9:30."
    assert pii.mask_text(sentence) == (sentence, pii.Counter())


def test_request_is_masked_before_reaching_the_model(api, raw_key, price, fake_bedrock):
    data = chat_body(
        system="Customer email: ravi@quickbite.in",
        messages=[{"role": "user", "content": "Refund to card 4111 1111 1111 1111 please"}],
    )
    response = post_chat(api, raw_key, data)

    assert response.status_code == 200
    call = fake_bedrock.calls[0]
    assert call["messages"][0]["content"][0]["text"] == "Refund to card [CARD] please"
    assert call["system"] == "Customer email: [EMAIL]"
    assert response.data["pii_masked"] == 2
    assert UsageLog.objects.get().pii_masked_count == 2
