"""Flask application context utilities for PiKaraoke."""

import logging
from typing import Any

from flask import current_app, request
from flask_socketio import emit

from pikaraoke.karaoke import Karaoke


def is_admin() -> bool:
    """Determine if the current app's admin password matches the admin cookie value
    This function checks if the provided password is `None` or if it matches
    the value of the "admin" cookie in the current Flask request. If the password
    is `None`, the function assumes the user is an admin. If the "admin" cookie
    is present and its value matches the provided password, the function returns `True`.
    Otherwise, it returns `False`.
    Returns:
        bool: `True` if the password matches the admin cookie or if the password is `None`,
              `False` otherwise.
    """
    password = get_admin_password()
    return password is None or request.cookies.get("admin") == password


def get_karaoke_instance() -> Karaoke:
    """Get the current app's Karaoke instance
    This function returns the Karaoke instance stored in the current app's configuration.
    Returns:
        Karaoke: The Karaoke instance stored in the current app's configuration.
    """
    return current_app.config["KARAOKE_INSTANCE"]


def get_admin_password() -> str:
    """Get the admin password from the current app's configuration
    This function returns the admin password stored in the current app's configuration.
    Returns:
        str: The admin password stored in the current app's configuration.
    """
    return current_app.config["ADMIN_PASSWORD"]


def get_site_name() -> str:
    """Get the site name from the current app's configuration
    This function returns the site name stored in the current app's configuration.
    Returns:
        str: The site name stored in the current app's configuration.
    """
    return current_app.config["SITE_NAME"]


def broadcast_event(event: str, data: Any = None) -> None:
    """Broadcast a SocketIO event to all connected clients.

    Args:
        event: Name of the event to broadcast.
        data: Optional data payload to send with the event.
    """
    logging.debug("Broadcasting event: " + event)
    emit(event, data, namespace="/", broadcast=True)


