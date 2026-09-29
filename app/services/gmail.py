import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, time as datetime_time, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from cryptography.fernet import Fernet
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import EmailAccount, EmailMessage, IgnoredEmail, utcnow
from app.schemas import EmailImport
from app.services.pipeline import ProcessingPipeline
from app.services.exclusions import matching_pattern

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
OAUTH_STATE_MAX_AGE_SECONDS = 10 * 60


def sync_query(settings: Settings) -> str:
    """Keep Gmail search at or after the configured inclusive cutoff date."""
    gmail_after_date = settings.gmail_sync_start_date - timedelta(days=1)
    return (
        f"after:{gmail_after_date.strftime('%Y/%m/%d')} "
        "(application OR internship OR interview OR assessment OR recruiter OR offer)"
    )


def _state_signing_key(settings: Settings) -> bytes:
    if not settings.token_encryption_key:
        raise ValueError("TOKEN_ENCRYPTION_KEY is required before Gmail can be connected")
    return settings.token_encryption_key.encode()


def _create_oauth_state(settings: Settings) -> str:
    payload = f"{int(time.time())}.{secrets.token_urlsafe(32)}"
    signature = hmac.new(_state_signing_key(settings), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def _validate_oauth_state(settings: Settings, state: str) -> None:
    try:
        timestamp, nonce, signature = state.split(".", 2)
        issued_at = int(timestamp)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("OAuth state is invalid; restart the connection flow") from exc
    payload = f"{timestamp}.{nonce}"
    expected = hmac.new(_state_signing_key(settings), payload.encode(), hashlib.sha256).hexdigest()
    age = int(time.time()) - issued_at
    if not hmac.compare_digest(signature, expected) or age < 0 or age > OAUTH_STATE_MAX_AGE_SECONDS:
        raise ValueError("OAuth state is invalid or expired; restart the connection flow")


def gmail_readiness(settings: Settings) -> dict:
    issues: list[str] = []
    path = Path(settings.google_client_secrets_file)
    client_type = "unknown"
    redirect_uris: list[str] = []
    if not path.exists():
        issues.append(f"OAuth client file not found: {path}")
    else:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            client_type = "web" if "web" in payload else "installed" if "installed" in payload else "unknown"
            client = payload.get(client_type, {}) if client_type != "unknown" else {}
            if client_type != "web":
                issues.append("OAuth client must be a Google Web application")
            if not client.get("client_id") or not client.get("client_secret"):
                issues.append("OAuth client ID or secret is missing")
            redirect_uris = client.get("redirect_uris", [])
            if settings.google_oauth_redirect_uri not in redirect_uris:
                issues.append(
                    f"Register and download this redirect URI: {settings.google_oauth_redirect_uri}"
                )
        except (json.JSONDecodeError, OSError, TypeError):
            issues.append("OAuth client file is not valid Google client JSON")
    if not settings.token_encryption_key:
        issues.append("TOKEN_ENCRYPTION_KEY is not configured")
    else:
        try:
            Fernet(settings.token_encryption_key.encode())
        except (ValueError, TypeError):
            issues.append("TOKEN_ENCRYPTION_KEY is not a valid Fernet key")
    return {
        "ready": not issues,
        "client_type": client_type,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "redirect_registered": settings.google_oauth_redirect_uri in redirect_uris,
        "issues": issues,
    }


def _flow(settings: Settings, state: str | None = None) -> Flow:
    if not Path(settings.google_client_secrets_file).exists():
        raise FileNotFoundError(
            f"Google OAuth client file not found: {settings.google_client_secrets_file}. See docs/YOUR_PART.md."
        )
    return Flow.from_client_secrets_file(
        settings.google_client_secrets_file,
        scopes=SCOPES,
        redirect_uri=settings.google_oauth_redirect_uri,
        state=state,
        autogenerate_code_verifier=False,
    )


def authorization_url(settings: Settings) -> str:
    readiness = gmail_readiness(settings)
    if not readiness["ready"]:
        raise ValueError("; ".join(readiness["issues"]))
    state = _create_oauth_state(settings)
    flow = _flow(settings)
    url, _ = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent", state=state
    )
    return url


def save_callback(session: Session, settings: Settings, code: str, state: str) -> EmailAccount:
    _validate_oauth_state(settings, state)
    if not settings.token_encryption_key:
        raise ValueError("TOKEN_ENCRYPTION_KEY is required before Gmail can be connected")
    flow = _flow(settings, state)
    flow.fetch_token(code=code)
    credentials = flow.credentials
    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    email_address = service.users().getProfile(userId="me").execute()["emailAddress"]
    encrypted = Fernet(settings.token_encryption_key.encode()).encrypt(credentials.to_json().encode()).decode()
    account = session.scalar(select(EmailAccount).where(EmailAccount.email_address == email_address))
    if not account:
        account = EmailAccount(email_address=email_address)
        session.add(account)
    account.encrypted_credentials = encrypted
    session.commit()
    session.refresh(account)
    return account


def _credentials(account: EmailAccount, settings: Settings) -> Credentials:
    if not settings.token_encryption_key or not account.encrypted_credentials:
        raise ValueError("Missing encrypted Gmail credentials")
    raw = Fernet(settings.token_encryption_key.encode()).decrypt(account.encrypted_credentials.encode())
    return Credentials.from_authorized_user_info(json.loads(raw), SCOPES)


def _header(headers: list[dict], name: str) -> str:
    return next((item["value"] for item in headers if item["name"].lower() == name.lower()), "")


def _body(payload: dict) -> tuple[str | None, str | None]:
    html: str | None = None
    plain: str | None = None

    def visit(part: dict) -> None:
        nonlocal html, plain
        data = part.get("body", {}).get("data")
        if data:
            decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode(errors="replace")
            if part.get("mimeType") == "text/plain" and plain is None:
                plain = decoded
            elif part.get("mimeType") == "text/html" and html is None:
                html = decoded
        for child in part.get("parts", []):
            visit(child)

    visit(payload)
    return html, plain


def sync_account(
    session: Session, settings: Settings, pipeline: ProcessingPipeline, account_id: int, limit: int = 100
) -> dict[str, object]:
    account = session.get(EmailAccount, account_id)
    if not account:
        raise LookupError("Email account not found")
    service = build("gmail", "v1", credentials=_credentials(account, settings), cache_discovery=False)
    query = sync_query(settings)
    cutoff = datetime.combine(settings.gmail_sync_start_date, datetime_time.min, tzinfo=timezone.utc)
    created = duplicate = scanned = pattern_matched = too_old = 0
    gmail_seconds = classification_seconds = persistence_seconds = 0.0
    page_token: str | None = None
    while created < limit:
        request = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=min(limit, 100),
            pageToken=page_token,
        )
        response = request.execute()
        items = response.get("messages", [])
        if not items:
            break

        item_ids = [item["id"] for item in items]
        imported_ids = set(session.scalars(
            select(EmailMessage.gmail_message_id).where(EmailMessage.gmail_message_id.in_(item_ids))
        ))
        ignored_ids = set(session.scalars(
            select(IgnoredEmail.gmail_message_id).where(IgnoredEmail.gmail_message_id.in_(item_ids))
        ))
        unseen_items = [item for item in items if item["id"] not in imported_ids | ignored_ids]
        scanned += len(items)
        duplicate += len(items) - len(unseen_items)
        remaining = limit - created
        emails: list[EmailImport] = []
        fetch_started = time.perf_counter()
        for item in unseen_items[:remaining]:
            raw = service.users().messages().get(userId="me", id=item["id"], format="full").execute()
            headers = raw["payload"].get("headers", [])
            received = parsedate_to_datetime(_header(headers, "Date")) if _header(headers, "Date") else None
            if received is None:
                received = datetime.fromtimestamp(int(raw["internalDate"]) / 1000, tz=timezone.utc)
            elif received.tzinfo is None:
                received = received.replace(tzinfo=timezone.utc)
            if received.astimezone(timezone.utc) < cutoff:
                too_old += 1
                continue
            html, plain = _body(raw["payload"])
            email = EmailImport(
                external_id=raw["id"],
                thread_id=raw.get("threadId"),
                sender=_header(headers, "From"),
                recipient=_header(headers, "To"),
                subject=_header(headers, "Subject"),
                body_html=html,
                body_text=plain,
                received_at=received,
                labels=raw.get("labelIds", []),
            )
            if pattern := matching_pattern(session, email.sender):
                session.add(IgnoredEmail(
                    gmail_message_id=email.external_id,
                    sender=email.sender,
                    subject=email.subject,
                    reason=f"learned-{pattern.kind}-pattern",
                ))
                pattern_matched += 1
                continue
            emails.append(email)
        gmail_seconds += time.perf_counter() - fetch_started

        if emails:
            classify_started = time.perf_counter()
            classified = pipeline.classify_many(emails)
            classification_seconds += time.perf_counter() - classify_started
            persistence_started = time.perf_counter()
            for email, clean_body, result in classified:
                pipeline.ingest_classified(session, email, clean_body, result)
            session.commit()
            persistence_seconds += time.perf_counter() - persistence_started
            created += len(classified)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    account.last_synced_at = utcnow()
    session.commit()
    return {
        "created": created,
        "duplicates": duplicate,
        "pattern_matched": pattern_matched,
        "too_old": too_old,
        "scanned": scanned,
        "timing": {
            "gmail_fetch_seconds": round(gmail_seconds, 3),
            "classification_seconds": round(classification_seconds, 3),
            "persistence_seconds": round(persistence_seconds, 3),
            "total_seconds": round(gmail_seconds + classification_seconds + persistence_seconds, 3),
        },
    }
