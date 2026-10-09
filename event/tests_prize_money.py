"""Unit tests for event.prize_money (previously ~21% covered)."""
from datetime import date
from types import SimpleNamespace

from django.test import TestCase

from club.models import Club
from event.models import Event, EventType, Result
from event.prize_money import (
    PRIZE_MONEY_SCHEMES,
    PrizeMoneyPdfService,
    _normalize_category,
    _resolve_rider_class_20_for_event,
)
from rider.models import Rider


class NormalizeCategoryTests(TestCase):
    def test_strips_and_lowercases(self):
        self.assertEqual(_normalize_category("  Elite Men  "), "elite men")

    def test_handles_none(self):
        self.assertEqual(_normalize_category(None), "")

    def test_handles_empty(self):
        self.assertEqual(_normalize_category(""), "")


class ResolveRiderClass20Tests(TestCase):
    def _rider(self, dob, gender="Muž", is_elite=False):
        return SimpleNamespace(date_of_birth=dob, gender=gender, is_elite=is_elite)

    def test_returns_empty_without_rider(self):
        self.assertEqual(_resolve_rider_class_20_for_event(None, date(2024, 1, 1)), "")

    def test_returns_empty_without_event_date(self):
        rider = self._rider(date(2000, 1, 1))
        self.assertEqual(_resolve_rider_class_20_for_event(rider, None), "")

    def test_returns_empty_without_date_of_birth(self):
        rider = self._rider(None)
        self.assertEqual(_resolve_rider_class_20_for_event(rider, date(2024, 1, 1)), "")

    def test_elite_men_junior_u23_elite(self):
        event_date = date(2024, 1, 1)
        self.assertEqual(
            _resolve_rider_class_20_for_event(self._rider(date(2007, 1, 1), "Muž", True), event_date),
            "Men Junior",
        )  # age 17
        self.assertEqual(
            _resolve_rider_class_20_for_event(self._rider(date(2003, 1, 1), "Muž", True), event_date),
            "Men Under 23",
        )  # age 21
        self.assertEqual(
            _resolve_rider_class_20_for_event(self._rider(date(1990, 1, 1), "Muž", True), event_date),
            "Men Elite",
        )  # age 34

    def test_elite_women_junior_u23_elite(self):
        event_date = date(2024, 1, 1)
        self.assertEqual(
            _resolve_rider_class_20_for_event(self._rider(date(2007, 1, 1), "Žena", True), event_date),
            "Women Junior",
        )
        self.assertEqual(
            _resolve_rider_class_20_for_event(self._rider(date(2003, 1, 1), "Žena", True), event_date),
            "Women Under 23",
        )
        self.assertEqual(
            _resolve_rider_class_20_for_event(self._rider(date(1990, 1, 1), "Žena", True), event_date),
            "Women Elite",
        )

    def test_elite_ostatni_treated_as_men(self):
        self.assertEqual(
            _resolve_rider_class_20_for_event(
                self._rider(date(1990, 1, 1), "Ostatní", True), date(2024, 1, 1)
            ),
            "Men Elite",
        )

    def test_youth_boys_age_brackets(self):
        event_date = date(2024, 1, 1)
        self.assertEqual(
            _resolve_rider_class_20_for_event(self._rider(date(2018, 1, 1), "Muž"), event_date),
            "Boys 6",
        )
        self.assertEqual(
            _resolve_rider_class_20_for_event(self._rider(date(2008, 1, 1), "Muž"), event_date),
            "Boys 16",
        )
        self.assertEqual(
            _resolve_rider_class_20_for_event(self._rider(date(2004, 1, 1), "Muž"), event_date),
            "Men 17-24",
        )  # age 20
        self.assertEqual(
            _resolve_rider_class_20_for_event(self._rider(date(1996, 1, 1), "Muž"), event_date),
            "Men 25-29",
        )  # age 28
        self.assertEqual(
            _resolve_rider_class_20_for_event(self._rider(date(1992, 1, 1), "Muž"), event_date),
            "Men 30-34",
        )  # age 32
        self.assertEqual(
            _resolve_rider_class_20_for_event(self._rider(date(1980, 1, 1), "Muž"), event_date),
            "Men 35 and over",
        )

    def test_youth_girls_age_brackets(self):
        event_date = date(2024, 1, 1)
        self.assertEqual(
            _resolve_rider_class_20_for_event(self._rider(date(2018, 1, 1), "Žena"), event_date),
            "Girls 6",
        )
        self.assertEqual(
            _resolve_rider_class_20_for_event(self._rider(date(2008, 1, 1), "Žena"), event_date),
            "Girls 16",
        )
        self.assertEqual(
            _resolve_rider_class_20_for_event(self._rider(date(2004, 1, 1), "Žena"), event_date),
            "Women 17-24",
        )
        self.assertEqual(
            _resolve_rider_class_20_for_event(self._rider(date(1990, 1, 1), "Žena"), event_date),
            "Women 25 and over",
        )


class PrizeMoneyPdfServiceHelperTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(team_name="Prize Club")
        self.service = PrizeMoneyPdfService()

    def _event(self, event_type):
        return Event.objects.create(
            name="Prize race",
            date=date(2024, 6, 1),
            organizer=self.club,
            type_for_ranking=event_type,
        )

    def test_get_scheme_known_type(self):
        event = self._event(EventType.MCR_JEDNOTLIVCU)
        self.assertIs(self.service.get_scheme(event), PRIZE_MONEY_SCHEMES[EventType.MCR_JEDNOTLIVCU])

    def test_get_scheme_unknown_type_returns_empty(self):
        event = self._event(EventType.VOLNY_ZAVOD)
        self.assertEqual(self.service.get_scheme(event), ())

    def test_allows_amount_toggle(self):
        self.assertTrue(self.service.allows_amount_toggle(self._event(EventType.CESKY_POHAR)))
        self.assertFalse(self.service.allows_amount_toggle(self._event(EventType.CESKA_LIGA)))
        self.assertFalse(self.service.allows_amount_toggle(self._event(EventType.VOLNY_ZAVOD)))

    def test_aliases_to_category_map(self):
        scheme = PRIZE_MONEY_SCHEMES[EventType.CESKY_POHAR]
        alias_map = self.service._aliases_to_category_map(scheme)
        # every alias maps to the normalized first alias of its category
        self.assertEqual(alias_map["men elite"], "men elite")
        self.assertEqual(alias_map["elite men"], "men elite")
        self.assertEqual(alias_map["em"], "men elite")

    def test_build_rows_place_ordered_with_amounts(self):
        rider = Rider.objects.create(
            uci_id=10000000001,
            first_name="Anna",
            last_name="Nova",
            gender="Žena",
            date_of_birth=date(1995, 1, 1),
            club=self.club,
        )
        r1 = Result(place=1, rider=rider, category="Elite Women")
        rows = self.service._build_rows([r1], (5000, 3000), include_amounts=True)
        self.assertEqual(len(rows), 2)  # one row per prize place
        self.assertEqual(rows[0][0], "1")
        self.assertEqual(rows[0][1], "Anna Nova")
        self.assertEqual(rows[0][2], 10000000001)
        self.assertEqual(rows[0][3], "5 000 Kč")
        # second place has no result -> blank name
        self.assertEqual(rows[1][1], "")

    def test_build_rows_without_amounts_uses_foreign_name(self):
        r1 = Result(place=1, rider=None, first_name="Foreign", last_name="Racer")
        rows = self.service._build_rows([r1], (800,), include_amounts=False)
        self.assertEqual(rows[0][1], "Foreign Racer")
        # no amount column: [place, name, uci_id, signature]
        self.assertEqual(len(rows[0]), 4)


class PrizeMoneyBuildPdfTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(team_name="Org Club")

    def _make_event(self, event_type):
        return Event.objects.create(
            name="Grand Prix",
            date=date(2024, 6, 1),
            organizer=self.club,
            type_for_ranking=event_type,
        )

    def test_build_pdf_unknown_type_raises(self):
        event = self._make_event(EventType.VOLNY_ZAVOD)
        with self.assertRaises(ValueError):
            PrizeMoneyPdfService().build_pdf(event)

    def test_build_pdf_cesky_pohar_returns_pdf_bytes(self):
        event = self._make_event(EventType.CESKY_POHAR)
        Result.objects.create(
            event=event,
            category="Elite Men",
            place=1,
            first_name="Jan",
            last_name="Rychly",
            is_20=True,
        )
        pdf = PrizeMoneyPdfService().build_pdf(event, include_amounts=True)
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_build_pdf_mcr_uses_rider_class_resolution(self):
        event = self._make_event(EventType.MCR_JEDNOTLIVCU)
        rider = Rider.objects.create(
            uci_id=10000000002,
            first_name="Petr",
            last_name="Elita",
            gender="Muž",
            date_of_birth=date(1990, 1, 1),
            is_elite=True,
            club=self.club,
        )
        Result.objects.create(
            event=event,
            category="Muži Elite",  # not a scheme alias -> falls back to rider class
            place=1,
            rider=rider,
            is_20=True,
        )
        pdf = PrizeMoneyPdfService().build_pdf(event)
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_build_pdf_forces_amounts_when_toggle_disabled(self):
        event = self._make_event(EventType.CESKA_LIGA)
        # include_amounts=False must be overridden to True internally; just assert it builds
        pdf = PrizeMoneyPdfService().build_pdf(event, include_amounts=False)
        self.assertTrue(pdf.startswith(b"%PDF"))
