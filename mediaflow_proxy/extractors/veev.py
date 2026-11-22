import json
import re
from urllib.parse import urlparse

from mediaflow_proxy.extractors.base import BaseExtractor, ExtractorError


def _decode_lzw(value: str) -> str:
    if not isinstance(value, str) or not 0 < len(value) <= 65536:
        raise ValueError("Invalid Veev LZW input")
    previous = value[0]
    if ord(previous) >= 256:
        raise ValueError("Invalid Veev LZW start")
    parts = [previous]
    size = 1
    dictionary = {}
    for char in value[1:]:
        code = ord(char)
        next_code = 256 + len(dictionary)
        part = char if code < 256 else dictionary.get(code)
        if code == next_code:
            part = previous + previous[0]
        if not part or size + len(part) > 65536:
            raise ValueError("Invalid or oversized Veev LZW data")
        parts.append(part)
        size += len(part)
        dictionary[next_code] = previous + part[0]
        previous = part
    return "".join(parts)


def _decode_layers(encoded: str, operations: str) -> str:
    value = _decode_lzw(encoded)
    for operation in reversed(operations):
        if operation == "1":
            value = value[::-1]
        value = bytes.fromhex(value).decode().replace("dXRmOA==", "")
    return value


class VeevExtractor(BaseExtractor):
    async def extract(self, url: str, **kwargs) -> dict:
        parsed = urlparse(url)
        match = re.fullmatch(r"/e/([A-Za-z0-9]+)/?", parsed.path)
        if parsed.scheme != "https" or parsed.netloc != "veev.to" or not match:
            raise ExtractorError("Veev: invalid embed URL")

        code = match[1]
        origin = "https://veev.to"
        page = await self._make_request(url, allow_redirects=False)
        token = re.search(
            r"""__pqrsww\s*=\s*['"]fc['"][\s\S]{0,200}?window\._vvto\[__pqrsww\]\s*=\s*("(?:[^"\\]|\\.)*")""",
            page.text,
        )
        if not token or len(token[1]) > 65536:
            raise ExtractorError("Veev: player token missing or invalid")

        try:
            challenge = _decode_lzw(json.loads(token[1]))
            layers = []
            offset = 0
            for _ in range(3):
                count = int(challenge[offset])
                row = challenge[offset + 1 : offset + 1 + count]
                if not count or len(row) != count or not re.fullmatch("[01]+", row):
                    raise ValueError("Invalid Veev layer configuration")
                layers.append(row)
                offset += count + 1
        except (IndexError, ValueError) as exc:
            raise ExtractorError("Veev: invalid player challenge") from exc

        response = await self._make_request(
            f"{origin}/dl",
            headers={"referer": url},
            params={"op": "player_api", "cmd": "gi", "file_code": code, "r": url, "ch": challenge, "ie": "1"},
            allow_redirects=False,
        )
        try:
            data = response.json()
            file = data.get("file") or {}
            if data.get("status") != "success" or file.get("file_status") != "OK" or file.get("file_code") != code:
                raise ExtractorError("Veev: player API returned no matching video")
            for item in file["dv"][:16]:
                try:
                    media_url = _decode_layers(item["s"], layers[0])
                    mime = _decode_layers(item["t"], layers[1])
                    media = urlparse(media_url)
                except (KeyError, TypeError, ValueError):
                    continue
                if mime == "video/mp4" and media.scheme == "https" and media.hostname and media.username is None:
                    return {
                        "destination_url": media_url,
                        "request_headers": {**self.base_headers, "referer": f"{origin}/"},
                        "mediaflow_endpoint": "proxy_stream_endpoint",
                    }
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ExtractorError("Veev: invalid player API response") from exc
        raise ExtractorError("Veev: no supported MP4 source in player response")
