from investment_agent.sources import source_display_name


def test_source_display_name_removes_upload_storage_prefix() -> None:
    source_uri = (
        "file:///app/data/uploads/"
        "90a03d80b62f4edd8bc705a6359402fc_gold_real_yields.md"
    )

    assert source_display_name(source_uri) == "gold_real_yields.md"


def test_source_display_name_preserves_regular_file_name() -> None:
    assert source_display_name("file:///research/gold.md") == "gold.md"


def test_source_display_name_decodes_url_encoded_file_name() -> None:
    assert (
        source_display_name("file:///research/Ray%20Dalio%27s%20Gold.md")
        == "Ray Dalio's Gold.md"
    )
