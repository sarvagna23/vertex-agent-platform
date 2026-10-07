from pii.redactor import redact_pii


def test_email_is_masked():
    result = redact_pii("Reach me at jane.doe+bank@example.com about my account")
    assert "jane.doe" not in result.text
    assert "[EMAIL]" in result.text
    assert result.counts["EMAIL"] == 1


def test_phone_is_masked():
    result = redact_pii("Call me on (404) 555-0123 or 404.555.0199")
    assert "555" not in result.text
    assert result.counts["PHONE"] == 2


def test_ssn_and_card_are_masked_before_phone():
    result = redact_pii("SSN 123-45-6789 and card 4111 1111 1111 1111")
    assert "[SSN]" in result.text
    assert "[CARD]" in result.text
    assert "PHONE" not in result.counts


def test_name_after_lead_in_is_masked():
    result = redact_pii("My name is Jane Doe and my mortgage payment vanished")
    assert "Jane" not in result.text
    assert "My name is [NAME]" in result.text


def test_title_name_is_masked():
    result = redact_pii("I spoke with Mr. Johnson at the branch")
    assert "Johnson" not in result.text


def test_company_names_are_not_masked():
    text = "This is Citibank refusing to fix a billing error"
    assert redact_pii(text).text == text


def test_clean_text_unchanged():
    text = "Why do customers complain about overdraft fees?"
    result = redact_pii(text)
    assert result.text == text
    assert not result.found_pii
