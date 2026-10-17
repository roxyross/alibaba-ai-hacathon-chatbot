"""Centralized, typed startup and runtime configuration validator for Roxy-AI billing.

Enforces production mode safety:
- Detects incompatible environment + credential pairings (e.g., prod + test keys).
- Detects sandbox flags enabled in production environments.
- Enforces durable PostgreSQL persistence when billing is active in production.
- Validates webhook verification secret presence for enabled providers.
- NEVER exposes secret keys or credential values in error messages or logs.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field


class BillingConfigurationError(ValueError):
    """Raised when an unsafe or contradictory billing configuration is detected."""
    pass


@dataclass
class BillingValidationReport:
    """Detailed summary of billing configuration checks."""
    is_production: bool
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    active_providers: list[str] = field(default_factory=list)


class BillingConfigValidator:
    """Validates payment gateway settings and environment configurations safely."""

    @classmethod
    def validate(cls, env: Mapping[str, str] | None = None) -> BillingValidationReport:
        """Validate billing configuration against environment variables.

        Args:
            env: Optional dictionary of environment variables. If None, os.environ is used.

        Returns:
            BillingValidationReport with validation findings.

        Raises:
            BillingConfigurationError: If in production and critical safety violations exist.
        """
        source = env if env is not None else os.environ

        app_env = source.get("APP_ENV", "").lower()
        env_var = source.get("ENV", "").lower()
        environment = source.get("ENVIRONMENT", "").lower()

        is_prod = (
            app_env in ("production", "prod")
            or env_var in ("production", "prod")
            or environment in ("production", "prod")
            or bool(source.get("VERCEL"))
            or bool(source.get("VERCEL_ENV") in ("production", "prod"))
            or bool(source.get("K_SERVICE"))
        )

        errors: list[str] = []
        warnings: list[str] = []
        active_providers: list[str] = []

        stripe_key = source.get("STRIPE_SECRET_KEY", "").strip()
        stripe_webhook_secret = source.get("STRIPE_WEBHOOK_SECRET", "").strip()
        safepay_key = source.get("SAFEPAY_API_KEY", "").strip()
        safepay_env = source.get("SAFEPAY_ENVIRONMENT", "").lower().strip()
        safepay_webhook_secret = source.get("SAFEPAY_WEBHOOK_SECRET", "").strip()
        db_url = source.get("DATABASE_URL", "").strip()
        sim_checkout = source.get("BILLING_SIMULATE_CHECKOUT", "").lower().strip() in ("1", "true", "yes")

        # Provider identification
        if stripe_key:
            active_providers.append("stripe")
        if safepay_key:
            active_providers.append("safepay")

        # 1. Production + Test credentials validation
        if is_prod:
            if stripe_key.startswith("sk_test_") or stripe_key.startswith("test_"):
                errors.append(
                    "CRITICAL_CONFIGURATION_ERROR: Stripe test-mode secret key detected in production environment. "
                    "Production must use a valid live secret key or leave billing unconfigured."
                )

            if safepay_key.startswith("sec_test_") or safepay_key.startswith("test_"):
                errors.append(
                    "CRITICAL_CONFIGURATION_ERROR: Safepay sandbox API key detected in production environment. "
                    "Production must use live merchant credentials."
                )

            # 2. Production + Safepay sandbox mode
            if safepay_env == "sandbox":
                errors.append(
                    "CRITICAL_CONFIGURATION_ERROR: SAFEPAY_ENVIRONMENT is set to 'sandbox' in production. "
                    "Must be set to 'production' or unset for live payments."
                )

            # 3. Production + Simulated checkout mode
            if sim_checkout:
                errors.append(
                    "CRITICAL_CONFIGURATION_ERROR: BILLING_SIMULATE_CHECKOUT is enabled in production. "
                    "Simulated transactions are strictly prohibited in production mode."
                )

            # 4. Production billing + Missing durable PostgreSQL database
            if active_providers and (not db_url or "sqlite" in db_url.lower()):
                errors.append(
                    "CRITICAL_CONFIGURATION_ERROR: Active payment providers configured in production without a "
                    "durable PostgreSQL DATABASE_URL. Financial state cannot rely on ephemeral storage."
                )

            # 5. Live webhook handling + Missing verification secret
            if stripe_key and not stripe_webhook_secret:
                errors.append(
                    "CRITICAL_CONFIGURATION_ERROR: Stripe is configured in production, but STRIPE_WEBHOOK_SECRET "
                    "is missing. Webhook signatures cannot be verified."
                )

            if safepay_key and not safepay_webhook_secret:
                errors.append(
                    "CRITICAL_CONFIGURATION_ERROR: Safepay is configured in production, but SAFEPAY_WEBHOOK_SECRET "
                    "is missing. Webhook HMAC signatures cannot be verified."
                )
        else:
            # Development / Testing warnings
            if not db_url:
                warnings.append("DATABASE_URL is not set; billing operations will use in-memory simulation.")
            if not stripe_key and not safepay_key:
                warnings.append("No payment gateway credentials configured; simulated checkouts permitted.")

        is_valid = len(errors) == 0

        report = BillingValidationReport(
            is_production=is_prod,
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            active_providers=active_providers,
        )

        if not is_valid and is_prod:
            raise BillingConfigurationError("\n".join(errors))

        return report


def validate_billing_configuration(env: Mapping[str, str] | None = None) -> BillingValidationReport:
    """Convenience helper to run BillingConfigValidator.validate()."""
    return BillingConfigValidator.validate(env)
