"""Explicit, nonsecret request policy for a newly registered provider.

An absent profile preserves historical behavior. Profiles never select a model
or endpoint implicitly, and a credential is never part of this descriptor.
"""
from __future__ import annotations

from copy import deepcopy
from urllib.parse import urlsplit

PROFILE = 'responses-no-thinking-v1'


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def provider_contract(model, base_url, profile=PROFILE):
    _require(profile == PROFILE, 'Unsupported provider profile')
    _require(type(model) is str and 0 < len(model) <= 200 and model == model.strip()
             and not any(c in model for c in '\r\n'), 'Invalid provider model')
    _require(type(base_url) is str and base_url and not any(c.isspace() for c in base_url),
             'Invalid provider base URL')
    parsed = urlsplit(base_url)
    try:
        parsed.port
    except ValueError:
        raise ValueError('Invalid provider URL port') from None
    _require(parsed.scheme in ('http', 'https') and parsed.hostname
             and not parsed.username and not parsed.password and not parsed.query
             and not parsed.fragment, 'Provider URL cannot contain credentials or request parameters')
    # SDK clients commonly append a slash; descriptor bytes have one canonical form.
    base_url = base_url.rstrip('/')
    return {'schema_version': 1, 'profile': PROFILE, 'model': model, 'base_url': base_url,
            'api_mode': 'responses', 'stream': False, 'store': False,
            'chat_template_kwargs': {'enable_thinking': False}}


def validate_contract(value):
    _require(type(value) is dict, 'Provider contract must be a mapping')
    expected = provider_contract(value.get('model'), value.get('base_url'), value.get('profile'))
    _require(set(value) == set(expected)
             and type(value.get('schema_version')) is int
             and type(value.get('stream')) is bool and type(value.get('store')) is bool
             and type(value.get('chat_template_kwargs')) is dict
             and type(value['chat_template_kwargs'].get('enable_thinking')) is bool
             and value == expected, 'Provider contract differs from the registered request policy')
    return deepcopy(expected)


def matches(value, expected):
    """Validate an untrusted runtime descriptor without losing its cost receipt."""
    if expected is None:
        return value is None
    try:
        return validate_contract(value) == validate_contract(expected)
    except (ValueError, TypeError):
        return False


def contract(credentials):
    """Return explicit policy, or None for a historical unprofiled configuration."""
    _require(type(credentials) is dict, 'Provider credentials must be a mapping')
    profile = credentials.get('provider_profile')
    if profile is None:
        return None
    _require(credentials.get('api_mode', 'responses') == 'responses', 'Provider API family mismatch')
    return provider_contract(credentials.get('model'), credentials.get('base_url'), profile)


def require_config(config, credentials):
    profile = config.get('provider_profile') if isinstance(config, dict) else getattr(config, 'provider_profile', None)
    _require(profile == credentials.get('provider_profile'), 'Configured and credential provider profiles differ')
    result = contract(credentials)
    if result is not None:
        mode = config.get('hermes_transport', 'streaming') if isinstance(config, dict) else getattr(config, 'hermes_transport', 'streaming')
        _require(mode == 'nonstreaming', 'Provider profile requires nonstreaming Responses transport')
    return result


def manifest_fields(config, credentials):
    value = require_config(config, credentials)
    return {'provider_contract': value} if value is not None else {}
