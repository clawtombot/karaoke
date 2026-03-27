"""Tests for queue/download presentation helpers."""

from tommyskaraoke.lib.queue_view import build_song_readiness, build_visible_queue, get_up_next_item


def test_build_visible_queue_includes_progress_for_real_queue_items():
    """Real queue items should surface a stable 100 percent download state."""
    queue = [{"file": "/songs/test.mp4", "title": "Test Song", "user": "Guest", "semitones": 0}]

    visible = build_visible_queue(
        queue,
        {"active": None, "pending": [], "errors": []},
        lambda _: {},
        lambda _: {"step": "Ready", "detail": None, "pending": False},
    )

    assert visible[0]["download"] == {"step": "Ready", "detail": None, "pending": False}


def test_build_visible_queue_appends_pending_autoqueue_downloads():
    """Auto-queued downloads should appear after the real queue with live progress."""
    visible = build_visible_queue(
        [],
        {
            "active": {
                "id": "dl-1",
                "display_title": "Fresh Download",
                "user": "Guest",
                "enqueue": True,
                "progress": 42.4,
                "status": "downloading",
            },
            "pending": [],
            "errors": [],
        },
        lambda _: {},
        lambda _: {"step": "Ready", "detail": None, "pending": False},
    )

    assert visible == [
        {
            "file": "__download__:dl-1",
            "title": "Fresh Download",
            "user": "Guest",
            "semitones": 0,
            "meta": None,
            "download": {"step": "Downloading", "detail": "42%", "pending": True},
        }
    ]


def test_get_up_next_item_prefers_real_queue_over_pending_downloads():
    """Actual queued songs should still win over not-yet-finished downloads."""
    queue = [{"file": "/songs/test.mp4", "title": "Queued Song", "user": "Guest", "semitones": 0}]
    downloads = {
        "active": {
            "id": "dl-1",
            "display_title": "Downloading Song",
            "user": "Guest",
            "enqueue": True,
            "progress": 75,
            "status": "downloading",
        },
        "pending": [],
        "errors": [],
    }

    next_item = get_up_next_item(queue, downloads, lambda _: {"step": "Ready", "detail": None, "pending": False})

    assert next_item == {
        "title": "Queued Song",
        "user": "Guest",
        "download": {"step": "Ready", "detail": None, "pending": False},
    }


def test_get_up_next_item_uses_autoqueue_download_when_queue_empty():
    """Pending auto-queued downloads become the up-next placeholder when needed."""
    next_item = get_up_next_item(
        [],
        {
            "active": None,
            "pending": [
                {
                    "id": "dl-2",
                    "display_title": "Queued Download",
                    "user": "Guest",
                    "enqueue": True,
                    "progress": 0,
                    "status": "queued",
                }
            ],
            "errors": [],
        },
        lambda _: {"step": "Ready", "detail": None, "pending": False},
    )

    assert next_item == {
        "title": "Queued Download",
        "user": "Guest",
        "download": {"step": "Queued", "detail": None, "pending": True},
    }


def test_build_song_readiness_for_separating_stems(tmp_path):
    """Stem separation should dominate readiness once the download is complete."""
    song_dir = tmp_path / "songs"
    song_dir.mkdir()
    song_path = song_dir / "test.mp4"
    song_path.write_text("video")
    stem_dir = song_dir / "stems" / "test.mp4"
    stem_dir.mkdir(parents=True)
    (stem_dir / "vocals.wav").write_text("partial")

    readiness = build_song_readiness(str(song_path), True)

    assert readiness == {"step": "Separating stems", "detail": "1/6", "pending": True}


def test_build_song_readiness_for_vocal_split_stage(tmp_path):
    """After demucs stems are ready, progress should enter the vocal split stage."""
    song_dir = tmp_path / "songs"
    song_dir.mkdir()
    song_path = song_dir / "test.mp4"
    song_path.write_text("video")
    stem_dir = song_dir / "stems" / "test.mp4"
    stem_dir.mkdir(parents=True)
    for stem in ('drums', 'bass', 'other', 'vocals', 'guitar', 'piano'):
        (stem_dir / f"{stem}.m4a").write_text("done")

    readiness = build_song_readiness(str(song_path), True)

    assert readiness == {"step": "Splitting vocals", "detail": None, "pending": True}
