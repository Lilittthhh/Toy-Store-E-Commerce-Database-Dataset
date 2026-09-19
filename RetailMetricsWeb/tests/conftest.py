"""Automated tests must never spend provider quota or send live notifications."""

import os


def pytest_configure():
    os.environ["NOTIFICATION_MODE"] = "mock"
    os.environ["SMTP_LIVE_SEND_ENABLED"] = "false"
    os.environ["SMS_LIVE_SEND_ENABLED"] = "false"
    os.environ["BREVO_SMS_LIVE_SEND_ENABLED"] = "false"
    os.environ["INFOBIP_LIVE_SEND_ENABLED"] = "false"
