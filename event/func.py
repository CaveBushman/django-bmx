"""
event/func.py — pomocné funkce pro modul event

Obsah:
  1. Pomocné funkce pro formátování dat (datum, pohlaví, klub)
  2. Záhlaví Excel exportů (BEM, REM, REM online, pojištění)
  3. Registrační logika (je registrace otevřena, rozlišení třídy a poplatku)
  4. Stripe platební integrace (generování řádků košíku)
  5. Správa košíku a přihlášek (Cart, save_entries, check_entry_duplicity)
  6. Validace a admin operace (neplatné licence, kvalifikace, výsledky z REM)
"""

import logging
from datetime import date, datetime
from club.models import Club
from django.conf import settings

logger = logging.getLogger(__name__)
from event.models import EntryClasses, Event, Entry, SeasonSettings
from accounts.models import Account
from ranking.ranking import schedule_ranking_recount
from .entry import EntryClass
from .result import GetResult
from rider.models import Rider
from django.utils import timezone
import threading
import csv
from django.db.models import Q
from django.db import transaction
import os


# ===========================================================================
# 1. FORMÁTOVACÍ POMOCNÉ FUNKCE
# Používají se při generování exportů (BEM, REM, EC) a přepisu dat do formátů
# požadovaných externími systémy.
# ===========================================================================

def expire_licence() -> str:
    """Vrátí datum expirace licence ve formátu YYYY/MM/DD (používá BEM export)."""
    year = date.today().year
    return f"{year}/12/31"


def rem_expire_licence() -> str:
    """Vrátí datum expirace licence ve formátu DD-MM-YYYY (používá REM export)."""
    year = date.today().year
    return f"31-12-{year}"


def team_name_resolve(club) -> str:
    """Vrátí název týmu z objektu Club (nebo z názvu klubu jako řetězec)."""
    if not club:
        return ""
    if hasattr(club, "team_name"):
        return club.team_name or ""
    resolved = Club.objects.filter(team_name=club).first()
    return resolved.team_name if resolved else str(club)


def date_of_birth_resolve(rider) -> str:
    """Přeformátuje datum narození z YYYY-MM-DD na DD-MM-YYYY (pro BEM export)."""
    date: str = str(rider.date_of_birth).replace('.', '-')
    date = date[8:] + "-" + date[5:7] + "-" + date[:4]
    return date


def date_of_birth_resolve_rem_online(date):
    """Přeformátuje datum narození z YYYY-MM-DD na DD.MM.YYYY (pro REM online export)."""
    date: str = str(date)
    date = date[8:] + "." + date[5:7] + "." + date[:4]
    return date


def gender_resolve(rider):
    """Vrátí pohlaví ve formátu F/M (pro BEM export)."""
    if rider.gender == "Žena":
        return "F"
    else:
        return "M"


def gender_resolve_small_letter(rider):
    """Vrátí pohlaví malým písmenem f/m (pro EC formulář a REM online export)."""
    if rider == "Žena":
        return "f"
    else:
        return "m"


def foreign_club_resolve(state):
    """Vrátí název zahraničního klubu podle kódu státu (pro BEM export)."""
    clubs = {
        "SVK": "Slovakia - All Clubs",
        "GER": "Germany - All Clubs",
        "POL": "Poland - All Clubs",
        "HUN": "Hungary - All Clubs",
        "AUT": "Austria - All Clubs",
        "FRA": "France - All Clubs",
        "BEL": "Belgium - All Clubs",
    }
    return clubs.get(state, "")


# ===========================================================================
# 2. ZÁHLAVÍ EXCEL EXPORTŮ
# Každá funkce nastaví záhlaví prvního řádku v konkrétním XLS exportu.
# ===========================================================================

def excel_first_line(ws):
    """Záhlaví pro BEM (Bike Event Manager) export jezdců."""
    ws.cell(1, 1, "Licence_num")
    ws.cell(1, 2, "UCI_ID")
    ws.cell(1, 3, "UCIcode")
    ws.cell(1, 4, "FederationID")
    ws.cell(1, 5, "International Licence Code")
    ws.cell(1, 6, "Expiry_date")
    ws.cell(1, 7, "Licence_type")
    ws.cell(1, 8, "Status")
    ws.cell(1, 9, "Dob")
    ws.cell(1, 10, "First_name")
    ws.cell(1, 11, "Surname")
    ws.cell(1, 12, "Email")
    ws.cell(1, 13, "Phone")
    ws.cell(1, 14, "Emergency Contact Person")
    ws.cell(1, 15, "Emergency Contact Number")
    ws.cell(1, 16, "Sex")
    ws.cell(1, 17, "CLUB")
    ws.cell(1, 18, "State")
    ws.cell(1, 19, "UCI_Country")
    ws.cell(1, 20, "Class")
    ws.cell(1, 21, "Class2")
    ws.cell(1, 22, "Class3")
    ws.cell(1, 23, "Class4")
    ws.cell(1, 24, "Plate")
    ws.cell(1, 25, "Plate2")
    ws.cell(1, 26, "Plate3")
    ws.cell(1, 27, "Plate4")
    ws.cell(1, 28, "Ranking")
    ws.cell(1, 29, "Ranking2")
    ws.cell(1, 30, "Ranking3")
    ws.cell(1, 31, "Ranking4")
    ws.cell(1, 32, "Transponder")
    ws.cell(1, 33, "Transponder2")
    ws.cell(1, 34, "Transponder3")
    ws.cell(1, 35, "Transponder4")
    ws.cell(1, 36, "Tlabel")
    ws.cell(1, 37, "Tlabel2")
    ws.cell(1, 38, "Tlabel3")
    ws.cell(1, 39, "Tlabel4")
    ws.cell(1, 40, "Reference")
    ws.cell(1, 41, "Team_No")
    ws.cell(1, 42, "Team2_No")
    ws.cell(1, 43, "Team3_No")
    ws.cell(1, 44, "Team4_No")
    ws.cell(1, 45, "Sponsor")
    ws.cell(1, 46, "Comment")
    ws.cell(1, 47, "Medical Suspension")
    ws.cell(1, 48, "Disciplinary Suspension")
    ws.cell(1, 49, "Other Suspension")
    ws.cell(1, 50, "POA Suspension")
    ws.cell(1, 51, "Suspension End Date")
    ws.cell(1, 52, "AdvancedRider")
    return ws


def excel_rem_first_line(ws):
    """Záhlaví pro REM (Race Entry Manager) export jezdců."""
    ws.cell(1, 1, "CLUB_DESCRIPTION")
    ws.cell(1, 2, "TEAM_DESCRIPTION")
    ws.cell(1, 3, "RIDER_FIRST")
    ws.cell(1, 4, "RIDER_LAST")
    ws.cell(1, 5, "RIDER_SEX")
    ws.cell(1, 6, "RIDER_BIRTHDATE")
    ws.cell(1, 7, "RIDER_MAIL")
    ws.cell(1, 8, "RIDER_TYPE")
    ws.cell(1, 9, "RIDER_LICENCE_TYPE")
    ws.cell(1, 10, "RIDER_UCIID")
    ws.cell(1, 11, "RIDER_UCIID_EXP_DATE")
    ws.cell(1, 12, "RIDER_PLATE1")
    ws.cell(1, 13, "RIDER_CHAMP_PLATE1")
    ws.cell(1, 14, "RIDER_TRANSPONDER1")
    ws.cell(1, 15, "RIDER_PLATE2")
    ws.cell(1, 16, "RIDER_CHAMP_PLATE2")
    ws.cell(1, 17, "RIDER_TRANSPONDER2")
    ws.cell(1, 18, "RIDER_PLATE3")
    ws.cell(1, 19, "RIDER_CHAMP_PLATE3")
    ws.cell(1, 20, "RIDER_TRANSPONDER3")
    ws.cell(1, 21, "RIDER_IDENT")
    ws.cell(1, 22, "RIDER_ACTIVE")
    ws.cell(1, 23, "RIDER_LOCKED")
    return ws


def insurance_first_line(ws):
    """Záhlaví pro export pojistného seznamu."""
    ws.cell(1, 1, "Kategorie")
    ws.cell(1, 2, "Křestní jméno")
    ws.cell(1, 3, "Příjmení")
    ws.cell(1, 4, "Datum narození")
    ws.cell(1, 5, "Adresa")
    return ws


def excel_rem_first_line_online(ws):
    """Záhlaví pro REM online přihlášky (export z online přihlašovacího systému)."""
    ws.cell(1, 1, "uci_id")
    ws.cell(1, 2, "uci_code")
    ws.cell(1, 3, "first_name")
    ws.cell(1, 4, "last_name")
    ws.cell(1, 5, "email")
    ws.cell(1, 6, "club")
    ws.cell(1, 7, "country")
    ws.cell(1, 8, "date_of_birth")
    ws.cell(1, 9, "sex")
    ws.cell(1, 10, "event")
    ws.cell(1, 11, "event_date")
    ws.cell(1, 12, "paid")
    ws.cell(1, 13, "event_price")
    ws.cell(1, 14, "admin_fee")
    ws.cell(1, 15, "transponder_hire_price")
    ws.cell(1, 16, "team_sponsor")
    ws.cell(1, 17, "class_0")
    ws.cell(1, 18, "transponder_0")
    ws.cell(1, 19, "transponderhire_0")
    ws.cell(1, 20, "plate_0")
    ws.cell(1, 21, "class_1")
    ws.cell(1, 22, "transponder_1")
    ws.cell(1, 23, "transponderhire_1")
    ws.cell(1, 24, "plate_1")
    return ws


# ===========================================================================
# 3. REGISTRAČNÍ LOGIKA — OTEVŘENÍ REGISTRACE, TŘÍDA A POPLATEK
# Tyto funkce se používají při přihlašování jezdce na závod.
# ===========================================================================

def is_registration_open(event) -> bool:
    """Vrátí True pokud je nyní otevřena online registrace na daný závod.

    Registrace je ZAVŘENA pokud:
    - Jsou nahrány výsledky závodu (xls_results)
    - reg_open je ručně vypnuto adminem
    - Aktuální čas je mimo interval reg_open_from–reg_open_to
    """
    now = timezone.now()

    if event.xls_results:
        return False  # Po nahrání výsledků zavřít registraci

    if not event.reg_open:
        return False  # Admin ručně zavřel registraci

    try:
        return event.reg_open_from <= now <= event.reg_open_to
    except (TypeError, AttributeError):
        return False


def _get_event_classes(event):
    """Vrátí cacheovaný EntryClasses objekt pro daný závod."""
    cached = getattr(event, "_cached_entry_classes", None)
    if cached is not None:
        return cached

    event_classes = getattr(event, "classes_and_fees_like", None)
    if event_classes is None:
        event_classes = EntryClasses.objects.filter(event__id=event.id).first()

    event._cached_entry_classes = event_classes
    return event_classes


def resolve_event_classes(event, rider, is_20, is_beginner=False):
    """Vrátí název třídy závodníka pro daný závod (z tabulky EntryClasses).

    Mapování:
    - is_beginner=True → třída začátečníků (Beginners 1–4)
    - is_20=True + muž/ostatní → standardní třída 20"
    - is_20=True + žena → třída žen 20" bez jakéhokoli posunu
    - is_20=False → třída Cruiser (24")
    """
    event_classes = _get_event_classes(event)

    if is_beginner:
        mapping = {
            "Beginners 1": event_classes.beginners_1,
            "Beginners 2": event_classes.beginners_2,
            "Beginners 3": event_classes.beginners_3,
        }
        return mapping.get(rider.class_beginner, event_classes.beginners_4)

    if is_20 and (rider.gender == "Muž" or rider.gender == "Ostatní"):
        mapping = {
            "Boys 6": event_classes.boys_6,
            "Boys 7": event_classes.boys_7,
            "Boys 8": event_classes.boys_8,
            "Boys 9": event_classes.boys_9,
            "Boys 10": event_classes.boys_10,
            "Boys 11": event_classes.boys_11,
            "Boys 12": event_classes.boys_12,
            "Boys 13": event_classes.boys_13,
            "Boys 14": event_classes.boys_14,
            "Boys 15": event_classes.boys_15,
            "Boys 16": event_classes.boys_16,
            "Men 17-24": event_classes.men_17_24,
            "Men 25-29": event_classes.men_25_29,
            "Men 30-34": event_classes.men_30_34,
            "Men 35 and over": event_classes.men_35_over,
            "Men Junior": event_classes.men_junior,
            "Men Under 23": event_classes.men_u23,
        }
        return mapping.get(rider.class_20, event_classes.men_elite)

    if is_20 and rider.gender == "Žena":
        mapping = {
            "Girls 6": event_classes.girls_6,
            "Girls 7": event_classes.girls_7,
            "Girls 8": event_classes.girls_8,
            "Girls 9": event_classes.girls_9,
            "Girls 10": event_classes.girls_10,
            "Girls 11": event_classes.girls_11,
            "Girls 12": event_classes.girls_12,
            "Girls 13": event_classes.girls_13,
            "Girls 14": event_classes.girls_14,
            "Girls 15": event_classes.girls_15,
            "Girls 16": event_classes.girls_16,
            "Women 17-24": event_classes.women_17_24,
            "Women 25 and over": event_classes.women_25_over,
            "Women Junior": event_classes.women_junior,
            "Women Under 23": event_classes.women_u23,
        }
        return mapping.get(rider.class_20, event_classes.women_elite)

    # Cruiser (24" kolo)
    if not is_20:
        mapping = {
            "Boys 12 and under": event_classes.cr_boys_12_and_under,
            "Boys 13 and 14": event_classes.cr_boys_13_14,
            "Boys 15 and 16": event_classes.cr_boys_15_16,
            "Men 17-24": event_classes.cr_men_17_24,
            "Men 25-29": event_classes.cr_men_25_29,
            "Men 30-34": event_classes.cr_men_30_34,
            "Men 35-39": event_classes.cr_men_35_39,
            "Men 40-44": event_classes.cr_men_40_44,
            "Men 45-49": event_classes.cr_men_45_49,
            "Men 50 and over": event_classes.cr_men_50_and_over,
            "Girls 12 and under": event_classes.cr_girls_12_and_under,
            "Girls 13-16": event_classes.cr_girls_13_16,
            "Women 17-29": event_classes.cr_women_17_29,
            "Women 30-39": event_classes.cr_women_30_39,
        }
        return mapping.get(rider.class_24, event_classes.cr_women_40_and_over)


def resolve_event_fee(event, rider, is_20, is_beginner=False):
    """Vrátí výši startovného pro závodníka na daném závodu.

    Ženy jedou svoji vlastní věkovou kategorii bez posunu.
    """
    event_classes = _get_event_classes(event)

    if is_beginner:
        mapping = {
            "Beginners 1": event_classes.beginners_1_fee,
            "Beginners 2": event_classes.beginners_2_fee,
            "Beginners 3": event_classes.beginners_3_fee,
        }
        return mapping.get(rider.class_beginner, event_classes.beginners_4_fee)

    if is_20 and (rider.gender == "Muž" or rider.gender == "Ostatní"):
        mapping = {
            "Boys 6": event_classes.boys_6_fee,
            "Boys 7": event_classes.boys_7_fee,
            "Boys 8": event_classes.boys_8_fee,
            "Boys 9": event_classes.boys_9_fee,
            "Boys 10": event_classes.boys_10_fee,
            "Boys 11": event_classes.boys_11_fee,
            "Boys 12": event_classes.boys_12_fee,
            "Boys 13": event_classes.boys_13_fee,
            "Boys 14": event_classes.boys_14_fee,
            "Boys 15": event_classes.boys_15_fee,
            "Boys 16": event_classes.boys_16_fee,
            "Men 17-24": event_classes.men_17_24_fee,
            "Men 25-29": event_classes.men_25_29_fee,
            "Men 30-34": event_classes.men_30_34_fee,
            "Men 35 and over": event_classes.men_35_over_fee,
            "Men Junior": event_classes.men_junior_fee,
            "Men Under 23": event_classes.men_u23_fee,
        }
        return mapping.get(rider.class_20, event_classes.men_elite_fee)

    if is_20 and rider.gender == "Žena":
        mapping = {
            "Girls 6": event_classes.girls_6_fee,
            "Girls 7": event_classes.girls_7_fee,
            "Girls 8": event_classes.girls_8_fee,
            "Girls 9": event_classes.girls_9_fee,
            "Girls 10": event_classes.girls_10_fee,
            "Girls 11": event_classes.girls_11_fee,
            "Girls 12": event_classes.girls_12_fee,
            "Girls 13": event_classes.girls_13_fee,
            "Girls 14": event_classes.girls_14_fee,
            "Girls 15": event_classes.girls_15_fee,
            "Girls 16": event_classes.girls_16_fee,
            "Women 17-24": event_classes.women_17_24_fee,
            "Women 25 and over": event_classes.women_25_over_fee,
            "Women Junior": event_classes.women_junior_fee,
            "Women Under 23": event_classes.women_u23_fee,
        }
        return mapping.get(rider.class_20, event_classes.women_elite_fee)

    # Cruiser (24" kolo)
    if not is_20:
        mapping = {
            "Boys 12 and under": event_classes.cr_boys_12_and_under_fee,
            "Boys 13 and 14": event_classes.cr_boys_13_14_fee,
            "Boys 15 and 16": event_classes.cr_boys_15_16_fee,
            "Men 17-24": event_classes.cr_men_17_24_fee,
            "Men 25-29": event_classes.cr_men_25_29_fee,
            "Men 30-34": event_classes.cr_men_30_34_fee,
            "Men 35-39": event_classes.cr_men_35_39_fee,
            "Men 40-44": event_classes.cr_men_40_44_fee,
            "Men 45-49": event_classes.cr_men_45_49_fee,
            "Men 50 and over": event_classes.cr_men_50_and_over_fee,
            "Girls 12 and under": event_classes.cr_girls_12_and_under_fee,
            "Girls 13-16": event_classes.cr_girls_13_16_fee,
            "Women 17-29": event_classes.cr_women_17_29_fee,
            "Women 30-39": event_classes.cr_women_30_39_fee,
        }
        return mapping.get(rider.class_24, event_classes.cr_women_40_and_over_fee)


def clean_classes_on_event(event):
    """Vrátí seznam unikátních tříd, které jsou skutečně použity na závodě.

    Načítá třídy z EntryClasses propojeného se závodem a odstraňuje duplicity.
    Používá se v šabloně pro zobrazení startovní listiny.
    """
    classes = []
    if event.is_beginners_event():
        classes += [
            event.classes_and_fees_like.beginners_1,
            event.classes_and_fees_like.beginners_2,
            event.classes_and_fees_like.beginners_3,
            event.classes_and_fees_like.beginners_4,
        ]
    classes += [
        event.classes_and_fees_like.boys_6, event.classes_and_fees_like.boys_7,
        event.classes_and_fees_like.girls_7, event.classes_and_fees_like.boys_8,
        event.classes_and_fees_like.girls_8, event.classes_and_fees_like.boys_9,
        event.classes_and_fees_like.girls_9, event.classes_and_fees_like.boys_10,
        event.classes_and_fees_like.girls_10, event.classes_and_fees_like.cr_boys_12_and_under,
        event.classes_and_fees_like.cr_girls_12_and_under, event.classes_and_fees_like.cr_boys_13_14,
        event.classes_and_fees_like.cr_girls_13_16, event.classes_and_fees_like.cr_boys_15_16,
        event.classes_and_fees_like.cr_men_17_24, event.classes_and_fees_like.cr_women_17_29,
        event.classes_and_fees_like.cr_men_25_29, event.classes_and_fees_like.cr_men_30_34,
        event.classes_and_fees_like.cr_women_30_39, event.classes_and_fees_like.cr_men_35_39,
        event.classes_and_fees_like.cr_men_40_44, event.classes_and_fees_like.cr_men_45_49,
        event.classes_and_fees_like.cr_women_40_and_over, event.classes_and_fees_like.cr_men_50_and_over,
        event.classes_and_fees_like.boys_11, event.classes_and_fees_like.girls_11,
        event.classes_and_fees_like.boys_12, event.classes_and_fees_like.girls_12,
        event.classes_and_fees_like.boys_13, event.classes_and_fees_like.girls_13,
        event.classes_and_fees_like.boys_14, event.classes_and_fees_like.girls_14,
        event.classes_and_fees_like.boys_15, event.classes_and_fees_like.girls_15,
        event.classes_and_fees_like.boys_16, event.classes_and_fees_like.girls_16,
        event.classes_and_fees_like.men_17_24, event.classes_and_fees_like.women_17_24,
        event.classes_and_fees_like.men_25_29, event.classes_and_fees_like.women_25_over,
        event.classes_and_fees_like.men_30_34, event.classes_and_fees_like.men_35_over,
        event.classes_and_fees_like.men_junior, event.classes_and_fees_like.women_junior,
        event.classes_and_fees_like.men_u23, event.classes_and_fees_like.women_u23,
        event.classes_and_fees_like.men_elite, event.classes_and_fees_like.women_elite,
    ]
    # dict.fromkeys zachová pořadí a odstraní duplicity
    classes = list(dict.fromkeys(classes))
    return classes


# ===========================================================================
# 4. STRIPE PLATEBNÍ INTEGRACE
# generate_stripe_line vytvoří jeden řádek pro Stripe Checkout session.
# Každý jezdec / každá přihláška = jeden line_item.
# ===========================================================================

def generate_stripe_line(event, rider, is_20, is_beginner=False):
    """Vygeneruje Stripe line_item slovník pro jednoho závodníka.

    Pro Evropský pohár se odečítá cena pojištění od startovného,
    pokud jezdec již má platné pojištění (have_valid_insurance=True).

    Vrací dict kompatibilní se Stripe Checkout API.
    """
    if is_beginner:
        fee: int = resolve_event_fee(event, rider, is_20=True, is_beginner=True)
        rider.class_beginner = resolve_event_classes(event, rider, is_20=True, is_beginner=True)
        line_item = {
            'price_data': {
                'currency': 'czk',
                'unit_amount': fee * 100,  # Stripe pracuje v haléřích
                'product_data': {
                    'name': rider.last_name + " " + rider.first_name + ", " + rider.class_beginner,
                    'images': [],
                    'description': "UCI ID: " + str(rider.uci_id) + ", " + event.name
                },
            },
            'quantity': 1,
        }
        return line_item

    elif is_20:
        fee: int = resolve_event_fee(event, rider, is_20=True)
        # Odečtení pojištění u Evropského poháru pro pojištěné jezdce
        if event.type_for_ranking == "Evropský pohár" and rider.have_valid_insurance:
            fee = fee - event.price_of_insurance
        rider.class_20 = resolve_event_classes(event, rider, is_20=True)
        line_item = {
            'price_data': {
                'currency': 'czk',
                'unit_amount': fee * 100,
                'product_data': {
                    'name': rider.last_name + " " + rider.first_name + ", " + rider.class_20,
                    'images': [],
                    'description': "UCI ID: " + str(rider.uci_id) + ", " + event.name
                },
            },
            'quantity': 1,
        }
        return line_item

    else:  # Cruiser (24")
        fee: int = resolve_event_fee(event, rider, is_20=False)
        if event.type_for_ranking == "Evropský pohár" and rider.have_valid_insurance:
            fee = fee - event.price_of_insurance
        rider.class_24 = resolve_event_classes(event, rider, is_20=False)
        line_item = {
            'price_data': {
                'currency': 'czk',
                'unit_amount': fee * 100,
                'product_data': {
                    'name': rider.last_name + " " + rider.first_name + ", " + rider.class_24,
                    'images': [],
                    'description': "UCI ID: " + str(rider.uci_id) + ", " + event.name
                },
            },
            'quantity': 1,
        }
        return line_item


# ===========================================================================
# 5. SPRÁVA KOŠÍKU A PŘIHLÁŠEK
# Cart = dočasná přihláška (před zaplacením), Entry = zaplacená přihláška.
# ===========================================================================

class Cart():
    """Dočasná přihláška v košíku — vytvoří Entry záznam s payment_complete=False.

    Po úspěšné platbě se payment_complete nastaví na True (viz webhook).
    """
    user: Account
    event: Event
    rider: Rider
    is_beginner = False
    is_20: bool = False
    is_24: bool = False
    fee_beginner: int = 0
    fee_20: int = 0
    fee_24: int = 0
    class_beginner: str = ""
    class_20: str = ""
    class_24: str = ""
    payment_complete: bool = False

    def save(self):
        """Uloží přihlášku do databáze jako nezaplacenou."""
        Entry.objects.create(
            user=self.user,
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
            payment_complete=self.payment_complete,
        )


def update_cart(request):
    """Aktualizuje čítač nezaplacených přihlášek v session (zobrazení v navigaci)."""
    count = Entry.objects.filter(user__id=request.user.id, payment_complete=False).count()
    request.session['orders'] = count


def save_entries(order, transaction_id):
    """Uloží přihlášku jako zaplacenou po dokončení platby.

    Používá se v Stripe webhookovém handleru po přijetí platby.
    """
    entry = EntryClass()
    entry.transaction_id = transaction_id
    entry.event = order.event
    entry.rider = order.rider
    entry.is_beginner = order.is_beginner
    entry.is_20 = order.is_20
    entry.is_24 = order.is_24
    entry.class_beginner = order.class_beginner
    entry.class_20 = order.class_20
    entry.class_24 = order.class_24
    entry.fee_beginner = order.fee_beginner
    entry.fee_20 = order.fee_20
    entry.fee_24 = order.fee_24
    entry.save()


def check_entry_duplicity(event, rider, is_beginner=False, is_20=False, is_24=False) -> bool:
    """Zkontroluje, zda jezdec již má zaplacenou přihlášku na daný závod v dané kategorii.

    Slouží k zamezení duplicitních přihlášek (jezdec se přihlásí dvakrát).
    """
    if is_beginner:
        return Entry.objects.filter(event=event, rider=rider, is_beginner=True, payment_complete=True).exists()
    if is_20:
        return Entry.objects.filter(event=event, rider=rider, is_20=True, payment_complete=True).exists()
    if is_24:
        return Entry.objects.filter(event=event, rider=rider, is_24=True, payment_complete=True).exists()
    return False


def is_beginner(rider) -> bool:
    """Vrátí True pokud jezdec splňuje podmínky pro start v kategorii začátečníků.

    Začátečník = méně než 3 zaplacené přihlášky (20" nebo 24" kolo) a není elite.
    Rok závodu se nezohledňuje — pokud jezdec závodil kdykoli v minulosti, není začátečník.
    """
    entry_count = Entry.objects.filter(
        Q(checkout=False, payment_complete=True, is_20=True, rider=rider) |
        Q(checkout=False, payment_complete=True, is_24=True, rider=rider)
    ).count()
    return entry_count < 3 and not rider.is_elite


# ===========================================================================
# 6. VALIDACE A ADMIN OPERACE
# Funkce pro adminy a komisaře — kontroly licencí, kvalifikace, import výsledků.
# ===========================================================================

def invalid_licence_in_event(event):
    """Vrátí množinu jezdců s neplatnou licencí přihlášených na daný závod.

    Používá se v komisařském přehledu před závodem.
    Kontrolují se pouze čeští jezdci.
    """
    check_20_entries = Entry.objects.filter(
        event=event.id, is_20=True, payment_complete=True, checkout=False
    ).select_related('rider')
    check_24_entries = Entry.objects.filter(
        event=event.id, is_24=True, payment_complete=True, checkout=False
    ).select_related('rider')

    invalid_licences = []

    for entry in check_20_entries:
        if (
            entry.rider
            and (entry.rider.nationality or "").upper() == "CZE"
            and not entry.rider.valid_licence
        ):
            invalid_licences.append(entry.rider)

    for entry in check_24_entries:
        if (
            entry.rider
            and (entry.rider.nationality or "").upper() == "CZE"
            and not entry.rider.valid_licence
        ):
            invalid_licences.append(entry.rider)

    # set() odstraní duplicitu jezdce, který startuje na 20" i 24"
    return set(invalid_licences)


def qualify_riders_to_cn(year, rider):
    """Vypočítá, zda jezdec splnil podmínky kvalifikace na Mistrovství ČR.

    Podmínka: min. počet startů na Českém poháru (dle SeasonSettings.qualify_to_cn).
    Vrátí jezdce s nastavenými atributy is_qualify_20 / is_qualify_24.
    """
    settings = SeasonSettings.objects.filter(year=datetime.today().year).first()
    qualify_threshold = settings.qualify_to_cn if settings else 2

    qualify_20 = Entry.objects.filter(
        event__type_for_ranking="Český pohár",
        event__date__year=year,
        checkout=False,
        is_20=True,
        is_beginner=False,
        payment_complete=True,
        rider__nationality="CZE",
        rider=rider,
    ).count()

    qualify_24 = Entry.objects.filter(
        event__type_for_ranking="Český pohár",
        event__date__year=year,
        checkout=False,
        is_24=True,
        payment_complete=True,
        rider__nationality="CZE",
        rider=rider,
    ).count()

    rider.is_qualify_20 = qualify_20 >= qualify_threshold
    rider.is_qualify_24 = qualify_24 >= qualify_threshold

    return rider


class SetResults(threading.Thread):
    """Thread pro import výsledků z REM TSV souboru do databáze.

    Po importu automaticky naplánuje přepočet rankingu na pozadí.
    Kategorie 'Příchozí' a hlavičkový řádek 'CLASS_RANKING' se přeskakují.
    """

    def __init__(self):
        threading.Thread.__init__(self)

    def setFile(self, file):
        """Nastaví cestu k souboru s výsledky (odstraní úvodní lomítko)."""
        self.file = file.lstrip("/")

    def setEvent(self, event):
        """Nastaví ID závodu, pro který se výsledky importují."""
        self.event = event

    @staticmethod
    def _normalize_value(value):
        if value is None:
            return ""
        return str(value).strip()

    @classmethod
    def _parse_int(cls, value):
        value = cls._normalize_value(value)
        if not value:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @classmethod
    def _parse_float(cls, value):
        value = cls._normalize_value(value)
        if not value:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _parse_phase_float(cls, raw, keys):
        for key in keys:
            parsed = cls._parse_float(raw.get(key))
            if parsed is not None:
                return parsed
        return None

    @classmethod
    def _phase_hill_time(cls, raw, phase, index=None):
        if phase == "MOTO" and index is not None:
            return cls._parse_phase_float(
                raw,
                [
                    f"MOTO{index}_HILL_TIME",
                    f"MOTO{index}_HILLTIME",
                    f"MOTO{index}_START_HILL_TIME",
                    f"MOTO{index}_START_TIME",
                ],
            )
        return cls._parse_phase_float(
            raw,
            [
                f"{phase}_HILL_TIME",
                f"{phase}_HILLTIME",
                f"{phase}_START_HILL_TIME",
                f"{phase}_START_TIME",
            ],
        )

    @classmethod
    def _phase_inter2_time(cls, raw, phase, index=None):
        if phase == "MOTO" and index is not None:
            return cls._parse_phase_float(
                raw,
                [
                    f"MOTO{index}_INTER2_TIME",
                    f"MOTO{index}_INTER2",
                    f"MOTO{index}_FIRST_TURN_TIME",
                    f"MOTO{index}_FIRST_TURN",
                    f"MOTO{index}_SPLIT1_TIME",
                    f"MOTO{index}_SPLIT1",
                    f"MOTO{index}_SPLIT_1_TIME",
                    f"MOTO{index}_SPLIT_1",
                ],
            )
        return cls._parse_phase_float(
            raw,
            [
                f"{phase}_INTER2_TIME",
                f"{phase}_INTER2",
                f"{phase}_FIRST_TURN_TIME",
                f"{phase}_FIRST_TURN",
                f"{phase}_SPLIT1_TIME",
                f"{phase}_SPLIT1",
                f"{phase}_SPLIT_1_TIME",
                f"{phase}_SPLIT_1",
            ],
        )

    @classmethod
    def import_file(cls, event_id, file_path):
        """Importuje REM TSV soubor a vytvoří pouze Result."""
        event = Event.objects.get(id=event_id)
        ranking_code = GetResult.ranking_code_resolve(type=event.type_for_ranking)

        with open(file_path, newline="", encoding="utf-8") as result_file:
            rows = list(csv.DictReader(result_file, delimiter="\t"))

        logger.info(f"REM výsledků celkem: {len(rows)}")

        with transaction.atomic():
            for raw in rows:
                category = cls._normalize_value(raw.get("CLASS"))
                place = cls._normalize_value(raw.get("CLASS_RANKING"))

                # Přeskočit kategorie Příchozí (nebodují do rankingu) a neplatné řádky
                if not category or not place:
                    logger.debug("Přeskočen REM řádek bez CLASS nebo CLASS_RANKING")
                    continue
                if "prichozi" in category.lower() or "příchozí" in category.lower():
                    logger.debug(
                        "Přeskočena příchozí kategorie: %s %s",
                        raw.get("FIRST_NAME"),
                        raw.get("LAST_NAME"),
                    )
                    continue

                try:
                    logger.debug(
                        "Ukládám výsledek: %s %s, pořadí ve třídě: %s",
                        raw.get("FIRST_NAME"),
                        raw.get("LAST_NAME"),
                        place,
                    )
                    result = GetResult(
                        event.date,
                        event.id,
                        event.name,
                        ranking_code,
                        cls._normalize_value(raw.get("UCIID")),
                        place,
                        category,
                        cls._normalize_value(raw.get("FIRST_NAME")),
                        cls._normalize_value(raw.get("LAST_NAME")),
                        cls._normalize_value(raw.get("CLUB")),
                        event.organizer.team_name,
                        event.type_for_ranking,
                    ).write_result()
                except Exception as e:
                    logger.error(f"Chyba při zpracování řádku {raw}: {e}")

    def run(self):
        file_path = os.path.join(settings.MEDIA_ROOT, "rem_results", self.file)
        self.import_file(self.event, file_path)

        # Po importu výsledků spustit přepočet rankingu na pozadí
        schedule_ranking_recount()
        from rider.rider import trigger_cn_qualification_recount_if_needed

        trigger_cn_qualification_recount_if_needed(Event.objects.get(id=self.event))
