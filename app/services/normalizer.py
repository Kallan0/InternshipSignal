import re

from bs4 import BeautifulSoup


QUOTE_MARKERS = (
    r"^On .+ wrote:$",
    r"^-{2,}\s*Original Message\s*-{2,}$",
    r"^From:\s.+$",
)


def normalize_email(body_html: str | None, body_text: str | None) -> str:
    """Turn an email into compact visible text without quoted history."""
    text = body_text or ""
    if not text and body_html:
        soup = BeautifulSoup(body_html, "html.parser")
        for element in soup(["script", "style", "head", "img"]):
            element.decompose()
        text = soup.get_text("\n")

    kept: list[str] = []
    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if line.startswith(">") or any(re.match(marker, line, re.IGNORECASE) for marker in QUOTE_MARKERS):
            break
        if re.search(r"unsubscribe|email preferences", line, re.IGNORECASE):
            continue
        kept.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
