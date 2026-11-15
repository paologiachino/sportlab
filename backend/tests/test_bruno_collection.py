"""The Bruno collection in `bruno/` must match the API published in OpenAPI.

Every endpoint needs a request, and no request may point to a removed endpoint,
so the collection cannot silently drift from the code (see bruno/README.md).
"""

import re
from pathlib import Path

import yaml

from app.main import app

BRUNO_DIR = Path(__file__).resolve().parents[2] / "bruno"
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
# Collection files that are not requests
NOT_REQUESTS = {"opencollection.yml", "folder.yml"}
# Folders that hold no requests: environments, and the spec saved by OpenAPI Sync
NOT_REQUEST_DIRS = {"environments", "resources"}

Operation = tuple[str, str]


def openapi_operations() -> set[Operation]:
    return {
        (method.upper(), path)
        for path, item in app.openapi()["paths"].items()
        for method in item
        if method in HTTP_METHODS
    }


def bruno_operations() -> set[Operation]:
    operations = set()
    for file in BRUNO_DIR.rglob("*.yml"):
        relative = file.relative_to(BRUNO_DIR)
        if file.name in NOT_REQUESTS or NOT_REQUEST_DIRS & set(relative.parts):
            continue
        http = yaml.safe_load(file.read_text(encoding="utf-8"))["http"]
        path = http["url"].removeprefix("{{baseUrl}}").split("?")[0]
        # Bruno path parameters (/activities/:id) match OpenAPI ones (/activities/{id})
        path = re.sub(r":(\w+)", r"{\1}", path)
        operations.add((http["method"].upper(), path))
    return operations


def test_collection_exists() -> None:
    assert (BRUNO_DIR / "opencollection.yml").is_file()


def test_every_endpoint_has_a_bruno_request() -> None:
    missing = openapi_operations() - bruno_operations()

    assert not missing, f"Add a request in bruno/ for: {sorted(missing)}"


def test_no_bruno_request_for_removed_endpoints() -> None:
    stale = bruno_operations() - openapi_operations()

    assert not stale, f"Remove or update the requests in bruno/ for: {sorted(stale)}"
