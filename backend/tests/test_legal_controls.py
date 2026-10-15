"""Synthetic checks; no email, legal filing, payment or external inference."""
import pytest
from sqlalchemy import select, func
from test_accounts_courses import platform, registration_age
from account_models import Account, AccountAction, EmailOutbox
import accounts
import age_screen
import email_delivery


@pytest.mark.parametrize('band', ['under_13', '13_to_17'])
def test_minors_need_a_separate_approved_access_process(platform, band):
    client, *_ = platform
    assert client.post('/api/accounts/age-check', json={'age_band': band}).json()['eligible'] is False


def test_under13_proof_cannot_create_account_or_email(platform):
    client, factory, sent = platform
    result = client.post('/api/accounts/age-check', json={'age_band': 'under_13'})
    assert result.status_code == 200 and result.json()['eligible'] is False
    assert 'httponly' in result.headers['set-cookie'].lower()
    assert result.headers['cache-control'] == 'private, no-store'
    body = {'email': 'child@example.test', 'display_name': 'Synthetic', 'password': 'Synthetic-password-123'}
    assert client.post('/api/accounts/register', json=body).status_code == 422
    assert client.post('/api/accounts/register', json={**body, 'age_check_token': result.json()['age_check_token']}).status_code == 403
    assert sent == []
    with factory() as db:
        for model in (Account, AccountAction, EmailOutbox):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_registration_requires_valid_cookie_bound_unexpired_proof(platform, monkeypatch):
    client, factory, sent = platform
    token = registration_age(client)
    body = {'email': 'adult@example.test', 'display_name': 'Synthetic', 'password': 'Synthetic-password-123', 'age_check_token': token}
    for invalid in ('x' * 30, token[:-1] + ('0' if token[-1] != '0' else '1'), 'я' * 30):
        assert client.post('/api/accounts/register', json={**body, 'age_check_token': invalid}).status_code == 403
    client.cookies.clear()
    assert client.post('/api/accounts/register', json=body).status_code == 403
    token = registration_age(client); body['age_check_token'] = token
    timestamp = int(token.split('.')[2])
    monkeypatch.setattr(age_screen.time, 'time', lambda: timestamp + 601)
    assert client.post('/api/accounts/register', json=body).status_code == 403
    assert sent == []


def test_age_endpoint_rejects_personal_fields_and_invalid_bands(platform):
    client, *_ = platform
    for body in ({'age_band': 'invalid'}, {'birth_date': '2000-01-01'},
                 {'age_band': '18_or_over', 'email': 'not-collected@example.test'}):
        assert client.post('/api/accounts/age-check', json=body).status_code == 422


def test_email_sender_rejects_marketing_before_queue_or_transport():
    for purpose in ('marketing', 'newsletter', 'promotion', 'unknown'):
        with pytest.raises(ValueError, match='Marketing email is disabled'):
            email_delivery.enqueue_action(None, None, purpose, 'unused')
        with pytest.raises(ValueError, match='Marketing email is disabled'):
            accounts.send_action('synthetic@example.test', purpose, 'unused')
