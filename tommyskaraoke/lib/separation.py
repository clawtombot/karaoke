"""Separation backend configuration and model cache helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass

from tommyskaraoke.constants import VOCAL_SPLIT_MODELS

SUPPORTED_SEPARATION_BACKENDS = ('demucs', 'mlx')
SUPPORTED_DEMUCS_DEVICES = ('cpu', 'cuda')
SUPPORTED_SEPARATION_MODELS = ('htdemucs_6s',)


@dataclass(frozen=True)
class SeparationConfig:
    """Validated configuration for stem separation."""

    backend: str
    model: str
    vocal_split_model: str
    device: str | None = None
    model_cache_dir: str | None = None


def parse_bool_env(name: str) -> bool | None:
    """Parse a boolean environment variable, returning None when unset."""
    raw = os.environ.get(name)
    if raw is None:
        return None

    value = raw.strip().lower()
    if value in {'1', 'true', 'yes', 'on'}:
        return True
    if value in {'0', 'false', 'no', 'off'}:
        return False

    raise ValueError(
        f'{name} must be one of: 1, 0, true, false, yes, no, on, off. Got: {raw}'
    )


def env_or_none(name: str) -> str | None:
    """Return an environment variable value, treating blank strings as missing."""
    value = os.environ.get(name)
    if value is None:
        return None

    stripped = value.strip()
    return stripped or None


def build_model_cache_env(model_cache_dir: str | None) -> dict[str, str]:
    """Return environment variables that pin model downloads outside the repo."""
    if not model_cache_dir:
        return {}

    base_dir = os.path.abspath(os.path.expanduser(model_cache_dir))
    return {
        'HF_HOME': os.path.join(base_dir, 'huggingface'),
        'TORCH_HOME': os.path.join(base_dir, 'torch'),
        'XDG_CACHE_HOME': base_dir,
    }


def apply_model_cache_env(model_cache_dir: str | None) -> dict[str, str]:
    """Apply cache env vars to the current process and return them."""
    env = build_model_cache_env(model_cache_dir)
    for key, value in env.items():
        os.environ[key] = value
    return env


def resolve_separation_config(
    *,
    enabled: bool,
    backend: str | None,
    model: str | None,
    vocal_split_model: str | None,
    device: str | None,
    model_cache_dir: str | None,
) -> SeparationConfig | None:
    """Validate separation config and normalize values for runtime use."""
    if not enabled:
        return None

    missing = []
    if not backend:
        missing.append('separation_backend')
    if not model:
        missing.append('separation_model')
    if not vocal_split_model:
        missing.append('vocal_split_model')
    if missing:
        raise ValueError(
            'Stem splitter is enabled but missing required configuration: '
            + ', '.join(missing)
        )

    normalized_backend = backend.lower()
    if normalized_backend not in SUPPORTED_SEPARATION_BACKENDS:
        raise ValueError(
            f'Unsupported separation backend: {backend}. '
            f'Expected one of: {", ".join(SUPPORTED_SEPARATION_BACKENDS)}'
        )

    normalized_model = model.strip()
    if normalized_model not in SUPPORTED_SEPARATION_MODELS:
        raise ValueError(
            f'Unsupported separation model: {model}. '
            f'Expected one of: {", ".join(SUPPORTED_SEPARATION_MODELS)}'
        )

    normalized_vocal_split_model = vocal_split_model.strip()
    if normalized_vocal_split_model not in VOCAL_SPLIT_MODELS:
        raise ValueError(
            'Unsupported vocal split model: '
            f'{vocal_split_model}. Expected one of: {", ".join(VOCAL_SPLIT_MODELS)}'
        )

    normalized_device = None
    if normalized_backend == 'demucs':
        if not device:
            raise ValueError(
                'Stem splitter backend "demucs" requires separation_device to be set '
                '(cpu or cuda).'
            )
        normalized_device = device.lower()
        if normalized_device not in SUPPORTED_DEMUCS_DEVICES:
            raise ValueError(
                f'Unsupported demucs device: {device}. '
                f'Expected one of: {", ".join(SUPPORTED_DEMUCS_DEVICES)}'
            )
    elif device:
        lowered_device = device.lower()
        if lowered_device not in {'mps', 'mlx'}:
            raise ValueError(
                'Stem splitter backend "mlx" does not use separation_device. '
                'Omit it, or set it to mps/mlx for clarity.'
            )

    normalized_model_cache_dir = None
    if model_cache_dir:
        normalized_model_cache_dir = os.path.abspath(os.path.expanduser(model_cache_dir))

    return SeparationConfig(
        backend=normalized_backend,
        model=normalized_model,
        vocal_split_model=normalized_vocal_split_model,
        device=normalized_device,
        model_cache_dir=normalized_model_cache_dir,
    )
