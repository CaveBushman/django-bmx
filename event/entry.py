import logging
from django.conf import settings
import os
import event

logger = logging.getLogger(__name__)
from .models import Entry, EntryForeign as EntryForeignModel, EventType
from rider.models import Rider, ForeignRider
from django.utils import timezone
from openpyxl import Workbook


class EntryClass:
    """ Class for saving entries to the Entry table in database """

    def __init__(self):
        self.transaction_id = None
        self.event = None
        self.rider: Rider = None
        self.is_beginner: bool = False
        self.is_20: bool = False
        self.is_24: bool = False
        self.class_beginner: str = None
        self.class_20: str = None
        self.class_24: str = None
        self.fee_beginner: int = 0
        self.fee_20: int = 0
        self.fee_24: int = 0

    def save(self):
        new_czech_entry = Entry.objects.create(
            transaction_id=self.transaction_id,
            event=self.event,
            rider=self.rider,
            is_beginner=self.is_beginner,
            is_20=self.is_20,
            is_24=self.is_24,
            fee_beginner=self.fee_beginner,
            fee_20=self.fee_20,
            fee_24=self.fee_24,
            class_beginner=self.class_beginner,
            class_20=self.class_20,
            class_24=self.class_24,
        )
        new_czech_entry.save()


class EntryForeign:
    """ Class for saving foreign entries to the Foreign Entry table in database """

    def __init__(self):
        self.event=None
        self.first_name=None
        self.last_name=None
        self.uci_id=None
        self.gender=None
        self.nationality=None
        self.club=None
        self.transponder=None
        self.is_20: bool =None
        self.is_24: bool=None
        self.class_20=None
        self.class_24=None
        self.fee_20=None
        self.fee_24=None
        self.checkout: bool=False
        self.transaction_id=None
        self.customer_name=None
        self.customer_email=None
        self.payment_complete:bool=False
        self.transaction_date=None

    def save(self):
        new_foreign_entry = EntryForeignModel.objects.create(
            event = self.event,
            first_name=self.first_name,
            last_name=self.last_name,
            uci_id=self.uci_id,
            gender=self.gender,
            nationality=self.nationality,
            club=self.club,
            transponder=self.transponder,
            is_20=self.is_20,
            is_24=self.is_24,
            class_20=self.class_20,
            class_24=self.class_24,
            fee_20=self.fee_20,
            fee_24=self.fee_24,
            checkout=self.checkout,
            transaction_id=self.transaction_id,
            customer_name=self.customer_name,
            customer_email=self.customer_email,
            payment_complete=self.payment_complete,
            transaction_date=self.transaction_date,
        )
        new_foreign_entry.save()
        

class REMRiders:
    """ Class for create riders lists in xlsx file for REM """

    def __init__(self):
        self.event = None
        self.file_name = None
        self.template_name = os.path.join(settings.MEDIA_ROOT, "rem_entries", "Rider_and_Registration.xlsx")
        # self.wb = load_workbook(self.template_name)
        self.wb = Workbook()
        self.wb.encoding = "utf-8"
        self.ws = self.wb.active
        self.ws.title = "Rider-Registration"
        self.riders = Rider.objects.filter(is_active=True, is_approved=True)
        self.foreign_riders = ForeignRider.objects.filter()

    def _save_workbook(self, file_name):
        os.makedirs(os.path.dirname(file_name), exist_ok=True)
        self.wb.save(file_name)

    def first_line(self):
        """ set first line in REM online entries excel file """
        self.ws.cell(1, 1, "Event")
        self.ws.cell(1, 2, "First")
        self.ws.cell(1, 3, "Last")
        self.ws.cell(1, 4, "Email")
        self.ws.cell(1, 5, "Club")
        self.ws.cell(1, 6, "Team")
        self.ws.cell(1, 7, "Country")
        self.ws.cell(1, 8, "Birthdate")
        self.ws.cell(1, 9, "Sex")
        self.ws.cell(1, 10, "UCIID")
        self.ws.cell(1, 11, "Rider_type")
        self.ws.cell(1, 12, "Rider_licence_type")
        self.ws.cell(1, 13, "Rider_ident")
        self.ws.cell(1, 14, "Paid")
        self.ws.cell(1, 15, "Event_price")
        self.ws.cell(1, 16, "Admin_fee")
        self.ws.cell(1, 17, "Transponder_hire_price")
        self.ws.cell(1, 18, "Class")
        self.ws.cell(1, 19, "Plate")
        self.ws.cell(1, 20, "Transponder")
        self.ws.cell(1, 21, "Plate_1")  # cruiser
        self.ws.cell(1, 22, "Transponder_1")  # cruiser
        self.ws.cell(1, 23, "Transponder_hire_flag")

    def _mcr_club_team_riders(self):
        """Jezdci ze soupisek družstev MČR — jeden řádek na jezdce a druh kola.

        Jezdec zapsaný na 20" i 24" jde do seznamu dvakrát, pokaždé jen s
        kolonkami svého kola. Stejné kolo v jednom roce se nezopakuje.
        Elite jezdec 24" jet nesmí, cruiser řádek se mu proto nezakládá.
        """
        from club.models import McrClubTeam, McrClubTeamMember

        teams = (
            McrClubTeam.objects
            .filter(year=self.event.date.year if self.event.date else timezone.now().year)
            .select_related("club")
            .prefetch_related("members__rider")
            .order_by("club__team_name", "name")
        )
        seen = set()
        for team in teams:
            for member in team.members.all():
                rider = member.rider
                if rider is None or (rider.id, member.wheel) in seen:
                    continue
                if member.wheel == McrClubTeamMember.WHEEL_24 and rider.is_elite:
                    logger.warning(
                        "REM seznam jezdců: elite jezdec %s je na soupisce družstva %s na 24\" — cruiser řádek vynechán",
                        rider.uci_id, team.name,
                    )
                    continue
                seen.add((rider.id, member.wheel))
                yield rider, team.name, member.wheel

    def create_all_riders_list(self):
        self.file_name = os.path.join(settings.MEDIA_ROOT, "rem_riders", f"REM_ALL_RIDERS_FOR_RACE_ID-{self.event.id}.xlsx")
        self.first_line()

        row: int = 2

        # Na MČR družstev jedou jen členové soupisek a REM potřebuje u jezdce
        # název družstva (klub zůstává klubem jezdce).
        is_mcr_club_teams = bool(self.event) and self.event.type_for_ranking == EventType.MCR_DRUZSTEV
        if is_mcr_club_teams:
            riders = self._mcr_club_team_riders()
        else:
            riders = ((rider, None, None) for rider in self.riders)

        for rider, team_name, wheel in riders:
            self.ws.cell(row, 1, )
            self.ws.cell(row, 2, rider.first_name)
            self.ws.cell(row, 3, rider.last_name)
            self.ws.cell(row, 4, rider.email)
            self.ws.cell(row, 5, event.func.team_name_resolve(rider.club))
            self.ws.cell(row, 6, team_name)
            self.ws.cell(row, 7, "CZE")
            self.ws.cell(row, 8, event.func.date_of_birth_resolve(rider))
            self.ws.cell(row, 9, event.func.gender_resolve(rider))
            self.ws.cell(row, 10, rider.uci_id)
            if rider.is_elite:
                self.ws.cell(row, 11, "E")
            else:
                self.ws.cell(row, 11, "C")
            self.ws.cell(row, 12, "U")
            self.ws.cell(row, 13, )
            self.ws.cell(row, 14, )
            self.ws.cell(row, 15, )
            self.ws.cell(row, 16, )
            self.ws.cell(row, 17, )
            self.ws.cell(row, 18, )
            # Řádek ze soupisky družstva patří jednomu kolu — vyplní se jen jeho sloupce.
            if wheel != "24":
                self.ws.cell(row, 19, rider.plate_display)
                self.ws.cell(row, 20, rider.transponder_20)
            if wheel != "20":
                self.ws.cell(row, 21, rider.plate_display)
                self.ws.cell(row, 22, rider.transponder_24)
            self.ws.cell(row, 23, )
            row += 1

        # Add foreign riders — na MČR družstev startují jen členové soupisek
        for rider in ([] if is_mcr_club_teams else self.foreign_riders):
            self.ws.cell(row, 1, )
            self.ws.cell(row, 2, rider.first_name)
            self.ws.cell(row, 3, rider.last_name)
            self.ws.cell(row, 4, )
            self.ws.cell(row, 5, rider.club)
            self.ws.cell(row, 6, )
            self.ws.cell(row, 7, rider.state)
            self.ws.cell(row, 8, event.func.date_of_birth_resolve(rider))
            self.ws.cell(row, 9, event.func.gender_resolve(rider))
            self.ws.cell(row, 10, rider.uci_id)
            if rider.is_elite:
                self.ws.cell(row, 11, "E")
            else:
                self.ws.cell(row, 11, "C")
            self.ws.cell(row, 12, "U")
            self.ws.cell(row, 13, )
            self.ws.cell(row, 14, )
            self.ws.cell(row, 15, )
            self.ws.cell(row, 16, )
            self.ws.cell(row, 17, )
            self.ws.cell(row, 18, )
            self.ws.cell(row, 19, rider.plate_display)
            self.ws.cell(row, 20, rider.transponder_20)
            self.ws.cell(row, 21, rider.plate_display)
            self.ws.cell(row, 22, rider.transponder_24)
            self.ws.cell(row, 23, )
            row += 1

        self._save_workbook(self.file_name)

        self.event.rem_riders_list = self.file_name
        self.event.rem_riders_created = timezone.now()
        self.event.save()

        # self.remove_temp_file()

    def create_entries_list(self):
        file_name = os.path.join(settings.MEDIA_ROOT, "rem_entries", f"REM_ENTRIES_FOR_RACE_ID-{self.event.id}.xlsx")
        self.first_line()
        czech_entries = Entry.objects.filter(event=self.event.id, payment_complete=True, checkout=False).select_related('rider')
        foreign_entries = EntryForeignModel.objects.filter(
            event=self.event.id,
            payment_complete=True,
            checkout=False,
        )

        uci_ids = list(foreign_entries.values_list('uci_id', flat=True))
        foreign_rider_clubs = {
            str(fr_uci_id): club
            for fr_uci_id, club in ForeignRider.objects.filter(uci_id__in=uci_ids, club__gt='').values_list('uci_id', 'club')
        }

        row: int = 2
        for entry in czech_entries:
            try:
                self.ws.cell(row, 1, self.event.name)
                self.ws.cell(row, 2, entry.rider.first_name)
                self.ws.cell(row, 3, entry.rider.last_name)
                self.ws.cell(row, 4, entry.rider.email)
                self.ws.cell(row, 5, event.func.team_name_resolve(entry.rider.club))
                self.ws.cell(row, 6, )
                self.ws.cell(row, 7, entry.rider.nationality)
                self.ws.cell(row, 8, event.func.date_of_birth_resolve_rem_online(entry.rider.date_of_birth))
                self.ws.cell(row, 9, event.func.gender_resolve_small_letter(entry.rider.gender))
                self.ws.cell(row, 10, entry.rider.uci_id)
                if entry.rider.is_elite:
                    self.ws.cell(row, 11, "E")
                else:
                    self.ws.cell(row, 11, "C")
                self.ws.cell(row, 12, "U")
                self.ws.cell(row, 13, )
                self.ws.cell(row, 14, "true")
                if entry.is_beginner:
                    self.ws.cell(row, 15, entry.fee_beginner)
                elif entry.is_20:
                    self.ws.cell(row, 15, entry.fee_20)
                else:
                    self.ws.cell(row, 15, entry.fee_24)
                self.ws.cell(row, 16, )
                self.ws.cell(row, 17, )
                if entry.is_beginner:
                    self.ws.cell(row, 18, entry.class_beginner)
                elif entry.is_20:
                    self.ws.cell(row, 18, entry.class_20)
                else:
                    self.ws.cell(row, 18, entry.class_24)
                if entry.is_20 and entry.rider.plate_champ_20:
                    world_plate = "W" + str(entry.rider.plate_champ_20)
                    self.ws.cell(row, 19, world_plate)
                elif entry.is_20 or entry.is_beginner:
                    self.ws.cell(row, 19, entry.rider.plate_display)
                elif entry.is_24 and entry.rider.plate_champ_24:
                    world_plate = "W" + str(entry.rider.plate_champ_24)
                    self.ws.cell(row, 21, world_plate)
                else:
                    self.ws.cell(row, 21, entry.rider.plate_display)
                if entry.is_24:
                    self.ws.cell(row, 22, entry.rider.transponder_24)
                else:
                    self.ws.cell(row, 20, entry.rider.transponder_20)
            except Exception as E:
                logger.error(f"Chyba při ukládání jezdce do REM: {E}")
            row += 1
        del czech_entries

        for entry in foreign_entries:
            try:
                self.ws.cell(row, 1, self.event.name)
                self.ws.cell(row, 2, entry.first_name)
                self.ws.cell(row, 3, entry.last_name)
                self.ws.cell(row, 4, entry.customer_email)
                club = foreign_rider_clubs.get(entry.uci_id) or entry.club or event.func.foreign_club_resolve(entry.nationality or "")
                self.ws.cell(row, 5, club)
                self.ws.cell(row, 6, )
                self.ws.cell(row, 7, entry.nationality)
                self.ws.cell(row, 8, event.func.date_of_birth_resolve_rem_online(entry.date_of_birth))
                self.ws.cell(row, 9, event.func.gender_resolve_small_letter(entry.gender))
                self.ws.cell(row, 10, entry.uci_id)
                if entry.is_elite:
                    self.ws.cell(row, 11, "E")
                else:
                    self.ws.cell(row, 11, "C")
                self.ws.cell(row, 12, "U")
                self.ws.cell(row, 13, )
                self.ws.cell(row, 14, "true")
                if entry.is_20:
                    self.ws.cell(row, 15, entry.fee_20)
                else:
                    self.ws.cell(row, 15, entry.fee_24)
                self.ws.cell(row, 16, )
                self.ws.cell(row, 17, )
                if entry.is_20:
                    self.ws.cell(row, 18, entry.class_20)
                else:
                    self.ws.cell(row, 18, entry.class_24)
                if entry.is_20:
                    self.ws.cell(row, 19, entry.plate)
                    self.ws.cell(row, 20, entry.transponder_20)
                else:
                    self.ws.cell(row, 21, entry.plate)
                    self.ws.cell(row, 22, entry.transponder_24)
            except Exception as E:
                logger.error(f"Chyba při ukládání jezdce do REM: {E}")
            row += 1
        del foreign_entries

        self._save_workbook(file_name)
        self.event.rem_entries = file_name
        self.event.rem_entries_created = timezone.now()
        self.event.save()

    def create_mcr_club_entries_list(self):
        from club.models import McrClubTeam, McrClubTeamMember

        file_name = os.path.join(settings.MEDIA_ROOT, "rem_entries", f"REM_MCR_CLUB_ENTRIES_FOR_RACE_ID-{self.event.id}.xlsx")
        self.first_line()
        teams = (
            McrClubTeam.objects
            .filter(year=self.event.date.year if self.event.date else timezone.now().year)
            .select_related("club")
            .prefetch_related("members__rider")
            .order_by("club__team_name", "name")
        )

        row = 2
        for team in teams:
            for member in team.members.all():
                rider = member.rider
                is_cruiser = member.wheel == McrClubTeamMember.WHEEL_24
                # Elite jezdec 24" jet nesmí — do startovky se cruiser řádek nedostane.
                if is_cruiser and rider.is_elite:
                    logger.warning(
                        "REM přihlášky MČR družstev: elite jezdec %s je na soupisce družstva %s na 24\" — vynechán",
                        rider.uci_id, team.name,
                    )
                    continue
                self.ws.cell(row, 1, self.event.name)
                self.ws.cell(row, 2, rider.first_name)
                self.ws.cell(row, 3, rider.last_name)
                self.ws.cell(row, 4, rider.email)
                self.ws.cell(row, 5, team.club.team_name)
                self.ws.cell(row, 6, team.name)
                self.ws.cell(row, 7, rider.nationality)
                self.ws.cell(row, 8, event.func.date_of_birth_resolve_rem_online(rider.date_of_birth))
                self.ws.cell(row, 9, event.func.gender_resolve_small_letter(rider.gender))
                self.ws.cell(row, 10, rider.uci_id)
                self.ws.cell(row, 11, "E" if rider.is_elite else "C")
                self.ws.cell(row, 12, "U")
                self.ws.cell(row, 14, "true")
                self.ws.cell(row, 15, 0)
                category = (
                    event.func.resolve_event_classes(self.event, rider, is_20=not is_cruiser)
                    if self.event.classes_and_fees_like_id
                    else ""
                )
                self.ws.cell(row, 18, category)
                if is_cruiser:
                    plate = ("W" + str(rider.plate_champ_24)) if rider.plate_champ_24 else rider.plate_display
                    self.ws.cell(row, 21, plate)
                    self.ws.cell(row, 22, rider.transponder_24)
                else:
                    plate = ("W" + str(rider.plate_champ_20)) if rider.plate_champ_20 else rider.plate_display
                    self.ws.cell(row, 19, plate)
                    self.ws.cell(row, 20, rider.transponder_20)
                row += 1

        self._save_workbook(file_name)
        self.event.rem_entries = file_name
        self.event.rem_entries_created = timezone.now()
        self.event.save()
