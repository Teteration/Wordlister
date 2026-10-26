"""Dispatch bounded HTTP responses to format-specific extractors."""

from wordlister_core.evidence import WordEvidence
from wordlister_core.extractors.headers import extract_headers
from wordlister_core.extractors.html import extract_html
from wordlister_core.extractors.javascript import extract_javascript
from wordlister_core.extractors.json_data import extract_json_text
from wordlister_core.extractors.url import extract_url
from wordlister_core.models import FetchedResponse


def _content_type(response: FetchedResponse) -> str:
    for name, value in response.headers.items():
        if name.lower() == "content-type":
            return value.split(";", maxsplit=1)[0].strip().lower()
    return ""


def extract_response(
    response: FetchedResponse,
    *,
    include_comments: bool,
) -> WordEvidence:
    """Extract candidates from response metadata and a recognized textual body."""

    response_urls = dict.fromkeys(
        (response.requested_url, *(hop.url for hop in response.history), response.final_url)
    )
    words = WordEvidence()
    for url in response_urls:
        words.update(extract_url(url))
    words.update(extract_headers(response.headers, response.final_url))

    for hop in response.history:
        words.update(extract_headers(hop.headers, hop.url))

    content_type = _content_type(response)
    if content_type == "application/json" or content_type.endswith("+json"):
        words.update(extract_json_text(response.text, base_url=response.final_url))
    elif content_type in {"application/javascript", "application/x-javascript", "text/javascript"}:
        words.update(extract_javascript(response.text, base_url=response.final_url))
    elif content_type in {"text/html", "application/xhtml+xml"} or not content_type:
        words.update(
            extract_html(
                response.text,
                response.final_url,
                include_comments=include_comments,
            )
        )

    return words
