"""Streaming multipart parser: the video part goes straight to disk, chunk by chunk.

The request body is never held in memory and the size limit is enforced while the
bytes arrive, so an oversized upload is rejected without being stored.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from python_multipart.multipart import MultipartParser, parse_options_header

from app.errors import ApiError

MAX_FIELD_BYTES = 64 * 1024


@dataclass
class ParsedUpload:
    fields: dict[str, str] = field(default_factory=dict)
    file_path: Path | None = None
    filename: str = ""
    content_type: str = ""
    size: int = 0


class _TooLargeError(Exception):
    """The file part exceeded the size limit while streaming."""


async def parse_multipart_upload(
    stream: AsyncIterator[bytes],
    content_type_header: str,
    *,
    file_field: str,
    dest_for: Callable[[str], Path],
    max_file_bytes: int,
) -> ParsedUpload:
    """Parse a multipart body. ``dest_for(filename)`` returns where to write the file."""
    ctype, params = parse_options_header(content_type_header)
    if ctype != b"multipart/form-data" or b"boundary" not in params:
        raise ApiError(400, "invalid_upload", "Expected a multipart/form-data upload.")

    result = ParsedUpload()
    headers: dict[bytes, bytes] = {}
    header_field = bytearray()
    header_value = bytearray()
    current_name: str | None = None
    current_is_file = False
    field_buf = bytearray()
    fh: BinaryIO | None = None

    def on_header_field(data: bytes, start: int, end: int) -> None:
        header_field.extend(data[start:end])

    def on_header_value(data: bytes, start: int, end: int) -> None:
        header_value.extend(data[start:end])

    def on_header_end() -> None:
        headers[bytes(header_field).lower()] = bytes(header_value)
        header_field.clear()
        header_value.clear()

    def on_part_begin() -> None:
        nonlocal current_name, current_is_file
        headers.clear()
        field_buf.clear()
        current_name = None
        current_is_file = False

    def on_headers_finished() -> None:
        nonlocal current_name, current_is_file, fh
        _, disp = parse_options_header(headers.get(b"content-disposition", b""))
        current_name = disp.get(b"name", b"").decode("utf-8", errors="replace")
        filename = disp.get(b"filename")
        if current_name == file_field and filename is not None:
            current_is_file = True
            result.filename = filename.decode("utf-8", errors="replace")
            result.content_type = headers.get(b"content-type", b"").decode("latin-1")
            path = dest_for(result.filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            result.file_path = path
            fh = path.open("wb")

    def on_part_data(data: bytes, start: int, end: int) -> None:
        if current_is_file and fh is not None:
            result.size += end - start
            if result.size > max_file_bytes:
                raise _TooLargeError()
            fh.write(data[start:end])
        else:
            field_buf.extend(data[start:end])
            if len(field_buf) > MAX_FIELD_BYTES:
                raise ApiError(413, "field_too_large", f"The field '{current_name}' is too long.")

    def on_part_end() -> None:
        nonlocal fh
        if current_is_file and fh is not None:
            fh.close()
            fh = None
        elif current_name:
            result.fields[current_name] = field_buf.decode("utf-8", errors="replace")

    parser = MultipartParser(
        params[b"boundary"],
        callbacks={
            "on_part_begin": on_part_begin,
            "on_part_data": on_part_data,
            "on_part_end": on_part_end,
            "on_header_field": on_header_field,
            "on_header_value": on_header_value,
            "on_header_end": on_header_end,
            "on_headers_finished": on_headers_finished,
        },
    )
    try:
        async for chunk in stream:
            if chunk:
                parser.write(chunk)
        parser.finalize()
    except _TooLargeError:
        raise ApiError(
            413,
            "file_too_large",
            f"This video is larger than the {max_file_bytes // (1024 * 1024)} MB limit.",
        ) from None
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError(400, "invalid_upload", "The upload was malformed or interrupted.") from exc
    finally:
        if fh is not None:
            fh.close()
    return result
