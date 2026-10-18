"""Comprehensive tests for centralized billing configuration validator.

Verifies:
- Detection of incompatible environment + credential pairings (e.g., prod + test keys).
- Detection of sandbox flags enabled in production environments.
- Enforcement of durable PostgreSQL persistence when billing is active in production.
- Validation of webhook verification secret presence for enabled providers.
- Strict non-exposure of secret keys or credential values in error messages.
"""

from __future__ import annotations

import pytest

from app.billing.validator import (
    BillingConfigurationError,
    BillingConfigValidator,
    validate_billing_configuration,
)


def test_production_rejects_stripe_test_secret_key() -> None:
    """Production mode must reject Stripe sk_test_... secret keys."""
    env = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+asyncpg://user:pwd@db.host:5432/roxy_prod",
        "STRIPE_SECRET_KEY": "sk_test_synthetic_test_secret_key_12345",
        "STRIPE_WEBHOOK_SECRET": "whsec_synthetic_webhook_secret_67890",
    }
    with pytest.raises(BillingConfigurationError) as exc_info:
        BillingConfigValidator.validate(env)

    err_msg = str(exc_info.value)
    assert "Stripe test-mode secret key detected in production" in err_msg
    # Strict secret non-exposure verification
    assert "sk_test_synthetic" not in err_msg
    assert "12345" not in err_msg


def test_production_rejects_safepay_sandbox_api_key() -> None:
    """Production mode must reject Safepay sec_test_... sandbox keys."""
    env = {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql+asyncpg://user:pwd@db.host:5432/roxy_prod",
        "SAFEPAY_API_KEY": "sec_test_synthetic_safepay_key_99999",
        "SAFEPAY_WEBHOOK_SECRET": "synthetic_secret_safe",
    }
    with pytest.raises(BillingConfigurationError) as exc_info:
        BillingConfigValidator.validate(env)

    err_msg = str(exc_info.value)
    assert "Safepay sandbox API key detected in production" in err_msg
    assert "sec_test_synthetic" not in err_msg


def test_production_rejects_safepay_sandbox_environment() -> None:
    """Production mode must reject SAFEPAY_ENVIRONMENT='sandbox'."""
    env = {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql+asyncpg://user:pwd@db.host:5432/roxy_prod",
        "SAFEPAY_API_KEY": "sec_live_synthetic_valid_format_key",
        "SAFEPAY_ENVIRONMENT": "sandbox",
        "SAFEPAY_WEBHOOK_SECRET": "synthetic_secret_safe",
    }
    with pytest.raises(BillingConfigurationError) as exc_info:
        BillingConfigValidator.validate(env)

    err_msg = str(exc_info.value)
    assert "SAFEPAY_ENVIRONMENT is set to 'sandbox' in production" in err_msg


def test_production_rejects_simulated_checkout() -> None:
    """Production mode must reject simulated checkout flag."""
    env = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+asyncpg://user:pwd@db.host:5432/roxy_prod",
        "BILLING_SIMULATE_CHECKOUT": "true",
    }
    with pytest.raises(BillingConfigurationError) as exc_info:
        BillingConfigValidator.validate(env)

    err_msg = str(exc_info.value)
    assert "BILLING_SIMULATE_CHECKOUT is enabled in production" in err_msg


def test_production_billing_requires_durable_database() -> None:
    """Active payment gateway in production requires PostgreSQL DATABASE_URL."""
    env = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "",
        "STRIPE_SECRET_KEY": "sk_live_synthetic_valid_format_stripe_key",
        "STRIPE_WEBHOOK_SECRET": "whsec_synthetic_valid_stripe_secret",
    }
    with pytest.raises(BillingConfigurationError) as exc_info:
        BillingConfigValidator.validate(env)

    err_msg = str(exc_info.value)
    assert "Active payment providers configured in production without a durable PostgreSQL" in err_msg


def test_production_requires_webhook_secret_for_enabled_providers() -> None:
    """Configuring payment provider in production without webhook secret fails closed."""
    # Stripe configured without webhook secret
    env_stripe = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+asyncpg://user:pwd@db.host:5432/roxy_prod",
        "STRIPE_SECRET_KEY": "sk_live_synthetic_valid_format_stripe_key",
        "STRIPE_WEBHOOK_SECRET": "",
    }
    with pytest.raises(BillingConfigurationError) as exc_info:
        BillingConfigValidator.validate(env_stripe)
    assert "STRIPE_WEBHOOK_SECRET is missing" in str(exc_info.value)

    # Safepay configured without webhook secret
    env_safepay = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+asyncpg://user:pwd@db.host:5432/roxy_prod",
        "SAFEPAY_API_KEY": "sec_live_synthetic_valid_format_safepay_key",
        "SAFEPAY_WEBHOOK_SECRET": "",
    }
    with pytest.raises(BillingConfigurationError) as exc_info2:
        BillingConfigValidator.validate(env_safepay)
    assert "SAFEPAY_WEBHOOK_SECRET is missing" in str(exc_info2.value)


def test_non_production_simulation_permitted() -> None:
    """In development/test mode, simulated checkouts and missing keys are allowed with warnings."""
    dev_env = {
        "APP_ENV": "development",
        "DATABASE_URL": "",
        "BILLING_SIMULATE_CHECKOUT": "true",
    }
    report = validate_billing_configuration(dev_env)
    assert not report.is_production
    assert report.is_valid
    assert len(report.errors) == 0
    assert any("DATABASE_URL is not set" in w for w in report.warnings)


def test_valid_production_configuration_passes() -> None:
    """Valid production configuration passes validation."""
    valid_prod_env = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+asyncpg://user:pwd@db.prod.internal:5432/roxy_prod",
        "STRIPE_SECRET_KEY": "sk_live_synthetic_valid_format_key",
        "STRIPE_WEBHOOK_SECRET": "whsec_synthetic_valid_webhook_secret",
        "SAFEPAY_API_KEY": "sec_live_synthetic_valid_format_key",
        "SAFEPAY_ENVIRONMENT": "production",
        "SAFEPAY_WEBHOOK_SECRET": "synthetic_valid_safepay_secret",
    }
    report = BillingConfigValidator.validate(valid_prod_env)
    assert report.is_production
    assert report.is_valid
    assert len(report.errors) == 0
    assert "stripe" in report.active_providers
    assert "safepay" in report.active_providers


def test_production_rejects_nayapay_sandbox_credentials() -> None:
    """Production mode must reject NayaPay test credentials and sandbox environment."""
    env = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+asyncpg://user:pwd@db.prod.internal:5432/roxy_prod",
        "NAYAPAY_ENABLED": "true",
        "NAYAPAY_ENVIRONMENT": "sandbox",
        "NAYAPAY_SECRET_KEY": "np_secret_test_key_123",
        "NAYAPAY_WEBHOOK_SECRET": "sec_123",
    }
    with pytest.raises(BillingConfigurationError) as exc_info:
        BillingConfigValidator.validate(env)
    err = str(exc_info.value)
    assert "NAYAPAY_ENVIRONMENT is set to 'sandbox'" in err
    assert "np_secret_test" not in err  # No secrets leaked


def test_production_rejects_sadapay_sandbox_credentials() -> None:
    """Production mode must reject SadaPay test credentials and sandbox environment."""
    env = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+asyncpg://user:pwd@db.prod.internal:5432/roxy_prod",
        "SADAPAY_ENABLED": "true",
        "SADAPAY_ENVIRONMENT": "sandbox",
        "SADAPAY_API_KEY": "sp_api_test_key_456",
        "SADAPAY_WEBHOOK_SECRET": "sec_456",
    }
    with pytest.raises(BillingConfigurationError) as exc_info:
        BillingConfigValidator.validate(env)
    err = str(exc_info.value)
    assert "SADAPAY_ENVIRONMENT is set to 'sandbox'" in err
    assert "sp_api_test" not in err  # No secrets leaked


def test_production_requires_webhook_secret_for_enabled_nayapay_sadapay() -> None:
    """Enabled NayaPay and SadaPay in production require webhook secrets."""
    env_np = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+asyncpg://user:pwd@db.prod.internal:5432/roxy_prod",
        "NAYAPAY_ENABLED": "true",
        "NAYAPAY_ENVIRONMENT": "production",
        "NAYAPAY_SECRET_KEY": "live_np_sec_key_xyz",
        "NAYAPAY_WEBHOOK_SECRET": "",
    }
    with pytest.raises(BillingConfigurationError) as exc_np:
        BillingConfigValidator.validate(env_np)
    assert "NAYAPAY_WEBHOOK_SECRET is missing" in str(exc_np.value)

    env_sp = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+asyncpg://user:pwd@db.prod.internal:5432/roxy_prod",
        "SADAPAY_ENABLED": "true",
        "SADAPAY_ENVIRONMENT": "production",
        "SADAPAY_API_KEY": "live_sp_api_key_xyz",
        "SADAPAY_WEBHOOK_SECRET": "",
    }
    with pytest.raises(BillingConfigurationError) as exc_sp:
        BillingConfigValidator.validate(env_sp)
    assert "SADAPAY_WEBHOOK_SECRET is missing" in str(exc_sp.value)
