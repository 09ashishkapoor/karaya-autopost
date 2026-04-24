import argparse
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request


AUTHORIZATION_URL = "https://www.tumblr.com/oauth2/authorize"
TOKEN_URL = "https://api.tumblr.com/v2/oauth2/token"
DEFAULT_SCOPE = "write offline_access"
DEFAULT_USER_AGENT = "karaya-autopost-tumblr/1.0"


def request_form(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": os.environ.get("TUMBLR_USER_AGENT", DEFAULT_USER_AGENT),
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Tumblr token request failed with HTTP {exc.code}: {details}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error while calling Tumblr API: {exc.reason}") from exc

    return json.loads(raw)


def get_required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def build_authorization_url(client_id: str, redirect_uri: str, scope: str, state: str) -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "scope": scope,
            "state": state,
            "redirect_uri": redirect_uri,
        }
    )
    return f"{AUTHORIZATION_URL}?{query}"


def exchange_code(code: str, redirect_uri: str) -> dict:
    client_id = get_required_env("TUMBLR_CLIENT_ID")
    client_secret = get_required_env("TUMBLR_CLIENT_SECRET")
    return request_form(
        TOKEN_URL,
        {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        },
    )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Helper for Tumblr OAuth2 authorization code flow.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    authorize = subparsers.add_parser("authorize", help="Print the Tumblr authorization URL.")
    authorize.add_argument("--state", default="", help="Optional state value. Defaults to a generated random value.")
    authorize.add_argument("--scope", default=DEFAULT_SCOPE, help="OAuth scope string.")
    authorize.add_argument("--redirect-uri", default="", help="Override TUMBLR_REDIRECT_URI for this run.")

    exchange = subparsers.add_parser("exchange", help="Exchange an authorization code for tokens.")
    exchange.add_argument("--code", required=True, help="Authorization code returned by Tumblr.")
    exchange.add_argument("--redirect-uri", default="", help="Override TUMBLR_REDIRECT_URI for this run.")

    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    redirect_uri = (args.redirect_uri or os.environ.get("TUMBLR_REDIRECT_URI", "")).strip()
    if not redirect_uri:
        raise RuntimeError("Missing redirect URI. Set TUMBLR_REDIRECT_URI or pass --redirect-uri.")

    if args.command == "authorize":
        client_id = get_required_env("TUMBLR_CLIENT_ID")
        state = args.state.strip() or secrets.token_urlsafe(24)
        url = build_authorization_url(client_id, redirect_uri, args.scope.strip(), state)
        print("Authorization URL:")
        print(url)
        print()
        print("State:")
        print(state)
        print()
        print("After approval, copy the code query parameter from the redirect URL and run:")
        print(f"python tumblr_oauth_helper.py exchange --code YOUR_CODE --redirect-uri {redirect_uri}")
        return

    token_response = exchange_code(args.code.strip(), redirect_uri)
    print(json.dumps(token_response, indent=2, ensure_ascii=False))
    print()
    refresh_token = token_response.get("refresh_token")
    if refresh_token:
        print("GitHub secret to set:")
        print(f"TUMBLR_REFRESH_TOKEN={refresh_token}")


if __name__ == "__main__":
    main()
