_ENDPOINT_URL_PREFIXES = ("http://", "https://", "http+unix://")


def reject_hsds_endpoint_override(value: str) -> None:
    """Reject URL forms that make h5pyd replace its configured endpoint."""
    if value.lower().startswith(_ENDPOINT_URL_PREFIXES):
        raise ValueError("invalid HSDS domain")
