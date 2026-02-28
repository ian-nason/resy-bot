import logging
import threading
from typing import List

from resy_bot.models import ResyConfig, WatchlistEntry, Watchlist
from resy_bot.manager import ResyManager
from resy_bot.notifications import notify_booking_result

logger = logging.getLogger(__name__)


def _run_single_venue(
    manager: ResyManager,
    entry: WatchlistEntry,
    config: ResyConfig,
) -> None:
    venue_label = entry.name or f"venue {entry.reservation_request.venue_id}"
    logger.info(f"[{venue_label}] Thread started, waiting for drop time")

    timed_request = entry.to_timed_request()

    try:
        resy_token = manager.make_reservation_at_opening_time(timed_request)
        logger.info(f"[{venue_label}] Booking successful! Token: {resy_token}")

        notify_booking_result(
            success=True,
            details=(
                f"Booking confirmed for {venue_label}!\n\n"
                f"Resy token: {resy_token}\n\n"
                f"Reservation details:\n"
                f"  Venue ID: {entry.reservation_request.venue_id}\n"
                f"  Party size: {entry.reservation_request.party_size}\n"
                f"  Date: {entry.reservation_request.target_date}\n"
                f"  Preferred time: {entry.reservation_request.ideal_hour}:"
                f"{entry.reservation_request.ideal_minute:02d}"
            ),
            notifications_config=entry.notifications,
            gmail_app_password=config.gmail_app_password,
            from_email=config.email,
        )

    except Exception as e:
        logger.error(f"[{venue_label}] Booking failed: {e}")

        notify_booking_result(
            success=False,
            details=(
                f"Booking failed for {venue_label}.\n\n"
                f"Error: {e}\n\n"
                f"Reservation details:\n"
                f"  Venue ID: {entry.reservation_request.venue_id}\n"
                f"  Party size: {entry.reservation_request.party_size}\n"
                f"  Date: {entry.reservation_request.target_date}"
            ),
            notifications_config=entry.notifications,
            gmail_app_password=config.gmail_app_password,
            from_email=config.email,
        )


def run_watchlist(config: ResyConfig, watchlist: Watchlist) -> None:
    manager = ResyManager.build(config)

    threads: List[threading.Thread] = []
    for entry in watchlist.venues:
        venue_label = entry.name or f"venue {entry.reservation_request.venue_id}"
        t = threading.Thread(
            target=_run_single_venue,
            args=(manager, entry, config),
            name=f"resy-{venue_label}",
        )
        threads.append(t)

    logger.info(f"Starting {len(threads)} venue thread(s)")
    for t in threads:
        t.start()

    for t in threads:
        t.join()

    logger.info("All venue threads completed")
