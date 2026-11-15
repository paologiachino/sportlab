# Bruno API collection

Requests for exploring the sportlab API by hand with [Bruno](https://www.usebruno.com/) (MIT licence). The collection is plain files in the repository, in the OpenCollection YAML format (Bruno 3.0 and later), so it is reviewed in pull requests like code.

Bruno is for manual exploration. The automated API tests are the pytest suite in `backend/tests`.

## Layout

```
bruno/
  opencollection.yml      collection root (name, default environment)
  environments/
    Local.yml             baseUrl for the backend on your machine
  health/                 one folder per API router
    folder.yml
    health.yml            GET /api/health
    health-db.yml         GET /api/health/db
```

## Setup

1. Start the backend (see `backend/README.md`), for example:

   ```sh
   cd backend
   uv run uvicorn app.main:app --reload
   ```

   `GET /api/health/db` also needs a reachable PostgreSQL at `DATABASE_URL`.

2. In Bruno: **Open Collection** and choose this `bruno/` folder. Bruno reads and writes the files in place; there is no import step.
3. Select the **Local** environment (top right) if it is not already selected.
4. Open a request and send it. The status assertion shows in the **Tests** tab of the response.

## Secrets

Never write a token, password or key into these files. When authentication arrives, tokens go into environment variables marked as **secret** in Bruno: the file keeps only the variable name, and the value stays in Bruno's local encrypted store on your machine.

## Keeping the collection in sync with the API

The source of truth is the API itself: FastAPI publishes its OpenAPI specification at `/openapi.json` (and the interactive docs at `/docs`).

`backend/tests/test_bruno_collection.py` compares that specification with the requests in this folder. The test suite, and therefore CI, fails when:

- an endpoint has no request here: add one;
- a request points to an endpoint that no longer exists: update or remove it.

So every pull request that adds, renames or removes an endpoint also updates this folder.

### Adding a request

- **In Bruno:** right-click the router's folder, **New Request**, fill in method and URL as `{{baseUrl}}/api/...`, then save. Bruno writes a new `.yml` file in the folder; commit it.
- **By hand:** copy an existing request file and change `info.name`, `info.seq`, `http.method`, `http.url` and `docs`.
- Path parameters use Bruno's `:name` form (`{{baseUrl}}/api/activities/:id`); the test matches them to OpenAPI's `{id}`.
- A new router gets a new folder with its own `folder.yml`.

### Bulk refresh from OpenAPI (optional)

When many endpoints change at once, Bruno can read the specification instead of writing requests one by one:

- **OpenAPI Sync (beta, in the app):** collection `···` menu, **OpenAPI**, add the URL `http://127.0.0.1:8000/openapi.json`, **Connect**. Sync keeps scripts, tests and assertions and asks when the spec and your edits conflict. The free edition allows a limited number of syncs per month. It saves the spec under `resources/spec/`; review that folder before committing it.
- **Bruno CLI** (`@usebruno/cli`, MIT): `bru import openapi --source http://127.0.0.1:8000/openapi.json --output <empty folder> --collection-name sportlab` generates a brand new collection. It does not merge into this one, so use it in a scratch folder and copy over only the new requests.

In both cases, run `uv run pytest` afterwards: the sync test confirms that the collection matches the API.
