"""
One-time helper: connect the LMS to a Google Calendar.

Run it on your own computer (not on Railway):

    python tools/google_calendar_setup.py

It asks for the OAuth "Desktop app" Client ID and Client secret you created
in Google Cloud, opens Google's sign-in page in your browser - sign in as the
calendar's owner (e.g. codencodemy@gmail.com) and allow access - then prints
the three values to add to the LMS service in Railway:

    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN

The access asked for is limited to creating and editing calendar events
(calendar.events). Nothing is saved to disk. Standard library only.
"""
import getpass
import http.server
import json
import secrets
import socketserver
import urllib.parse
import urllib.request
import webbrowser

SCOPE = "https://www.googleapis.com/auth/calendar.events"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def main():
    print(__doc__.split("Run it")[0].strip(), "\n")
    client_id = input("Client ID: ").strip()
    client_secret = getpass.getpass("Client secret (hidden as you type): ").strip()
    state = secrets.token_urlsafe(16)
    result = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            result.update({k: v[0] for k, v in q.items()})
            ok = "code" in q and q.get("state", [""])[0] == state
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(("<h2>Done - you can close this tab and go back to the terminal.</h2>" if ok else
                              "<h2>Something went wrong - check the terminal.</h2>").encode())

        def log_message(self, *args):
            pass

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as srv:
        redirect = f"http://127.0.0.1:{srv.server_address[1]}/"
        url = AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": client_id, "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
            "access_type": "offline", "prompt": "consent", "state": state,
        })
        print("\nOpening Google sign-in in your browser. If it doesn't open, paste this link:\n" + url + "\n")
        webbrowser.open(url)
        srv.handle_request()

    if result.get("state") != state or "code" not in result:
        raise SystemExit(f"Google did not return a code: {result.get('error', 'unknown error')}")
    body = urllib.parse.urlencode({
        "code": result["code"], "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": redirect, "grant_type": "authorization_code",
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=body, method="POST"), timeout=20) as r:
        tokens = json.loads(r.read().decode())
    refresh = tokens.get("refresh_token")
    if not refresh:
        raise SystemExit("No refresh token returned. Remove the app's access at "
                         "https://myaccount.google.com/permissions and run this again.")
    print("Connected. Add these three Variables to the codencode service in Railway:\n")
    print(f"GOOGLE_CLIENT_ID={client_id}")
    print("GOOGLE_CLIENT_SECRET=(the Client secret you just typed)")
    print(f"GOOGLE_REFRESH_TOKEN={refresh}")
    print("\nKeep the refresh token private - it lets the LMS manage this calendar's events.")


if __name__ == "__main__":
    main()
