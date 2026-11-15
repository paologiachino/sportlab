# Google sign-in: OAuth client setup

Sportlab signs people in with Google (OpenID Connect). The backend needs an OAuth client created in Google Cloud: its **client ID** and **client secret** go into `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`. This is done once, by hand, in the Google Cloud console. How the flow works in the code is described in [backend-step-2.md](backend-step-2.md).

Google's console changes often: the names below are those of the **Google Auth Platform** pages (Branding, Audience, Data access, Clients). If a label differs, look for the same setting nearby.

## Recommended layout

One Google Cloud project, **one OAuth client per environment**:

| Client name | Environment | Authorized redirect URI |
| --- | --- | --- |
| `sportlab development` | Development | `http://localhost:8000/api/auth/google/callback` |
| `sportlab staging` | Staging | `https://sportlab-staging.lacrete.casa/api/auth/google/callback` |
| `sportlab production` | Production | `https://sportlab.lacrete.casa/api/auth/google/callback` |

Why separate clients:

- The production secret never sits on a laptop: the development `.env` holds only the development secret.
- A leaked secret is revoked for one environment without touching the others.
- Each client accepts only its own redirect URI, so a code issued for development can never be sent to production, and the other way round.

The backend builds the redirect URI from `PUBLIC_URL` + `/api/auth/google/callback`, not from the request, so the reverse proxy in front of staging and production does not change it. It must match the console **exactly**: scheme, host, port, path, no trailing slash.

## 1. Project

1. Open https://console.cloud.google.com/ and sign in with the Google account that will own the project. A dedicated account (for example the one used for `ADMIN_EMAIL`) keeps the project independent of a personal address.
2. Create a project named `sportlab`. No billing account is needed for sign-in.

## 2. Branding (the consent screen)

**Google Auth Platform → Branding.**

- **App name**: `Sportlab`.
- **User support email**: shown to people on the consent screen. Use an address you are happy to show to every user, such as the dedicated one.
- **App logo**: leave empty. A logo triggers Google's brand verification, which is not needed for this app.
- **Authorized domains**: add `lacrete.casa` (staging and production redirect URIs live under it; `localhost` needs no entry).
- **Developer contact email**: an address where Google can reach you about the project; it is not shown to users.

## 3. Audience

**Google Auth Platform → Audience.**

- **User type**: **External** (any Google account; `Internal` exists only for Google Workspace organisations).
- **Publishing status**:
  - **Testing** while trying things out: only the accounts listed under **Test users** (up to 100) can sign in; others get an `access_denied` page from Google. Add your own test accounts here.
  - **In production** before family members use it. Sportlab asks only for `openid`, `email` and `profile`, which Google classes as non-sensitive, so publishing needs no review. Opening sign-in to any Google account is safe: new accounts are created as `pending` and can do nothing until an administrator approves them.

## 4. Data access (scopes)

**Google Auth Platform → Data access → Add or remove scopes**: select `openid`, `.../auth/userinfo.email` and `.../auth/userinfo.profile`, and nothing else.

The backend requests exactly these scopes (`GOOGLE_SCOPES` in `backend/app/core/google.py`). From Google it keeps only the account id (`sub`), the verified email address and the display name; it stores no Google token and never calls other Google APIs.

## 5. OAuth clients

**Google Auth Platform → Clients → Create client**, once per row of the table above:

1. **Application type**: **Web application**.
2. **Name**: for example `sportlab development`.
3. **Authorized JavaScript origins**: leave empty. The browser never talks to Google with the client ID; the whole exchange happens on the backend.
4. **Authorized redirect URIs**: the single URI of that environment, from the table.
5. **Create**, then copy the **client ID** and the **client secret** immediately into your password manager. Newer versions of the console show the secret only once; if it is lost, add a new secret to the client and delete the old one.

Changes to redirect URIs can take a few minutes to apply.

## 6. Configure the backend

### Development

In `.env` at the repository root (never committed):

```sh
ENVIRONMENT=development
PUBLIC_URL=http://localhost:8000
GOOGLE_CLIENT_ID=<client ID of "sportlab development">
GOOGLE_CLIENT_SECRET=<its secret>
ADMIN_EMAIL=<the Google address that becomes the first administrator>
```

Restart `uvicorn`: settings are read once at startup.

### Staging and production

The same variables, with that environment's client and `PUBLIC_URL` (`https://sportlab-staging.lacrete.casa` or `https://sportlab.lacrete.casa`), and `ENVIRONMENT=staging` or `production`. The values live in the environment configuration of the deploy ([sportlab-infra](https://github.com/paologiachino/sportlab-infra)), never in this repository. Outside development `PUBLIC_URL` must be `https`, and the backend logs a warning at startup when `ADMIN_EMAIL` is empty.

## 7. Try it in development

1. Start the database and the backend (see `backend/README.md`).
2. Open **http://localhost:8000/api/auth/google/login** in the browser. Use `localhost`, not `127.0.0.1`: the browser keeps cookies per host name, and the short-lived login cookie set on one name is not sent back when Google returns to the other, so the callback would fail with `400`.
3. Choose the Google account and accept. Google sends the browser back to `/api/auth/google/callback`, which opens the session and redirects to `/`. There is no frontend yet, so `/` answers `{"detail":"Not Found"}`: that is expected.
4. Open **http://localhost:8000/api/auth/me**. You should see your account:
   - the `ADMIN_EMAIL` account, on its first sign-in: `"status": "active"`, `"role": "admin"`;
   - any other account: `"status": "pending"`, `"role": "user"`, until an administrator approves it.
5. To approve someone, sign in as the administrator and call `POST /api/admin/users/{id}/approve`, for example from Bruno (see `bruno/README.md` for using the browser session there).

`ADMIN_EMAIL` counts only when the account is **created**. If that address already signed in before `ADMIN_EMAIL` was set, it stays a pending user; in development the simplest fix is to start from an empty database (`docker compose down -v`, then the migrations again).

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Google shows `Error 400: redirect_uri_mismatch` | `PUBLIC_URL` + `/api/auth/google/callback` differs from the URI registered on the client: `http` vs `https`, `localhost` vs `127.0.0.1`, port, trailing slash, or the wrong client ID for this environment. |
| `503` `Google login is not configured` | `GOOGLE_CLIENT_ID` or `GOOGLE_CLIENT_SECRET` is empty, or the backend was not restarted after editing `.env`. |
| Google shows `access_denied` / "app is being tested" | The publishing status is **Testing** and the account is not in **Test users**. |
| `400` `Google sign-in failed` at the callback | The login cookie was missing or expired (another host name, more than 10 minutes on Google's page, cookies blocked), the consent was refused, or the client secret is wrong. The backend log names the error type. |
| `403` `Google email address not verified` | The Google account has no verified email; sign-in is refused because `ADMIN_EMAIL` could otherwise be claimed by anyone. |
| `502` `Google is not reachable` | The backend could not reach Google (network, DNS, proxy). |

## Rotating a client secret

On the client page, **Add secret**, put the new secret in the environment configuration and restart the backend, then disable and delete the old secret. Rotate at once if a secret may have leaked; existing sportlab sessions are not affected, since they do not use Google tokens.
