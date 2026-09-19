from frontend.views.notification_test import (
    channel_ready,
    send_disabled,
    valid_email_destination,
    valid_sms_destination,
)


def ready_config(**overrides):
    config = {
        "mode": "live", "email_provider": "smtp", "email_live_enabled": True,
        "smtp_host_configured": True, "smtp_port_configured": True,
        "smtp_username_configured": True, "smtp_password_configured": True,
        "smtp_sender_configured": True, "sms_provider": "mock",
        "sms_delivery_mode": "mock", "sms_live_enabled": False,
        "brevo_api_key_configured": False, "brevo_sms_sender_configured": True,
    }
    config.update(overrides)
    return config


def test_destination_validation_matches_supported_inputs():
    assert valid_email_destination("admin@example.com")
    assert not valid_email_destination("not-an-email")
    assert valid_sms_destination("0917 123 4567")
    assert valid_sms_destination("+639171234567")
    assert not valid_sms_destination("9171234567")


def test_live_buttons_require_valid_destination_readiness_and_confirmation():
    config = ready_config()
    assert not send_disabled(config, "email", "admin@example.com", True)
    assert not send_disabled(config, "sms", "09171234567", False)
    assert send_disabled(config, "email", "invalid", True)
    assert send_disabled(config, "sms", "invalid", True)
    assert send_disabled(config, "email", "admin@example.com", False)
    assert not send_disabled(config, "sms", "09171234567", False)
    assert send_disabled(ready_config(email_live_enabled=False), "email", "admin@example.com", True)
    assert send_disabled(ready_config(smtp_host_configured=False), "email", "admin@example.com", True)


def test_email_and_sms_readiness_are_independent():
    no_sms = ready_config()
    assert channel_ready(no_sms, "email") and channel_ready(no_sms, "sms")
    assert not send_disabled(no_sms, "email", "admin@example.com", True)
    assert not send_disabled(no_sms, "sms", "09171234567", False)

    no_email = ready_config(smtp_password_configured=False)
    assert not channel_ready(no_email, "email")
    assert channel_ready(no_email, "sms")
    assert send_disabled(no_email, "email", "admin@example.com", True)
    assert not send_disabled(no_email, "sms", "09171234567", False)


def test_mock_mode_stays_network_free_and_does_not_require_live_confirmation():
    config = ready_config(
        mode="mock", email_provider="mock", email_live_enabled=False,
        sms_provider="mock", sms_live_enabled=False,
    )
    assert not send_disabled(config, "email", "admin@example.com", False)
    assert not send_disabled(config, "sms", "+639171234567", False)


def test_brevo_live_button_requires_only_sms_readiness_and_confirmation():
    config = ready_config(sms_provider="brevo", sms_delivery_mode="brevo",
                          sms_live_enabled=True, brevo_api_key_configured=True)
    assert not send_disabled(config, "sms", "09171234567", True)
    assert send_disabled(config, "sms", "09171234567", False)
    assert send_disabled(ready_config(**{**config, "brevo_api_key_configured": False}),
                         "sms", "09171234567", True)
    assert not send_disabled(ready_config(**{**config, "smtp_password_configured": False}),
                             "sms", "09171234567", True)
    assert not valid_sms_destination("+14155550123")
