"""Shared pytest fixtures for BILL4PE backend tests."""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ai-expense-hub-8.preview.emergentagent.com").rstrip("/")


def _unique_email():
    return f"test_{uuid.uuid4().hex[:10]}@bill4pe-qa.com"


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def registered_user(session):
    """Register a fresh user. Returns dict with token, user, password, email."""
    email = _unique_email()
    password = "Secret@12345"
    name = "Test User"
    r = session.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password, "name": name},
        timeout=30,
    )
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    data = r.json()
    return {
        "token": data["token"],
        "user": data["user"],
        "email": email,
        "password": password,
        "name": name,
    }


@pytest.fixture(scope="session")
def auth_headers(registered_user):
    return {
        "Authorization": f"Bearer {registered_user['token']}",
        "Content-Type": "application/json",
    }
