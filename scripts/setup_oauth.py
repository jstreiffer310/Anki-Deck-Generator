import os
import sys
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CREDS_PATH = PROJECT_ROOT / "credentials.json"
TOKEN_PATH = PROJECT_ROOT / "token.json"
URL_FILE = PROJECT_ROOT / "auth_url.txt"
SCOPES = ["https://www.googleapis.com/auth/documents.readonly"]

def main():
    if not CREDS_PATH.exists():
        print(f"Error: Credentials not found at {CREDS_PATH}")
        sys.exit(1)

    def prompt_hook(url):
        with open(URL_FILE, "w", encoding="utf-8") as f:
            f.write(url)
        print(f"AUTH_URL_READY: {url}", flush=True)

    class CustomFlow(InstalledAppFlow):
        def authorization_url(self, **kwargs):
            url, state = super().authorization_url(**kwargs)
            prompt_hook(url)
            return url, state

    custom_flow = CustomFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
    
    print("Starting local redirect server on port 8080...", flush=True)
    creds = custom_flow.run_local_server(
        host="localhost",
        port=8080,
        authorization_prompt_message=None,
        open_browser=False
    )

    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        f.write(creds.to_json())

    print(f"SUCCESS: token.json saved to {TOKEN_PATH}", flush=True)
    if URL_FILE.exists():
        try:
            URL_FILE.unlink()
        except Exception:
            pass

if __name__ == "__main__":
    main()
