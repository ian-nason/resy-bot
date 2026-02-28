import argparse
import json
import logging

from resy_bot.logging import setup_logging
from resy_bot.models import ResyConfig, TimedReservationRequest, Watchlist
from resy_bot.manager import ResyManager
from resy_bot.api_access import ResyApiAccess
from resy_bot.notifications import notify_booking_result
from resy_bot.watchlist import run_watchlist

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


def run_watchlist_command(resy_config_path: str, watchlist_path: str) -> None:
    setup_logging()
    logger.info("Running watchlist mode")

    with open(resy_config_path, "r") as f:
        config_data = json.load(f)

    with open(watchlist_path, "r") as f:
        watchlist_data = json.load(f)

    config = ResyConfig(**config_data)
    watchlist = Watchlist(**watchlist_data)

    logger.info(f"Loaded watchlist with {len(watchlist.venues)} venue(s)")
    run_watchlist(config, watchlist)


def search_venue_command(resy_config_path: str, query: str) -> None:
    setup_logging()

    with open(resy_config_path, "r") as f:
        config_data = json.load(f)

    config = ResyConfig(**config_data)
    api_access = ResyApiAccess.build(config)

    results = api_access.search_venues(query=query)

    if not results:
        print(f"No venues found for '{query}'")
        return

    print(f"\nSearch results for '{query}':\n")
    print(f"{'Venue ID':<12} {'Name':<35} {'Cuisine':<20} {'Neighborhood':<20} {'Location'}")
    print("-" * 110)
    for venue in results:
        vid = str(venue.get('venue_id') or '')
        name = venue.get('name') or ''
        cuisine = venue.get('cuisine') or ''
        neighborhood = venue.get('neighborhood') or ''
        locality = venue.get('locality') or ''
        region = venue.get('region') or ''
        location = f"{locality}, {region}" if locality else region
        print(f"{vid:<12} {name:<35} {cuisine:<20} {neighborhood:<20} {location}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="ResyBot",
        description="Resy reservation bot",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    run_parser = subparsers.add_parser(
        "run", help="Run bot for a single reservation request"
    )
    run_parser.add_argument("resy_config_path", help="Path to credentials.json")
    run_parser.add_argument(
        "reservation_config_path", help="Path to reservation_request.json"
    )

    watchlist_parser = subparsers.add_parser(
        "watchlist", help="Run bot for multiple venues from a watchlist"
    )
    watchlist_parser.add_argument("resy_config_path", help="Path to credentials.json")
    watchlist_parser.add_argument("watchlist_path", help="Path to watchlist.json")

    search_parser = subparsers.add_parser(
        "search", help="Search for a venue by name"
    )
    search_parser.add_argument("resy_config_path", help="Path to credentials.json")
    search_parser.add_argument("query", help="Restaurant name to search for")

    args = parser.parse_args()

    if args.command == "run":
        wait_for_drop_time(args.resy_config_path, args.reservation_config_path)
    elif args.command == "watchlist":
        run_watchlist_command(args.resy_config_path, args.watchlist_path)
    elif args.command == "search":
        search_venue_command(args.resy_config_path, args.query)
    else:
        parser.print_help()
