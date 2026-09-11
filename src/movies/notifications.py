"""Notification helpers for movie comments.

Mirrors `src.accounts.notifications`: synchronous now (logs / sends via
`send_email`), can be swapped for a Celery-dispatched task later without
changing call sites.
"""

from src.accounts.notifications import send_email


def send_comment_reply_email(
    to_email: str, movie_name: str, reply_text: str
) -> None:
    send_email(
        to=to_email,
        subject=f"New reply to your comment on {movie_name}",
        body=f'Someone replied to your comment: "{reply_text}"',
    )


def send_comment_like_email(to_email: str, movie_name: str) -> None:
    send_email(
        to=to_email,
        subject=f"Your comment on {movie_name} got a like",
        body="Someone liked your comment.",
    )
