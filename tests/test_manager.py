from datetime import datetime, timedelta
import pytest
from unittest.mock import MagicMock, patch

from resy_bot.errors import NoSlotsError, ExhaustedRetriesError, ResyServerError
from resy_bot.api_access import ResyApiAccess
from resy_bot.models import (
    FindRequestBody,
    DetailsRequestBody,
    BookRequestBody,
    PaymentMethod,
    ReservationRetriesConfig,
)
from resy_bot.manager import ResyManager

from tests.factories import (
    ResyConfigFactory,
    SlotFactory,
    ReservationRequestFactory,
    DetailsResponseBodyFactory,
    ReservationRetriesConfigFactory,
    TimedReservationRequestFactory,
    ReservationRequestDaysInAdvanceFactory,
)


def test_build():
    config = ResyConfigFactory.create()
    manager = ResyManager.build(config)

    assert isinstance(manager, ResyManager)
    assert isinstance(manager.api_access, ResyApiAccess)


def test_make_reservation():
    config = ResyConfigFactory.create()
    retries_config = ReservationRetriesConfigFactory.create()
    request = ReservationRequestFactory.create()
    mock_api_access = MagicMock()
    slots = SlotFactory.create_batch(3)
    mock_api_access.find_booking_slots.return_value = slots

    details_response = DetailsResponseBodyFactory.create()
    mock_api_access.get_booking_token.return_value = details_response

    mock_selector = MagicMock()
    mock_selector.select.return_value = slots[0]

    manager = ResyManager(config, mock_api_access, mock_selector, retries_config)

    manager.make_reservation(request)

    expected_day = request.ideal_date.strftime("%Y-%m-%d")

    expected_find_request_body = FindRequestBody(
        venue_id=request.venue_id, party_size=request.party_size, day=expected_day
    )

    expected_details_request_body = DetailsRequestBody(
        config_id=slots[0].config.token, day=expected_day, party_size=request.party_size
    )

    expected_booking_request = BookRequestBody(
        book_token=details_response.book_token.value,
        struct_payment_method=PaymentMethod(id=config.payment_method_id),
    )

    mock_api_access.find_booking_slots.assert_called_once_with(
        expected_find_request_body
    )

    mock_selector.select.assert_called_once_with(slots, request)

    mock_api_access.get_booking_token.assert_called_once_with(
        expected_details_request_body
    )

    mock_api_access.book_slot.assert_called_once_with(expected_booking_request)


def test_make_reservation_days_in_advance():
    config = ResyConfigFactory.create()
    retries_config = ReservationRetriesConfigFactory.create()
    request = ReservationRequestDaysInAdvanceFactory.create()
    mock_api_access = MagicMock()
    slots = SlotFactory.create_batch(3)
    mock_api_access.find_booking_slots.return_value = slots

    details_response = DetailsResponseBodyFactory.create()
    mock_api_access.get_booking_token.return_value = details_response

    mock_selector = MagicMock()
    mock_selector.select.return_value = slots[0]

    manager = ResyManager(config, mock_api_access, mock_selector, retries_config)

    manager.make_reservation(request)

    expected_day = request.target_date.strftime("%Y-%m-%d")

    expected_find_request_body = FindRequestBody(
        venue_id=request.venue_id, party_size=request.party_size, day=expected_day
    )

    expected_details_request_body = DetailsRequestBody(
        config_id=slots[0].config.token, day=expected_day, party_size=request.party_size
    )

    expected_booking_request = BookRequestBody(
        book_token=details_response.book_token.value,
        struct_payment_method=PaymentMethod(id=config.payment_method_id),
    )

    mock_api_access.find_booking_slots.assert_called_once_with(
        expected_find_request_body
    )

    mock_selector.select.assert_called_once_with(slots, request)

    mock_api_access.get_booking_token.assert_called_once_with(
        expected_details_request_body
    )

    mock_api_access.book_slot.assert_called_once_with(expected_booking_request)


def test_make_reservation_no_slots():
    config = ResyConfigFactory.create()
    retries_config = ReservationRetriesConfigFactory.create()
    request = ReservationRequestFactory.create()
    mock_api_access = MagicMock()
    mock_api_access.find_booking_slots.return_value = []

    mock_selector = MagicMock()

    manager = ResyManager(config, mock_api_access, mock_selector, retries_config)

    with pytest.raises(NoSlotsError):
        manager.make_reservation(request)


@patch("resy_bot.manager.ResyManager.make_reservation")
def test_make_reservation_with_retries(mock_make_reservation):
    config = ResyConfigFactory.create()
    mock_make_reservation.side_effect = NoSlotsError
    mock_api_access = MagicMock()
    mock_selector = MagicMock()
    retry_config = ReservationRetriesConfig(
        seconds_between_retries=0.01,
        n_retries=5,
    )

    request = ReservationRequestFactory.create()

    manager = ResyManager(config, mock_api_access, mock_selector, retry_config)

    with pytest.raises(ExhaustedRetriesError):
        manager.make_reservation_with_retries(request)

    assert mock_make_reservation.call_count == 5


def test_get_drop_time():
    config = ResyConfigFactory.create()
    mock_api_access = MagicMock()
    mock_selector = MagicMock()
    retry_config = ReservationRetriesConfig(
        seconds_between_retries=0.1,
        n_retries=5,
    )

    request = TimedReservationRequestFactory.create(
        expected_drop_hour=10,
        expected_drop_minute=0,
    )

    manager = ResyManager(config, mock_api_access, mock_selector, retry_config)

    drop_time = manager._get_drop_time(request)

    now = datetime.now()
    expected = datetime(now.year, now.month, now.day, 10, 0) - timedelta(seconds=2)
    assert drop_time == expected


@patch("resy_bot.manager.datetime")
@patch("resy_bot.manager.ResyManager.make_reservation_with_retries")
def test_make_reservation_at_opening_time(mock_make_reservation, mock_dt):
    now = datetime.now()
    mock_dt.now.return_value = now - timedelta(seconds=0.1)
    request = TimedReservationRequestFactory.create(
        expected_drop_hour=now.hour,
        expected_drop_minute=now.minute,
    )
    # _get_drop_time uses datetime(year, month, day, hour, minute) - timedelta(seconds=2)
    mock_dt.return_value = datetime(
        year=now.year,
        month=now.month,
        day=now.day,
        hour=now.hour,
        minute=now.minute,
    )
    mock_dt.side_effect = None

    config = ResyConfigFactory.create()
    mock_api_access = MagicMock()
    mock_selector = MagicMock()
    retry_config = ReservationRetriesConfig(
        seconds_between_retries=0.1,
        n_retries=5,
    )

    manager = ResyManager(config, mock_api_access, mock_selector, retry_config)

    manager.make_reservation_at_opening_time(request)

    mock_make_reservation.assert_called_once()


@patch("resy_bot.manager.ResyManager.make_reservation")
def test_retry_on_500_does_not_count(mock_make_reservation):
    """500 errors should not count toward the retry limit."""
    config = ResyConfigFactory.create()
    # First two calls: server error, third call: no slots, fourth: success
    mock_make_reservation.side_effect = [
        ResyServerError("500"),
        ResyServerError("500"),
        NoSlotsError("no slots"),
        "token123",
    ]
    mock_api_access = MagicMock()
    mock_selector = MagicMock()
    retry_config = ReservationRetriesConfig(
        seconds_between_retries=0.01,
        n_retries=2,
    )

    request = ReservationRequestFactory.create()
    manager = ResyManager(config, mock_api_access, mock_selector, retry_config)

    result = manager.make_reservation_with_retries(request)
    assert result == "token123"
    # 2 server errors + 1 no slots + 1 success = 4 calls
    assert mock_make_reservation.call_count == 4


@patch("resy_bot.manager.ResyManager.make_reservation")
def test_fallback_party_sizes(mock_make_reservation):
    """If primary party size has no slots, try fallback sizes."""
    config = ResyConfigFactory.create()
    # First call (party=4): no slots, second call (party=2): success
    mock_make_reservation.side_effect = [NoSlotsError("no slots"), "token456"]
    mock_api_access = MagicMock()
    mock_selector = MagicMock()
    retry_config = ReservationRetriesConfig(
        seconds_between_retries=0.01,
        n_retries=5,
    )

    request = ReservationRequestFactory.create(
        party_size=4,
        fallback_party_sizes=[2],
    )
    manager = ResyManager(config, mock_api_access, mock_selector, retry_config)

    result = manager.make_reservation_with_retries(request)
    assert result == "token456"
    assert mock_make_reservation.call_count == 2
    # Verify the second call used party_size=2
    second_call_request = mock_make_reservation.call_args_list[1][0][0]
    assert second_call_request.party_size == 2


@patch("resy_bot.manager.ResyManager.make_reservation")
def test_date_range(mock_make_reservation):
    """date_range should try multiple dates."""
    config = ResyConfigFactory.create()
    # First call (target date): no slots, second call (target+1): success
    mock_make_reservation.side_effect = [NoSlotsError("no slots"), "token789"]
    mock_api_access = MagicMock()
    mock_selector = MagicMock()
    retry_config = ReservationRetriesConfig(
        seconds_between_retries=0.01,
        n_retries=5,
    )

    from datetime import date
    target = date.today()
    request = ReservationRequestFactory.create(
        ideal_date=target,
        date_range=3,
    )
    manager = ResyManager(config, mock_api_access, mock_selector, retry_config)

    result = manager.make_reservation_with_retries(request)
    assert result == "token789"
    # First call with target date, second with target+1
    first_req = mock_make_reservation.call_args_list[0][0][0]
    second_req = mock_make_reservation.call_args_list[1][0][0]
    assert first_req.ideal_date == target
    assert second_req.ideal_date == target + timedelta(days=1)
