"""Offline regression tests. No MongoDB, real keys, payments or email delivery."""
import base64
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

os.environ['MONGO_URL'] = 'mongodb://127.0.0.1:27017'
os.environ['DB_NAME'] = 'bill4pe_offline_tests'
os.environ['JWT_SECRET'] = 'offline-test-secret-not-for-production'
for key in ('RAZORPAY_KEY_ID', 'RAZORPAY_KEY_SECRET', 'RESEND_API_KEY', 'EMERGENT_EMAIL_KEY'):
    os.environ[key] = ''

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core.security import get_current_user
from routers import bills
from services import email

USER = {'id': 'owner-1', 'name': 'Test User', 'email': '1234567890@phone.bill4pe.local'}
EXPENSE = {
    'id': 'expense-1', 'user_id': USER['id'], 'bill_generated': True,
    'bill_id': 'BILL-TEST-001', 'total': 20, 'bill_fee': 1, 'category': 'food',
    'items': [{'name': 'Roti', 'quantity': 1, 'unit_price': 20}],
    'payment': {'merchant_name': 'Test merchant', 'transaction_id': 'TX-TEST'},
}

@pytest.fixture
def setup(monkeypatch):
    expenses = SimpleNamespace(find_one=AsyncMock(return_value=dict(EXPENSE)), update_one=AsyncMock())
    monkeypatch.setattr(bills, 'db', SimpleNamespace(expenses=expenses))
    monkeypatch.setattr(bills, 'has_email', Mock(return_value=True))
    sender = AsyncMock(return_value='email-test-id')
    monkeypatch.setattr(bills, 'send_email', sender)
    app = FastAPI()
    app.include_router(bills.router, prefix='/api')
    app.dependency_overrides[get_current_user] = lambda: dict(USER)
    return TestClient(app), expenses, sender

def test_email_attaches_valid_pdf_owned_by_current_user(setup):
    client, expenses, sender = setup
    response = client.post('/api/bills/expense-1/email', json={'recipient_email': 'client@example.com', 'note': 'Thanks'})
    assert response.status_code == 200
    assert expenses.find_one.call_args.args[0] == {'id': 'expense-1', 'user_id': 'owner-1'}
    kwargs = sender.call_args.kwargs
    assert kwargs['reply_to'] is None  # phone login has no usable reply-to email
    attachment = kwargs['attachments'][0]
    assert attachment['filename'] == 'BILL-TEST-001.pdf'
    assert base64.b64decode(attachment['content']).startswith(b'%PDF-')
    assert expenses.update_one.await_count == 1

def test_missing_or_unowned_bill_is_not_emailed(setup):
    client, expenses, sender = setup
    expenses.find_one.return_value = None
    assert client.post('/api/bills/other/email', json={'recipient_email': 'client@example.com'}).status_code == 404
    sender.assert_not_awaited()

def test_pending_bill_is_not_emailed(setup):
    client, expenses, sender = setup
    expenses.find_one.return_value = {**EXPENSE, 'bill_generated': False}
    assert client.post('/api/bills/expense-1/email', json={'recipient_email': 'client@example.com'}).status_code == 400
    sender.assert_not_awaited()

def test_unconfigured_mail_is_actionable(setup, monkeypatch):
    client, _, sender = setup
    monkeypatch.setattr(bills, 'has_email', lambda **kwargs: False)
    response = client.post('/api/bills/expense-1/email', json={'recipient_email': 'client@example.com'})
    assert response.status_code == 503
    assert 'RESEND_API_KEY' in response.json()['detail']
    sender.assert_not_awaited()

def test_provider_failure_does_not_leak_details_or_mark_sent(setup):
    client, expenses, sender = setup
    sender.side_effect = RuntimeError('SECRET-provider-internals')
    response = client.post('/api/bills/expense-1/email', json={'recipient_email': 'client@example.com'})
    assert response.status_code == 502
    assert 'SECRET' not in response.text
    expenses.update_one.assert_not_awaited()

@pytest.mark.parametrize('body', [{'recipient_email': 'not-email'}, {'recipient_email': 'c@example.com', 'note': 'x' * 2001}])
def test_email_validation(setup, body):
    client, _, sender = setup
    assert client.post('/api/bills/expense-1/email', json=body).status_code == 422
    sender.assert_not_awaited()

def test_invoice_html_escapes_user_content():
    malicious = {**EXPENSE, 'items': [{'name': '<script>test</script>', 'quantity': '1', 'unit_price': 20}]}
    html = email.build_invoice_html(malicious, {'name': '<img src=x>'}, note='<b>unsafe</b>', verify_url='javascript:alert(1)')
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert '<b>unsafe</b>' not in html and '&lt;b&gt;' in html
    assert 'javascript:' not in html

def test_proxy_alone_cannot_claim_pdf_email_support(monkeypatch):
    monkeypatch.setattr(email, 'RESEND_API_KEY', '')
    monkeypatch.setattr(email, 'EMERGENT_EMAIL_KEY', 'fake-proxy')
    assert email.has_email()
    assert not email.has_email(attachments=True)

def test_resend_receives_the_attachment_without_network(monkeypatch):
    import asyncio
    import resend
    monkeypatch.setattr(email, 'RESEND_API_KEY', 'fake-test-only')
    send = Mock(return_value={'id': 'offline-email'})
    monkeypatch.setattr(resend.Emails, 'send', send)
    attachment = {'filename': 'test.pdf', 'content': base64.b64encode(b'%PDF-test').decode()}
    assert asyncio.run(email.send_email('client@example.com', 'Test', '<p>Test</p>', attachments=[attachment])) == 'offline-email'
    assert send.call_args.args[0]['attachments'] == [attachment]
