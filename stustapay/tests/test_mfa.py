import base64

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.hashes import SHA1
from cryptography.hazmat.primitives.twofactor.totp import TOTP

from stustapay.core.mfa import decrypt_secret, encrypt_secret, match_totp, recovery_digest


def test_totp_window_format_and_replay():
    secret = base64.b32encode(b"12345678901234567890").decode()
    code = TOTP(b"12345678901234567890", 6, SHA1(), 30).generate(3000).decode()
    assert match_totp(secret, code, now=3000, last_step=-1) == 100
    assert match_totp(secret, code, now=3030, last_step=-1) == 100
    assert match_totp(secret, code, now=3060, last_step=-1) is None
    assert match_totp(secret, code, now=3000, last_step=100) is None
    assert match_totp(secret, "１２３４５６", now=3000, last_step=-1) is None
    assert match_totp(secret, "12345", now=3000, last_step=-1) is None


def test_secret_encryption_is_bound_to_user_and_key():
    encrypted = encrypt_secret("SECRET", key="server-secret", user_id=1)
    assert b"SECRET" not in encrypted
    assert decrypt_secret(encrypted, key="server-secret", user_id=1) == "SECRET"
    with pytest.raises(InvalidTag):
        decrypt_secret(encrypted, key="server-secret", user_id=2)
    with pytest.raises(InvalidTag):
        decrypt_secret(encrypted, key="different-key", user_id=1)


def test_recovery_digest_normalizes_display_format():
    assert recovery_digest("abcd-1234") == recovery_digest(" ABCD1234 ")
    assert recovery_digest("abcd-1234") != recovery_digest("abcd-1235")


async def test_enrollment_login_recovery_and_disable(user_service, event_admin_user, event_admin_token):
    import time

    from stustapay.core.mfa import totp_for_secret
    from stustapay.core.schema.mfa import MfaUpdate

    user, password = event_admin_user
    assert not (await user_service.get_mfa_status(token=event_admin_token)).enabled
    setup = await user_service.update_mfa(token=event_admin_token, payload=MfaUpdate(action="setup", password=""))
    assert setup.success and setup.secret and setup.provisioning_uri.startswith("otpauth://totp/")
    # An unfinished setup must not lock the user out.
    assert (await user_service.login_user(username=user.login, password=password)).success
    code = totp_for_secret(setup.secret).generate(time.time()).decode()
    rejected = await user_service.update_mfa(
        token=event_admin_token, payload=MfaUpdate(action="enable", password="", code=code)
    )
    assert rejected.error == "invalid_credentials"
    assert not (await user_service.get_mfa_status(token=event_admin_token)).enabled
    enabled = await user_service.update_mfa(
        token=event_admin_token, payload=MfaUpdate(action="enable", password=password, code=code)
    )
    assert enabled.success and len(enabled.recovery_codes) == 10
    assert (await user_service.get_mfa_status(token=event_admin_token)).enabled
    missing = await user_service.login_user(username=user.login, password=password)
    assert missing.mfa_required and missing.success is None
    replay = await user_service.login_user(username=user.login, password=password, mfa_code=code)
    assert replay.mfa_required and replay.success is None
    recovered = await user_service.login_user(
        username=user.login, password=password, mfa_code=enabled.recovery_codes[0]
    )
    assert recovered.success
    fresh_code = totp_for_secret(setup.secret).generate(time.time() + 30).decode()
    assert (await user_service.login_user(username=user.login, password=password, mfa_code=fresh_code)).success
    assert (await user_service.login_user(username=user.login, password=password, mfa_code=fresh_code)).success is None
    reused = await user_service.login_user(username=user.login, password=password, mfa_code=enabled.recovery_codes[0])
    assert reused.success is None
    disabled = await user_service.update_mfa(
        token=recovered.success.token,
        payload=MfaUpdate(action="disable", password=password, code=enabled.recovery_codes[1]),
    )
    assert disabled.success
    assert (await user_service.login_user(username=user.login, password=password)).success


async def test_mfa_attempt_limit_survives_requests(user_service, event_admin_user, event_admin_token):
    import time

    from stustapay.core.mfa import totp_for_secret
    from stustapay.core.schema.mfa import MfaUpdate

    user, password = event_admin_user
    setup = await user_service.update_mfa(token=event_admin_token, payload=MfaUpdate(action="setup", password=password))
    enabled = await user_service.update_mfa(
        token=event_admin_token,
        payload=MfaUpdate(
            action="enable", password=password, code=totp_for_secret(setup.secret).generate(time.time()).decode()
        ),
    )
    for _ in range(10):
        result = await user_service.login_user(username=user.login, password=password, mfa_code="invalid")
        assert result.success is None
    blocked = await user_service.login_user(username=user.login, password=password, mfa_code=enabled.recovery_codes[0])
    assert blocked.success is None and blocked.mfa_error == "rate_limited"


async def test_enrollment_expiry_and_setup_restarts_do_not_reset_limit(
    user_service, event_admin_user, event_admin_token, db_connection
):
    import time

    from stustapay.core.mfa import totp_for_secret
    from stustapay.core.schema.mfa import MfaUpdate

    user, password = event_admin_user
    setup = await user_service.update_mfa(token=event_admin_token, payload=MfaUpdate(action="setup", password=password))
    await db_connection.execute(
        "update usr_mfa set pending_since = now() - interval '11 minutes' where usr = $1", user.id
    )
    expired = await user_service.update_mfa(
        token=event_admin_token,
        payload=MfaUpdate(
            action="enable", password=password, code=totp_for_secret(setup.secret).generate(time.time()).decode()
        ),
    )
    assert expired.error == "invalid_state"
    assert not (await user_service.get_mfa_status(token=event_admin_token)).enabled
    for _ in range(9):
        await user_service.update_mfa(token=event_admin_token, payload=MfaUpdate(action="setup", password=password))
        result = await user_service.update_mfa(
            token=event_admin_token, payload=MfaUpdate(action="enable", password=password, code="invalid")
        )
        assert result.error == "invalid_code"
    await user_service.update_mfa(token=event_admin_token, payload=MfaUpdate(action="setup", password=password))
    result = await user_service.update_mfa(
        token=event_admin_token, payload=MfaUpdate(action="enable", password=password, code="invalid")
    )
    assert result.error == "rate_limited"
    await db_connection.execute(
        "update usr_mfa set attempt_window = now() - interval '16 minutes' where usr = $1", user.id
    )
    result = await user_service.update_mfa(
        token=event_admin_token, payload=MfaUpdate(action="enable", password=password, code="invalid")
    )
    assert result.error == "invalid_code"


async def test_factor_changes_revoke_sessions_and_require_both_credentials(
    user_service, event_admin_user, event_admin_token, db_connection
):
    import asyncio
    import time

    from stustapay.core.mfa import totp_for_secret
    from stustapay.core.schema.mfa import MfaUpdate

    user, password = event_admin_user
    other = await user_service.login_user(username=user.login, password=password)
    setup = await user_service.update_mfa(token=event_admin_token, payload=MfaUpdate(action="setup", password=password))
    enabled = await user_service.update_mfa(
        token=event_admin_token,
        payload=MfaUpdate(
            action="enable", password=password, code=totp_for_secret(setup.secret).generate(time.time()).decode()
        ),
    )
    assert await user_service.auth_service.get_user_from_token(token=other.success.token) is None
    assert await user_service.auth_service.get_user_from_token(token=event_admin_token) is not None
    wrong_password = await user_service.update_mfa(
        token=event_admin_token, payload=MfaUpdate(action="disable", password="wrong", code=enabled.recovery_codes[0])
    )
    assert not wrong_password.success
    wrong_code = await user_service.update_mfa(
        token=event_admin_token, payload=MfaUpdate(action="disable", password=password, code="invalid")
    )
    assert not wrong_code.success
    assert (await user_service.get_mfa_status(token=event_admin_token)).enabled
    # Racing recovery attempts can create only one session.
    results = await asyncio.gather(
        *[
            user_service.login_user(username=user.login, password=password, mfa_code=enabled.recovery_codes[0])
            for _ in range(2)
        ]
    )
    assert sum(result.success is not None for result in results) == 1
    stored = await db_connection.fetchrow("select * from usr_mfa where usr = $1", user.id)
    assert len(stored["recovery_hashes"]) == 9
    assert enabled.recovery_codes[1] not in stored["recovery_hashes"]
    assert setup.secret.encode() not in stored["secret"]
    regenerated = await user_service.update_mfa(
        token=event_admin_token,
        payload=MfaUpdate(action="regenerate", password=password, code=enabled.recovery_codes[1]),
    )
    assert regenerated.success
    stale = await user_service.login_user(username=user.login, password=password, mfa_code=enabled.recovery_codes[2])
    assert stale.success is None
    assert (
        await user_service.login_user(username=user.login, password=password, mfa_code=regenerated.recovery_codes[0])
    ).success
