MAX_HSDS_DOMAIN_LENGTH = 2048
_FORBIDDEN_DOMAIN_CHARACTERS = "?@:"


def validate_hsds_file_domain(value: str) -> str:
    """Validate an HSDS file reference and return its canonical file domain."""
    if not value or len(value) > MAX_HSDS_DOMAIN_LENGTH or not value.isascii():
        raise ValueError("invalid HSDS domain")
    if (
        value.strip() != value
        or not value.isprintable()
        or "\\" in value
        or "%" in value
    ):
        raise ValueError("invalid HSDS domain")

    parts = value.split("#")
    if len(parts) > 2:
        raise ValueError("invalid HSDS domain")

    domain = parts[0]
    fragment = parts[1] if len(parts) == 2 else None
    _validate_rooted_path(domain)
    if (
        not domain.endswith(".nxs")
        or any(character in domain for character in _FORBIDDEN_DOMAIN_CHARACTERS)
    ):
        raise ValueError("invalid HSDS domain")

    if fragment is not None:
        _validate_rooted_path(fragment)

    return domain


def _validate_rooted_path(value: str) -> None:
    if not value.startswith("/") or value.startswith("//") or value.endswith("/"):
        raise ValueError("invalid HSDS domain")

    segments = value[1:].split("/")
    if not segments:
        raise ValueError("invalid HSDS domain")
    for segment in segments:
        if (
            not segment
            or segment in {".", ".."}
            or segment.strip() != segment
        ):
            raise ValueError("invalid HSDS domain")
