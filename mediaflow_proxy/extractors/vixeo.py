import base64
import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, SoupStrainer

from mediaflow_proxy.extractors.base import BaseExtractor, ExtractorError


class VixeoExtractor(BaseExtractor):
    async def extract(self, url: str, **kwargs) -> dict:
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "vixeo.io"
            or not re.fullmatch(r"/e/[A-Za-z0-9]+/?", parsed.path)
        ):
            raise ExtractorError("Vixeo: invalid embed URL")
        page = await self._make_request(url, allow_redirects=False)
        root = BeautifulSoup(page.text, "lxml", parse_only=SoupStrainer(id="streamsonic-player-root")).find(
            id="streamsonic-player-root"
        )
        encoded = root.get("data-config", "") if root else ""
        if not 0 < len(encoded) <= 65536:
            raise ExtractorError("Vixeo: player configuration missing or invalid")
        try:
            data = json.loads(base64.b64decode(encoded, validate=True))
            source = data["source"].replace("|", "")
            if len(source) > 8192 or not re.fullmatch("[0-9a-fA-F]+", source):
                raise ValueError("Invalid media source")
            media_url = urljoin(url, bytes.fromhex(source).decode("latin-1")[::-1])
            media = urlparse(media_url)
            is_mp4 = data["isMp4"]
            if (
                media.scheme != "https"
                or not media.hostname
                or media.username is not None
                or not isinstance(is_mp4, bool)
            ):
                raise ValueError("Invalid media URL or format")
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ExtractorError("Vixeo: invalid player configuration") from exc
        return {
            "destination_url": media_url,
            "request_headers": {**self.base_headers, "referer": url},
            "mediaflow_endpoint": "proxy_stream_endpoint" if is_mp4 else "hls_manifest_proxy",
        }
