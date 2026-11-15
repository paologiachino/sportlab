"""Shared test setup.

pytest loads this file before importing the test modules, so the synthetic
environment below is in place when `app.main` validates the settings.
Values already set (for example by CI) are kept.
"""

import os

SYNTHETIC_ENV = {
    "ENVIRONMENT": "development",
    "DATABASE_URL": "postgresql+psycopg://test_app:test@localhost:5432/sportlab_test",
    "DATABASE_MIGRATION_URL": "postgresql+psycopg://test_migrator:test@localhost:5432/sportlab_test",
    "SECRET_KEY": "test-secret-key",
    "ENCRYPTION_KEY": "test-encryption-key",
}

for name, value in SYNTHETIC_ENV.items():
    os.environ.setdefault(name, value)
