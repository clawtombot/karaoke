# Stem splitter: the 6 stems produced by htdemucs_6s
STEM_NAMES = ("drums", "bass", "other", "vocals", "guitar", "piano")
STEMS_SUBDIR = "stems"

# Second-pass vocal split: lead vs backing vocals
VOCAL_SPLIT_STEMS = ("lead_vocals", "backing_vocals")

# All stems exposed to the frontend (replaces "vocals" with lead/backing when available)
ALL_STEM_NAMES = ("drums", "bass", "other", "lead_vocals", "backing_vocals", "guitar", "piano")

# Model config for vocal split second pass.
# swap=True means the model's primary output is backing vocals (BVE extracts backing).
# swap=False means the model's primary output is lead vocals (karaoke models extract lead).
VOCAL_SPLIT_MODELS = {
    "UVR-BVE-4B_SN-44100-1.pth": {
        "swap": True,
        "label": "BVE v1 (20s)",
        "description": "Cleaner lead vocal isolation for practice mixes.",
    },
    "5_HP-Karaoke-UVR.pth": {
        "swap": False,
        "label": "HP5 Karaoke (21s)",
        "description": "Balanced karaoke split with solid instrumental recovery.",
    },
    "6_HP-Karaoke-UVR.pth": {
        "swap": False,
        "label": "HP6 Karaoke (27s)",
        "description": "More aggressive karaoke split for harder vocal removal cases.",
    },
}

SEPARATION_BACKENDS = {
    "demucs": {
        "label": "Demucs",
        "description": "Portable CPU/CUDA backend for Linux, Windows, and general hosting.",
        "devices": ("cpu", "cuda"),
    },
    "mlx": {
        "label": "Demucs MLX",
        "description": "Apple Silicon backend using MLX for fast local separation on macOS.",
        "devices": (),
    },
}

SEPARATION_DEVICE_OPTIONS = {
    "cpu": {
        "label": "CPU",
        "description": "Most compatible, slower than GPU acceleration.",
    },
    "cuda": {
        "label": "NVIDIA CUDA",
        "description": "Best option for systems like an RTX 4070 host.",
    },
}

SEPARATION_MODELS = {
    "htdemucs_6s": {
        "label": "HT Demucs 6 Stem",
        "description": "Vocals, drums, bass, other, guitar, and piano in one pass.",
        "backends": ("demucs", "mlx"),
    },
}


def get_stem_separation_options() -> dict[str, list[dict[str, str]] | dict[str, list[dict[str, str]]]]:
    """Return user-facing option metadata for the Settings UI."""
    return {
        "backends": [
            {
                "value": backend,
                "label": meta["label"],
                "description": meta["description"],
            }
            for backend, meta in SEPARATION_BACKENDS.items()
        ],
        "devices": {
            backend: [
                {
                    "value": device,
                    "label": SEPARATION_DEVICE_OPTIONS[device]["label"],
                    "description": SEPARATION_DEVICE_OPTIONS[device]["description"],
                }
                for device in meta["devices"]
            ]
            for backend, meta in SEPARATION_BACKENDS.items()
        },
        "models": [
            {
                "value": model,
                "label": meta["label"],
                "description": meta["description"],
            }
            for model, meta in SEPARATION_MODELS.items()
        ],
        "vocal_models": [
            {
                "value": model,
                "label": meta["label"],
                "description": meta["description"],
            }
            for model, meta in VOCAL_SPLIT_MODELS.items()
        ],
    }


def stems_complete(stem_dir: str) -> bool:
    """Return True if all stems (demucs + vocal split) are ready."""
    import os

    demucs_ok = all(
        os.path.isfile(os.path.join(stem_dir, f"{s}.m4a"))
        for s in STEM_NAMES
    )
    vocal_split_ok = all(
        os.path.isfile(os.path.join(stem_dir, f"{s}.m4a"))
        for s in VOCAL_SPLIT_STEMS
    )
    return demucs_ok and vocal_split_ok


def demucs_complete(stem_dir: str) -> bool:
    """Return True if all 6 demucs stems exist."""
    import os

    return all(
        os.path.isfile(os.path.join(stem_dir, f"{s}.m4a"))
        for s in STEM_NAMES
    )


LANGUAGES = {
    "en": "English",
    "de_DE": "German",
    "es_VE": "Spanish (Venezuela)",
    "fi_FI": "Finnish",
    "fr_FR": "French",
    "id_ID": "Indonesian",
    "it_IT": "Italian",
    "ja_JP": "Japanese",
    "ko_KR": "Korean",
    "nl_NL": "Dutch",
    "no_NO": "Norwegian",
    "pt_BR": "Brazilian Portuguese",
    "ru_RU": "Russian",
    "th_TH": "Thai",
    "zh_Hans_CN": "Chinese (Simplified)",
    "zh_Hant_TW": "Chinese (Traditional)",
}
