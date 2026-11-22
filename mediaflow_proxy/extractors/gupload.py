import base64
from itertools import cycle
import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup, SoupStrainer

from mediaflow_proxy.extractors.base import BaseExtractor, ExtractorError


class GuploadExtractor(BaseExtractor):
    _hosts = {"gupload.xyz", "gupload.site", "gupload.io"}

    @staticmethod
    def _player_config(html: str) -> dict:
        legacy = re.search(r"""decodePayload\(\s*['"]([^'"]+)['"]\s*\)""", html)
        try:
            if legacy:
                return json.loads(base64.b64decode(legacy[1].strip(), validate=True).split(b"|", 1)[1])
            for script in BeautifulSoup(html, "lxml", parse_only=SoupStrainer("script")).find_all("script"):
                source = script.string or ""
                if "initModernPlayer" not in source:
                    continue
                config = re.search(r"\bvar\s+_cfg\s*=\s*_dp\('[0-9a-fA-F]{8}~([A-Za-z0-9+/=]{1,65536})'\)", source)
                key = re.search(
                    r"var _p=\['([^'\\]{1,16})','([^'\\]{1,16})','([^'\\]{1,16})','([^'\\]{1,16})'\]"
                    r";return _p\[0\]\+_p\[1\]\+_p\[2\]\+_p\[3\];",
                    source,
                )
                if config and key:
                    encoded = base64.b64decode(config[1], validate=True)
                    return json.loads(bytes(a ^ b for a, b in zip(encoded, cycle("".join(key.groups()).encode()))))
        except (IndexError, ValueError) as exc:
            raise ExtractorError("GUpload: invalid player configuration") from exc
        raise ExtractorError("GUpload: player configuration not found")

    async def extract(self, url: str, **kwargs) -> dict:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc not in self._hosts:
            raise ExtractorError("GUpload: invalid embed domain")

        origin = f"https://{parsed.netloc}"
        headers = {**self.base_headers, "referer": f"{origin}/", "origin": origin}
        page = await self._make_request(url, headers=headers, allow_redirects=False)
        data = self._player_config(page.text)
        media_url = data.get("videoUrl") if isinstance(data, dict) else None
        if not isinstance(media_url, str):
            raise ExtractorError("GUpload: player configuration has no video URL")

        media = urlparse(media_url)
        if media.scheme != "https" or media.netloc not in self._hosts:
            raise ExtractorError("GUpload: unsupported media origin")
        extension = media.path.lower().rsplit(".", 1)[-1]
        if extension not in {"m3u8", "mp4"}:
            raise ExtractorError("GUpload: unsupported media format")
        return {
            "destination_url": media_url,
            "request_headers": headers,
            "mediaflow_endpoint": "hls_manifest_proxy" if extension == "m3u8" else "proxy_stream_endpoint",
        }
