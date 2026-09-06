import re
import unicodedata


MAX_HSDS_DOMAIN_LENGTH = 2048
_PERCENT_ESCAPE = re.compile(r"%[0-9A-Fa-f]{2}")


def validate_hsds_file_domain(value: str, suffix: str = ".nxs") -> str:
    """Validate an HSDS file reference and return its canonical file domain."""
    if not value:
        raise ValueError("invalid HSDS domain")

    # Browser viewers use the fragment as an object path; h5pyd opens the file domain only.
    domain = value.partition("#")[0]
    if not domain or len(domain) > MAX_HSDS_DOMAIN_LENGTH:
        raise ValueError("invalid HSDS domain")
    if "\\" in domain or _PERCENT_ESCAPE.search(domain):
        raise ValueError("invalid HSDS domain")
    if any(unicodedata.category(character) == "Cc" for character in domain):
        raise ValueError("invalid HSDS domain")

    _validate_rooted_path(domain)
    if not domain.endswith(suffix):
        raise ValueError("invalid HSDS domain")

    return domain


def _validate_rooted_path(value: str) -> None:
    if not value.startswith("/") or value.startswith("//") or value.endswith("/"):
        raise ValueError("invalid HSDS domain")

    segments = value[1:].split("/")
    for segment in segments:
        if not segment or segment in {".", ".."}:
            raise ValueError("invalid HSDS domain")
