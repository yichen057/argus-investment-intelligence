from investment_agent.connectors.gmail import GmailFilter


def test_gmail_filter_builds_query_for_multiple_senders() -> None:
    gmail_filter = GmailFilter(
        query="label:investment",
        allowed_senders=("Research@Example.com", "news@example.org"),
        after_epoch=1_700_000_000,
    )

    assert gmail_filter.api_query() == (
        "label:investment "
        "{from:research@example.com from:news@example.org} "
        "after:1700000000"
    )


def test_sender_allowlist_is_case_insensitive() -> None:
    gmail_filter = GmailFilter(allowed_senders=("Research@Example.com",))

    assert gmail_filter.sender_allowed("research@example.com")
    assert not gmail_filter.sender_allowed("other@example.com")

