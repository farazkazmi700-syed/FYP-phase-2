import requests
import uuid
from flask import Blueprint, redirect, render_template, request, session, url_for
from google_auth_oauthlib.flow import Flow

from .config import Config
from .db import get_db
from .utils import google_credentials_path, now_iso, require_login, safe_redirect_target

auth_bp = Blueprint("auth", __name__)


def oauth_redirect_uri() -> str:
    """Return the Google OAuth callback URI used by the authorization flow."""
    return Config.GOOGLE_REDIRECT_URI or url_for("auth.auth_callback", _external=True)


def get_google_oauth_flow():
    """Create the Google OAuth flow from local credentials or environment variables."""
    redirect_uri = oauth_redirect_uri()
    credentials_path = google_credentials_path()

    if credentials_path:
        return Flow.from_client_secrets_file(
            credentials_path,
            scopes=Config.SCOPES,
            redirect_uri=redirect_uri,
            autogenerate_code_verifier=False,
        )

    if not Config.GOOGLE_CLIENT_ID or not Config.GOOGLE_CLIENT_SECRET:
        raise RuntimeError(
            "Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in your .env file."
        )

    client_config = {
        "web": {
            "client_id": Config.GOOGLE_CLIENT_ID,
            "client_secret": Config.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    return Flow.from_client_config(
        client_config,
        scopes=Config.SCOPES,
        redirect_uri=redirect_uri,
        autogenerate_code_verifier=False,
    )


@auth_bp.route("/")
def index():
    """Redirect users to chat when logged in, otherwise show login."""
    if session.get("user_id"):
        return redirect(url_for("chat.chat"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET"])
def login():
    """Render the login page for anonymous users."""
    if session.get("user_id"):
        return redirect(url_for("chat.chat"))
    return render_template("login.html")


@auth_bp.route("/auth/login")
@auth_bp.route("/auth/google")
def auth_login():
    """Start the Google OAuth login flow."""
    try:
        flow = get_google_oauth_flow()
        session["post_auth_redirect"] = safe_redirect_target(request.args.get("next") or url_for("chat.chat"))
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true",
        )
        session["oauth_state"] = state
        return redirect(authorization_url)
    except Exception as exc:
        return render_template("login.html", error=f"OAuth initialization failed: {exc}")


@auth_bp.route("/auth/callback")
def auth_callback():
    """Handle the OAuth callback and create or update a user session."""
    try:
        code = request.args.get("code")
        if not code:
            return render_template("login.html", error="Authorization failed.")

        flow = get_google_oauth_flow()
        flow.oauth2session.state = session.get("oauth_state")
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials

        user_info_response = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {credentials.token}"},
            timeout=20,
        )
        user_info_response.raise_for_status()
        user_info = user_info_response.json()

        google_id = user_info["id"]
        email = user_info["email"]
        name = user_info.get("name", "")
        picture_url = user_info.get("picture", "")

        db = get_db()
        user_row = db.execute(
            "SELECT id FROM users WHERE google_id = ?",
            (google_id,),
        ).fetchone()

        if user_row:
            user_id = user_row["id"]
        else:
            user_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO users (id, google_id, email, name, picture_url, created_at) VALUES (?,?,?,?,?,?)",
                (user_id, google_id, email, name, picture_url, now_iso()),
            )
            db.commit()

        redirect_target = session.pop("post_auth_redirect", url_for("chat.chat"))
        session.clear()
        session["user_id"] = user_id
        session["username"] = name
        session["email"] = email
        session["picture_url"] = picture_url

        return redirect(redirect_target)
    except Exception as exc:
        return render_template("login.html", error=f"Authentication failed: {exc}")


@auth_bp.route("/logout")
@auth_bp.route("/auth/logout")
@require_login
def logout():
    """Log the current user out and clear session state."""
    session.clear()
    return redirect(url_for("auth.login"))
