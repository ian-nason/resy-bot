import time
from datetime import datetime, date, timedelta
from typing import List

from resy_bot.logging import logging
from resy_bot.errors import NoSlotsError, ExhaustedRetriesError, ResyServerError
from resy_bot.constants import (
    N_RETRIES,
    SECONDS_TO_WAIT_BETWEEN_RETRIES,
    EARLY_START_SECONDS,
    SERVER_ERROR_RETRY_WAIT,
)
from resy_bot.models import (
    ResyConfig,
    ReservationRequest,
    TimedReservationRequest,
    ReservationRetriesConfig,
)
from resy_bot.model_builders import (
    build_find_request_body,
    build_get_slot_details_body,
    build_book_request_body,
)
from resy_bot.api_access import ResyApiAccess
from resy_bot.selectors import AbstractSelector, SimpleSelector

logger = logging.getLogger(__name__)
logger.setLevel("INFO")


class ResyManager:
    @classmethod
    def build(cls, config: ResyConfig) -> "ResyManager":
        api_access = ResyApiAccess.build(config)
        selector = SimpleSelector()
        retry_config = ReservationRetriesConfig(
            seconds_between_retries=SECONDS_TO_WAIT_BETWEEN_RETRIES,
            n_retries=N_RETRIES,
        )
        return cls(config, api_access, selector, retry_config)

    def __init__(
        self,
        config: ResyConfig,
        api_access: ResyApiAccess,
        slot_selector: AbstractSelector,
        retry_config: ReservationRetriesConfig,
    ):
        self.config = config
        self.api_access = api_access
        self.selector = slot_selector
        self.retry_config = retry_config

    def get_venue_id(self, address: str):
        """
        TODO: get venue id from string address
            will use geolocator to get lat/long
        :return:
        """
        pass

    def make_reservation(self, reservation_request: ReservationRequest) -> str:
        body = build_find_request_body(reservation_request)

        slots = self.api_access.find_booking_slots(body)
        logger.info(f"Returned: {slots}")

        if len(slots) == 0:
            raise NoSlotsError("No Slots Found")
        else:
            logger.info(len(slots))
            logger.info(slots)

        selected_slot = self.selector.select(slots, reservation_request)

        logger.info(selected_slot)
        details_request = build_get_slot_details_body(
            reservation_request, selected_slot
        )
        logger.info(details_request)
        token = self.api_access.get_booking_token(details_request)

        booking_request = build_book_request_body(token, self.config)

        resy_token = self.api_access.book_slot(booking_request)

        return resy_token

    def _get_dates_to_try(self, reservation_request: ReservationRequest) -> List[date]:
        target = reservation_request.target_date
        n_dates = reservation_request.date_range or 1
        return [target + timedelta(days=i) for i in range(n_dates)]

    def _get_party_sizes_to_try(self, reservation_request: ReservationRequest) -> List[int]:
        sizes = [reservation_request.party_size]
        if reservation_request.fallback_party_sizes:
            sizes.extend(reservation_request.fallback_party_sizes)
        return sizes

    def _with_overrides(
        self, reservation_request: ReservationRequest, target_date: date, party_size: int
    ) -> ReservationRequest:
        return reservation_request.copy(
            update={
                "ideal_date": target_date,
                "days_in_advance": None,
                "party_size": party_size,
            }
        )

    def make_reservation_with_retries(
        self, reservation_request: ReservationRequest
    ) -> str:
        dates = self._get_dates_to_try(reservation_request)
        party_sizes = self._get_party_sizes_to_try(reservation_request)

        retries = 0
        while retries < self.retry_config.n_retries:
            server_error = False
            for target_date in dates:
                if server_error:
                    break
                for party_size in party_sizes:
                    modified = self._with_overrides(reservation_request, target_date, party_size)
                    try:
                        return self.make_reservation(modified)
                    except NoSlotsError:
                        logger.info(
                            f"no slots for party of {party_size} on {target_date}, "
                            f"trying next option"
                        )
                        continue
                    except ResyServerError:
                        logger.warning(
                            f"API returned 500 for venue {reservation_request.venue_id}, "
                            f"waiting {SERVER_ERROR_RETRY_WAIT}s (not counted as retry)"
                        )
                        time.sleep(SERVER_ERROR_RETRY_WAIT)
                        server_error = True
                        break

            if not server_error:
                retries += 1
                logger.info(
                    f"no slots found ({retries}/{self.retry_config.n_retries}); "
                    f"currently {datetime.now().isoformat()}"
                )
                time.sleep(self.retry_config.seconds_between_retries)

        raise ExhaustedRetriesError(
            f"Retried {self.retry_config.n_retries} times, without finding a slot"
        )

    def _get_drop_time(self, reservation_request: TimedReservationRequest) -> datetime:
        now = datetime.now()
        return datetime(
            year=now.year,
            month=now.month,
            day=now.day,
            hour=reservation_request.expected_drop_hour,
            minute=reservation_request.expected_drop_minute,
        ) - timedelta(seconds=EARLY_START_SECONDS)

    def make_reservation_at_opening_time(
        self, reservation_request: TimedReservationRequest
    ) -> str:
        """
        cycle until we hit the opening time, then run & return the reservation
        """
        drop_time = self._get_drop_time(reservation_request)
        last_check = datetime.now()

        while True:
            if datetime.now() < drop_time:
                if datetime.now() - last_check > timedelta(seconds=10):
                    logger.info(f"{datetime.now()}: still waiting")
                    last_check = datetime.now()
                continue

            logger.info(f"time reached, making a reservation now! {datetime.now()}")
            return self.make_reservation_with_retries(
                reservation_request.reservation_request
            )
