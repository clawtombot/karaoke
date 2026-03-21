# Stem splitter: the 6 stems produced by htdemucs_6s
STEM_NAMES = ("drums", "bass", "other", "vocals", "guitar", "piano")
STEMS_SUBDIR = "stems"


def stems_complete(stem_dir: str) -> bool:
    """Return True if all stem M4A files exist in stem_dir."""
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
