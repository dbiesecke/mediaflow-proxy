import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, SoupStrainer

from mediaflow_proxy.extractors.base import BaseExtractor, ExtractorError


class FireStreamExtractor(BaseExtractor):
    _hosts = {"firestream.to", "firestream.site", "frstream.life"}

    async def extract(self, url: str, **kwargs) -> dict:
        parsed = urlparse(url)
        match = re.fullmatch(r"/[ev]/([A-Za-z0-9_-]+)/?", parsed.path)
        if parsed.scheme != "https" or parsed.netloc not in self._hosts or not match:
            raise ExtractorError("FireStream: invalid video URL")

        slug = match[1]
        embed_url = urljoin(url, f"/e/{slug}")
        page = await self._make_request(embed_url, allow_redirects=False)
        if page.status in {301, 302, 303, 307, 308}:
            embed_url = urljoin(embed_url, page.headers.get("Location", ""))
            target = urlparse(embed_url)
            if target.scheme != "https" or target.netloc not in self._hosts or target.path != f"/e/{slug}":
                raise ExtractorError("FireStream: unexpected embed redirect")
            page = await self._make_request(embed_url, allow_redirects=False)

        script = BeautifulSoup(page.text, "lxml", parse_only=SoupStrainer("script", id="token-blob")).script
        blob = script.get_text(strip=True) if script else ""
        if not blob or len(blob) > 65536:
            raise ExtractorError("FireStream: player token missing or invalid")

        origin = page.get_origin()
        headers = {"referer": embed_url, "origin": origin}
        response = await self._make_request(
            f"{origin}/api/videos/{slug}/resolve",
            method="POST",
            headers=headers,
            json={"blob": blob},
            allow_redirects=False,
        )
        try:
            data = response.json()
            for key in ("signedVideoUrl", "signedVideoSdUrl", "signedVideoMp4Url", "signedVideoSdMp4Url"):
                media_url = data.get(key)
                if not isinstance(media_url, str):
                    continue
                media = urlparse(media_url)
                if media.scheme != "https" or not media.hostname or media.username is not None:
                    continue
                extension = media.path.lower().rsplit(".", 1)[-1]
                if extension in {"m3u8", "mp4"}:
                    return {
                        "destination_url": media_url,
                        "request_headers": {**self.base_headers, **headers},
                        "mediaflow_endpoint": "hls_manifest_proxy" if extension == "m3u8" else "proxy_stream_endpoint",
                    }
        except (AttributeError, ValueError) as exc:
            raise ExtractorError("FireStream: invalid player API response") from exc
        raise ExtractorError("FireStream: no supported media in player response")
