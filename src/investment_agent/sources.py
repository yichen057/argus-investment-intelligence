from urllib.parse import unquote


def source_display_name(source_uri: str) -> str:
    if source_uri.startswith("file://"):
        name = source_uri.removeprefix("file://").rstrip("/").split("/")[-1]
    else:
        name = source_uri.rstrip("/").split("/")[-1]
    name = unquote(name)
    prefix, separator, original_name = name.partition("_")
    if separator and len(prefix) == 32 and all(
        character in "0123456789abcdef" for character in prefix.lower()
    ):
        return original_name
    return name
