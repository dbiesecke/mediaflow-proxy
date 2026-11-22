import re
from urllib.parse import urlparse

from mediaflow_proxy.extractors.base import BaseExtractor, ExtractorError
from mediaflow_proxy.utils.http_utils import DownloadError
from mediaflow_proxy.utils.packed import UnpackingError, eval_solver


class VidHideExtractor(BaseExtractor):
    async def extract(self, url: str, **kwargs) -> dict:
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "moflix-stream.click"
            or not re.fullmatch(r"/embed/[A-Za-z0-9]+/?", parsed.path)
        ):
            raise ExtractorError("VidHide: invalid embed URL")

        headers = {**self.base_headers, "referer": url}
        try:
            # The JW Player uses links.hls4 before the external mirrors.
            media_url = await eval_solver(self, url, headers, [r'"hls4"\s*:\s*"(/stream/[^"]+\.m3u8(?:\?[^"]*)?)"'])
        except UnpackingError as exc:
            if isinstance(exc.__cause__, DownloadError):
                raise exc.__cause__ from None
            raise ExtractorError("VidHide: no primary HLS playlist in player configuration") from exc
        return {
            "destination_url": media_url,
            "request_headers": headers,
            "mediaflow_endpoint": "hls_manifest_proxy",
            "stream_transformer": "ts_stream",
            "remove_response_headers": ["content-length"],
        }
