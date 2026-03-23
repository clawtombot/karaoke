"""API endpoints for song metadata: tidy names and Last.fm suggestions."""

from __future__ import annotations

from fastapi import APIRouter

from pikaraoke.lib.metadata_parser import regex_tidy, search_lastfm_tracks

router = APIRouter(tags=["metadata"])


@router.get("/metadata/tidy-name")
async def tidy_name(filename: str):
    """Apply regex-based cleanup to a song filename."""
    return {"tidied": regex_tidy(filename)}


@router.get("/metadata/suggest-names")
async def suggest_names(filename: str, limit: int = 5):
    """Search Last.fm for track suggestions matching a filename."""
    results = search_lastfm_tracks(filename, limit=limit)
    return {"suggestions": results}
