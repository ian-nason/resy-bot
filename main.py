import argparse
import json
import logging

from resy_bot.logging import setup_logging
from resy_bot.models import ResyConfig, TimedReservationRequest
from resy_bot.manager import ResyManager
from resy_bot.notifications import notify_booking_result

logger = logging.getLogger(__name__)


def wait_for_drop_time(resy_config_path: str, reservation_config_path: str) -> str:
    setup_logging()
    logger.info("waiting for drop time!")

    with open(resy_config_path, "r") as f:
        config_data = json.load(f)

    with open(reservation_config_path, "r") as f:
        reservation_data = json.load(f)

    config = ResyConfig(**config_data)
    manager = ResyManager.build(config)

    timed_request = TimedReservationRequest(**reservation_data)

    try:
        resy_token = manager.make_reservation_at_opening_time(timed_request)
        logger.info(f"Booking successful! Resy token: {resy_token}")

        notify_booking_result(
            success=True,
            details=f"Booking confirmed!\n\nResy token: {resy_token}\n\nReservation details:\n"
            f"  Venue ID: {timed_request.reservation_request.venue_id}\n"
            f"  Party size: {timed_request.reservation_request.party_size}\n"
            f"  Date: {timed_request.reservation_request.target_date}\n"
            f"  Preferred time: {timed_request.reservation_request.ideal_hour}:{timed_request.reservation_request.ideal_minute:02d}",
            notifications_config=timed_request.notifications,
            gmail_app_password=config.gmail_app_password,
            from_email=config.email,
        )

        return resy_token

    except Exception as e:
        logger.error(f"Booking failed: {e}")

        notify_booking_result(
            success=False,
            details=f"Booking failed.\n\nError: {e}\n\nReservation details:\n"
            f"  Venue ID: {timed_request.reservation_request.venue_id}\n"
            f"  Party size: {timed_request.reservation_request.party_size}\n"
            f"  Date: {timed_request.reservation_request.target_date}",
            notifications_config=timed_request.notifications,
            gmail_app_password=config.gmail_app_password,
            from_email=config.email,
        )

        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="ResyBot",
        description="Wait until reservation drop time and make one",
    )

    parser.add_argument("resy_config_path")
    parser.add_argument("reservation_config_path")

    args = parser.parse_args()

    wait_for_drop_time(args.resy_config_path, args.reservation_config_path)
