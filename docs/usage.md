# MediaFlow Proxy usage

Start the local development server with Python 3.13 and the locked dependencies:

```bash
uv sync --locked --python 3.13
uv run --no-sync uvicorn mediaflow_proxy.main:app --host 127.0.0.1 --port 8888 --no-access-log
```

See [endpoint overview](usage/overview.md) for direct media, HLS and DASH proxying. The running server serves its generated OpenAPI document at `/openapi.json` and Swagger UI at `/docs`.

## Resolve a video host

Use a concrete embed or watch URL as `d` and URL-encode its full value. For a URL that uses a fragment as the video ID, encode `#` as part of the parameter. Browsers otherwise treat the fragment as part of the MediaFlow URL and omit it from the HTTP request. See [extractor parameters and provider names](usage/extractor.md).

For an authenticated instance, set `MEDIAFLOW_API_PASSWORD` in your local environment and send it as the `api_password` header. This example returns extraction metadata:

```bash
curl --get 'http://127.0.0.1:8888/extractor/video' \
  --header "api_password: $MEDIAFLOW_API_PASSWORD" \
  --data-urlencode 'host=FireStream' \
  --data-urlencode 'd=https://firestream.to/e/example'
```

Add `--data-urlencode 'redirect_stream=true'` for a 302 to the selected proxy route. When `API_PASSWORD` is configured, the redirect carries an encrypted playback token. Treat that token as a credential. Use [URL generation](usage/url-params-and-encoding.md#generating-urls) when playback needs a specific expiry or IP binding.

| Provider | Playback route |
|----------|----------------|
| FireStream | Use `/extractor/video` for watch and embed links. The player response determines HLS or MP4. |
| Veev | Use `/extractor/video.mp4`. Keep extraction and media requests on the same egress IP. |
| GUpload | The URL generator defaults to HLS via `/extractor/video.m3u8`. Use `/extractor/video` to follow the source format or select `.mp4` explicitly for an MP4 source. |
| VOE | Use `/extractor/video.m3u8` or the generic extractor route. |
| Vixeo | Use `/extractor/video`. The embed declares the media format. |
| VidHide on `moflix-stream.click` | Use `/extractor/video.m3u8`. The proxy removes the PNG wrapper from MPEG-TS segments. |
| FileMoon-compatible `moflix-stream.link` | Pass `host=FileMoon` for the `/e/<id>` player. |

For a playback check, follow the redirect and request a small byte range for MP4. Confirm the content type and MP4 signature. For HLS, confirm `#EXTM3U`, follow any variant playlist and check a segment. An extractor 302 establishes that it returned a signed proxy URL. A separate media request establishes whether the CDN delivered bytes.

A hoster or player API HTTP 404 can indicate an unavailable video. Preserve the stage when recording 403, 502, TLS or timeout results. A signing failure occurs before the proxy can fetch the target. Keep query credentials and playback tokens out of logs and shared reports.
