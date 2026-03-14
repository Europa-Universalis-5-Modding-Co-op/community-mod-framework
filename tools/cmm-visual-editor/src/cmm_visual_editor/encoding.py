"""UTF-8-BOM encoding helpers for Paradox script files."""

BOM = b"\xef\xbb\xbf"


def encode_bom(text: str) -> bytes:
    """Encode text as UTF-8 with BOM prefix and CRLF line endings."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    return BOM + normalized.encode("utf-8")


def encode_json(text: str) -> bytes:
    """Encode JSON text as UTF-8 (no BOM) with CRLF line endings."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    return normalized.encode("utf-8")


def decode_bom(data: bytes) -> str:
    """Decode UTF-8 data, stripping BOM if present."""
    if data.startswith(BOM):
        data = data[3:]
    return data.decode("utf-8")
