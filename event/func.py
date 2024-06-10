from datetime import date, datetime
from club.models import Club
from event.models import EntryClasses, Event, Entry, SeasonSettings
from accounts.models import Account
from ranking.ranking import SetRanking
from .entry import EntryClass
from .result import GetResult
from rider.models import Rider
from django.utils import timezone
import threading
import csv


def expire_licence() -> str:
    year = date.today().year
    return f"{year}/12/31"


def rem_expire_licence() -> str:
    year = date.today().year
    return f"31-12-{year}"


def team_name_resolve(club) -> str:
    club = Club.objects.get(team_name=club)
    return club.team_name


def date_of_birth_resolve(rider) -> str:
    date: str = str(rider.date_of_birth).replace('.', '-')
    date = date[8:] + "-" + date[5:7] + "-" + date[:4]
    return date


def date_of_birth_resolve_rem_online(date):
    """Set date of birth to REM format"""
    date: str = str(date)
    date = date[8:] + "." + date[5:7] + "." + date[:4]
    return date


def gender_resolve(rider):
    """ Set gender to BEM format """
    if rider.gender == "Žena":
        return "F"
    else:
        return "M"


def gender_resolve_small_letter(rider):
    """ Set gender to EC form and REM format """
    if rider == "Žena":
        return "f"
    else:
        return "m"


def excel_first_line(ws):
    """ set first line in BEM and Riders list excel file """
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
    """ set first line in REM and Riders list excel file """
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
    ws.cell(1, 1, "Kategorie")
    ws.cell(1, 2, "Křestní jméno")
    ws.cell(1, 3, "Příjmení")
    ws.cell(1, 4, "Datum narození")
    ws.cell(1, 5, "Adresa")

    return ws


def excel_rem_first_line_online(ws):
    """ set first line in REM online entires excel file """
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


def is_registration_open(event):
    """ Function for check, if registration is open"""
    now = timezone.now()  # .strftime("%m/%d/%Y, %H:%M:%S")

    # if results is uploaded, registration is close
    if event.xls_results:
        return False

    # event registration is manually close
    if not event.reg_open:
        return False

    # check, id today is between reg_open_from and reg_open_to
    if (now >= event.reg_open_from) and (
            now <= event.reg_open_to):
        return True
    else:
        return False


def resolve_event_classes(event, rider, is_20, is_beginner=False):
    """ Function for resolve class in event | is_20 = TRUE for 20" bike """
    event_classes = EntryClasses.objects.get(event__id=event.id)

    if is_beginner:
        if rider.class_beginner == "Beginners 1":
            return event_classes.beginners_1
        elif rider.class_beginner == "Beginners 2":
            return event_classes.beginners_2
        elif rider.class_beginner == "Beginners 3":
            return event_classes.beginners_3
        else:
            return event_classes.beginners_4

    if is_20 and (rider.gender == "Muž" or rider.gender == "Ostatní"):
        if rider.class_20 == "Boys 6":
            return event_classes.boys_6
        elif rider.class_20 == "Boys 7":
            return event_classes.boys_7
        elif rider.class_20 == "Boys 8":
            return event_classes.boys_8
        elif rider.class_20 == "Boys 9":
            return event_classes.boys_9
        elif rider.class_20 == "Boys 10":
            return event_classes.boys_10
        elif rider.class_20 == "Boys 11":
            return event_classes.boys_11
        elif rider.class_20 == "Boys 12":
            return event_classes.boys_12
        elif rider.class_20 == "Boys 13":
            return event_classes.boys_13
        elif rider.class_20 == "Boys 14":
            return event_classes.boys_14
        elif rider.class_20 == "Boys 15":
            return event_classes.boys_15
        elif rider.class_20 == "Boys 16":
            return event_classes.boys_16
        elif rider.class_20 == "Men 17-24":
            return event_classes.men_17_24
        elif rider.class_20 == "Men 25-29":
            return event_classes.men_25_29
        elif rider.class_20 == "Men 30-34":
            return event_classes.men_30_34
        elif rider.class_20 == "Men 35 and over":
            return event_classes.men_35_over
        elif rider.class_20 == "Men Junior":
            return event_classes.men_junior
        elif rider.class_20 == "Men Under 23":
            return event_classes.men_u23
        else:
            return event_classes.men_elite

            # Ženy s bonusem
    if is_20 and rider.gender == "Žena" and rider.have_girl_bonus:
        if rider.class_20 == "Girls 7":
            return event_classes.girls_7
        elif rider.class_20 == "Girls 8":
            return event_classes.girls_8
        elif rider.class_20 == "Girls 9":
            return event_classes.girls_9
        elif rider.class_20 == "Girls 10":
            return event_classes.girls_10
        elif rider.class_20 == "Girls 11":
            return event_classes.girls_11
        elif rider.class_20 == "Girls 12":
            return event_classes.girls_12
        elif rider.class_20 == "Girls 13":
            return event_classes.girls_13
        elif rider.class_20 == "Girls 14":
            return event_classes.girls_14
        elif rider.class_20 == "Girls 15":
            return event_classes.girls_15
        elif rider.class_20 == "Girls 16":
            return event_classes.girls_16
        elif rider.class_20 == "Women 17-24":
            return event_classes.women_17_24
        elif rider.class_20 == "Women 25 and over":
            return event_classes.women_25_over
        elif rider.class_20 == "Women Junior":
            return event_classes.women_junior
        elif rider.class_20 == "Women Under 23":
            return event_classes.women_u23
        else:
            return event_classes.women_elite

    # Ženy bez bonusu
    if is_20 and rider.gender == "Žena" and not rider.have_girl_bonus:
        if rider.class_20 == "Girls 7":
            return event_classes.girls_8
        elif rider.class_20 == "Girls 8":
            return event_classes.girls_9
        elif rider.class_20 == "Girls 9":
            return event_classes.girls_10
        elif rider.class_20 == "Girls 10":
            return event_classes.girls_11
        elif rider.class_20 == "Girls 11":
            return event_classes.girls_12
        elif rider.class_20 == "Girls 12":
            return event_classes.girls_13
        elif rider.class_20 == "Girls 13":
            return event_classes.girls_14
        elif rider.class_20 == "Girls 14":
            return event_classes.girls_15
        elif rider.class_20 == "Girls 15":
            return event_classes.girls_16
        elif rider.class_20 == "Girls 16":
            return event_classes.girls_17_24
        elif rider.class_20 == "Women 17-24":
            return event_classes.women_17_24
        elif rider.class_20 == "Women 25 and over":
            return event_classes.girls_24_over
        elif rider.class_20 == "Women Junior":
            return event_classes.women_junior
        elif rider.class_20 == "Women Under 23":
            return event_classes.women_u23
        else:
            return event_classes.women_elite

    if not is_20:
        if rider.class_24 == "Boys 12 and under":
            return event_classes.cr_boys_12_and_under
        elif rider.class_24 == "Boys 13 and 14":
            return event_classes.cr_boys_13_14
        elif rider.class_24 == "Boys 15 and 16":
            return event_classes.cr_boys_15_16
        elif rider.class_24 == "Men 17-24":
            return event_classes.cr_men_17_24
        elif rider.class_24 == "Men 25-29":
            return event_classes.cr_men_25_29
        elif rider.class_24 == "Men 30-34":
            return event_classes.cr_men_30_34
        elif rider.class_24 == "Men 35-39":
            return event_classes.cr_men_35_39
        elif rider.class_24 == "Men 40-44":
            return event_classes.cr_men_40_44
        elif rider.class_24 == "Men 45-49":
            return event_classes.cr_men_45_49
        elif rider.class_24 == "Men 50 and over":
            return event_classes.cr_men_50_and_over
        elif rider.class_24 == "Girls 12 and under":
            return event_classes.cr_girls_12_and_under
        elif rider.class_24 == "Girls 13-16":
            return event_classes.cr_girls_13_16
        elif rider.class_24 == "Women 17-29":
            return event_classes.cr_women_17_29
        elif rider.class_24 == "Women 30-39":
            return event_classes.cr_women_30_39
        else:
            return event_classes.cr_women_40_and_over


def foreign_club_resolve(state):
    """ Function for setting Club based on state code """
    if state == "SVK":
        return "Slovakia - All Clubs"
    elif state == "GER":
        return "Germany - All Clubs"
    elif state == "POL":
        return "Poland - All Clubs"
    elif state == "HUN":
        return "Hungary - All Clubs"
    elif state == "AUT":
        return "Austria - All Clubs"
    elif state == "FRA":
        return "France - All Clubs"
    elif state == "BEL":
        return "Belgium - All Clubs"


def resolve_event_fee(event, rider, is_20, is_beginner=False):
    """ Function for resolve fees in event | is_20 = TRUE for 20" bike """

    event_classes = EntryClasses.objects.get(event=event)

    if is_beginner:
        if rider.class_beginner == "Beginners 1":
            return event_classes.beginners_1_fee
        elif rider.class_beginner == "Beginners 2":
            return event_classes.beginners_2_fee
        elif rider.class_beginner == "Beginners 3":
            return event_classes.beginners_3_fee
        else:
            return event_class.beginners_4_fee

    if is_20 and (rider.gender == "Muž" or rider.gender == "Ostatní"):
        if rider.class_20 == "Boys 6":
            return event_classes.boys_6_fee
        elif rider.class_20 == "Boys 7":
            return event_classes.boys_7_fee
        elif rider.class_20 == "Boys 8":
            return event_classes.boys_8_fee
        elif rider.class_20 == "Boys 9":
            return event_classes.boys_9_fee
        elif rider.class_20 == "Boys 10":
            return event_classes.boys_10_fee
        elif rider.class_20 == "Boys 11":
            return event_classes.boys_11_fee
        elif rider.class_20 == "Boys 12":
            return event_classes.boys_12_fee
        elif rider.class_20 == "Boys 13":
            return event_classes.boys_13_fee
        elif rider.class_20 == "Boys 14":
            return event_classes.boys_14_fee
        elif rider.class_20 == "Boys 15":
            return event_classes.boys_15_fee
        elif rider.class_20 == "Boys 16":
            return event_classes.boys_16_fee
        elif rider.class_20 == "Men 17-24":
            return event_classes.men_17_24_fee
        elif rider.class_20 == "Men 25-29":
            return event_classes.men_25_29_fee
        elif rider.class_20 == "Men 30-34":
            return event_classes.men_30_34_fee
        elif rider.class_20 == "Men 35 and over":
            return event_classes.men_35_over_fee
        elif rider.class_20 == "Men Junior":
            return event_classes.men_junior_fee
        elif rider.class_20 == "Men Under 23":
            return event_classes.men_u23_fee
        else:
            return event_classes.men_elite_fee

            # Ženy s bonusem
    if is_20 and rider.gender == "Žena" and rider.have_girl_bonus:
        if rider.class_20 == "Girls 7":
            return event_classes.girls_7_fee
        elif rider.class_20 == "Girls 8":
            return event_classes.girls_8_fee
        elif rider.class_20 == "Girls 9":
            return event_classes.girls_9_fee
        elif rider.class_20 == "Girls 10":
            return event_classes.girls_10_fee
        elif rider.class_20 == "Girls 11":
            return event_classes.girls_11_fee
        elif rider.class_20 == "Girls 12":
            return event_classes.girls_12_fee
        elif rider.class_20 == "Girls 13":
            return event_classes.girls_13_fee
        elif rider.class_20 == "Girls 14":
            return event_classes.girls_14_fee
        elif rider.class_20 == "Girls 15":
            return event_classes.girls_15_fee
        elif rider.class_20 == "Girls 16":
            return event_classes.girls_16_fee
        elif rider.class_20 == "Women 17-24":
            return event_classes.women_17_24_fee
        elif rider.class_20 == "Women 25 and over":
            return event_classes.women_25_over_fee
        elif rider.class_20 == "Women Junior":
            return event_classes.women_junior_fee
        elif rider.class_20 == "Women Under 23":
            return event_classes.women_u23_fee
        else:
            return event_classes.women_elite_fee

    # Ženy bez bonusu
    if is_20 and rider.gender == "Žena" and not rider.have_girl_bonus:
        if rider.class_20 == "Girls 7":
            return event_classes.girls_8_fee
        elif rider.class_20 == "Girls 8":
            return event_classes.girls_9_fee
        elif rider.class_20 == "Girls 9":
            return event_classes.girls_10_fee
        elif rider.class_20 == "Girls 10":
            return event_classes.girls_11_fee
        elif rider.class_20 == "Girls 11":
            return event_classes.girls_12_fee
        elif rider.class_20 == "Girls 12":
            return event_classes.girls_13_fee
        elif rider.class_20 == "Girls 13":
            return event_classes.girls_14_fee
        elif rider.class_20 == "Girls 14":
            return event_classes.girls_15_fee
        elif rider.class_20 == "Girls 15":
            return event_classes.girls_16_fee
        elif rider.class_20 == "Girls 16":
            return event_classes.women_17_24_fee
        elif rider.class_20 == "Women 17-24":
            return event_classes.women_17_24_fee
        elif rider.class_20 == "Women 25 and over":
            return event_classes.women_25_over_fee
        elif rider.class_20 == "Women Junior":
            return event_classes.women_junior_fee
        elif rider.class_20 == "Women Under 23":
            return event_classes.women_u23_fee
        else:
            return event_classes.women_elite_fee

    # Cruiser
    if not is_20:
        if rider.class_24 == "Boys 12 and under":
            return event_classes.cr_boys_12_and_under_fee
        elif rider.class_24 == "Boys 13 and 14":
            return event_classes.cr_boys_13_14_fee
        elif rider.class_24 == "Boys 15 and 16":
            return event_classes.cr_boys_15_16_fee
        elif rider.class_24 == "Men 17-24":
            return event_classes.cr_men_17_24_fee
        elif rider.class_24 == "Men 25-29":
            return event_classes.cr_men_25_29_fee
        elif rider.class_24 == "Men 30-34":
            return event_classes.cr_men_30_34_fee
        elif rider.class_24 == "Men 35-39":
            return event_classes.cr_men_35_39_fee
        elif rider.class_24 == "Men 40-44":
            return event_classes.cr_men_40_44_fee
        elif rider.class_24 == "Men 45-49":
            return event_classes.cr_men_45_49_fee
        elif rider.class_24 == "Men 50 and over":
            return event_classes.cr_men_50_and_over_fee
        elif rider.class_24 == "Girls 12 and under":
            return event_classes.cr_girls_12_and_under_fee
        elif rider.class_24 == "Girls 13-16":
            return event_classes.cr_girls_13_16_fee
        elif rider.class_24 == "Women 17-29":
            return event_classes.cr_women_17_29_fee
        elif rider.class_24 == "Women 30-39":
            return event_classes.cr_women_30_39_fee
        else:
            return event_classes.cr_women_40_and_over_fee


class SetResults(threading.Thread):
    """ Class for saving results """

    def __init__(self):
        threading.Thread.__init__(self)

    def setFile(self, file):
        self.file = file

    def setEvent(self, event):
        self.event = event

    def run(self):
        event = Event.objects.get(id=self.event)
        ranking_code = GetResult.ranking_code_resolve(type=event.type_for_ranking)
        with open("media/rem_results" + self.file, newline='') as result:
            results_reader = csv.reader(result, delimiter='\t')
            for raw in results_reader:
                # Kategorie Příchozích neboduje do rankingu
                if raw[4].find("Příchozí") == -1 and raw[4].find("Prichozi") == -1 and raw[25].find(
                        "CLASS_RANKING") == -1:
                    uci_id = str(raw[12])
                    category = raw[4]
                    place = str(raw[25])
                    first_name = raw[1]
                    last_name = raw[2]
                    club = raw[3]
                    result = GetResult(event.date, event.id, event.name, ranking_code, uci_id, place, category,
                                       first_name, last_name, club, event.organizer.team_name, event.type_for_ranking)
                    result.write_result()

            event.rem_results = "rem_results" + self.file
            event.save()

            SetRanking().start()


class Cart():
    """ Cart for registering to multiple events """
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


def generate_stripe_line(event, rider, is_20, is_beginner=False):
    """ Function for generation stripe line """

    if is_beginner:
        fee: int = resolve_event_fee(event, rider, is_20=True, is_beginner=True)
        rider.class_beginner = resolve_event_classes(event, rider, is_20=True, is_beginner=True)
        line_item = {
            'price_data': {
                'currency': 'czk',
                'unit_amount': fee * 100,
                'product_data': {
                    'name': rider.last_name + " " + rider.first_name + ", " + rider.class_beginner,
                    'images': [],
                    'description': "UCI ID: " + str(rider.uci_id) + ", " + event.name
                },
            },
            'quantity': 1,
        },
        return line_item

    elif is_20:
        fee: int = resolve_event_fee(event, rider, is_20=True)
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
        },
        return line_item

    else:
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
        },
        return line_item


def clean_classes_on_event(event):
    """ Function for return classes used in event """
    classes = []
    if event.is_beginners_event():
        classes += [event.classes_and_fees_like.beginners_1, event.classes_and_fees_like.beginners_2,
                    event.classes_and_fees_like.beginners_3, event.classes_and_fees_like.beginners_4]
    classes += [event.classes_and_fees_like.boys_6, event.classes_and_fees_like.boys_7,
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
                event.classes_and_fees_like.cr_women_40_and_over,
                event.classes_and_fees_like.cr_men_50_and_over, event.classes_and_fees_like.boys_11,
                event.classes_and_fees_like.girls_11, event.classes_and_fees_like.boys_12,
                event.classes_and_fees_like.girls_12, event.classes_and_fees_like.boys_13,
                event.classes_and_fees_like.girls_13, event.classes_and_fees_like.boys_14,
                event.classes_and_fees_like.girls_14, event.classes_and_fees_like.boys_15,
                event.classes_and_fees_like.girls_15, event.classes_and_fees_like.boys_16,
                event.classes_and_fees_like.girls_16, event.classes_and_fees_like.men_17_24,
                event.classes_and_fees_like.women_17_24, event.classes_and_fees_like.men_25_29,
                event.classes_and_fees_like.women_25_over, event.classes_and_fees_like.men_30_34,
                event.classes_and_fees_like.men_35_over, event.classes_and_fees_like.men_junior,
                event.classes_and_fees_like.women_junior, event.classes_and_fees_like.men_u23,
                event.classes_and_fees_like.women_u23, event.classes_and_fees_like.men_elite,
                event.classes_and_fees_like.women_elite]
    classes = list(dict.fromkeys(classes))
    return classes


def update_cart(request):
    sum = Entry.objects.filter(user__id=request.user.id, payment_complete=False).count()
    request.session['orders'] = sum


def save_entries(order, transaction_id):
    """Function for saving entries"""
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
    return


def check_entry_duplicity(event, rider, is_beginner=False, is_20=False, is_24=False):
    """ Function for checking, if rider is confirmed as entries on the event"""
    if is_beginner:
        entries = Entry.objects.filter(event=event, rider=rider, is_beginner=True, payment_complete=True)
        if entries:
            return True
        else:
            return False

    if is_20:
        entries = Entry.objects.filter(event=event, rider=rider, is_20=True, payment_complete=True)
        if entries:
            return True
        else:
            return False

    if is_24:
        entries = Entry.objects.filter(event=event, rider=rider, is_24=True, payment_complete=True)
        if entries:
            return True
        else:
            return False


def set_beginner_class(rider, event): # NOT IN USE NOW
    """ Function for set beginner class """
    age = rider.get_age(rider)
    if age <= 6:
        return resolve_event_classes(event, rider, is_20=True, is_beginner=True)
    elif age <= 10 and rider.created:
        diff = datetime.now().date() - rider.created.date()
        if diff.days > 356:  # if rider have plate more then one year, rider cannot start in Beginners class
            return ""
        else:
            return resolve_event_classes(event, rider, is_20=True, is_beginner=True)
    else:
        return ""


def is_beginner(rider):
    """ Function for resolve, if rider can registration to beginners class """
    entries = Entry.objects.filter(checkout=False, payment_complete=True, is_20=True, rider=rider, event__date__year=datetime.today().year)
    if entries.count() >= 3 or rider.is_elite:
        return False
    else:
        return True


def invalid_licence_in_event(event):
    """ Check invalid licence in event """
    check_20_entries = Entry.objects.filter(event=event.id, is_20=True, payment_complete=1, checkout=False)
    check_24_entries = Entry.objects.filter(event=event.id, is_24=True, payment_complete=1, checkout=False)

    invalid_licences = []

    for check20 in check_20_entries:
        try:
            rider = Rider.objects.get(uci_id=check20.rider)
            if not rider.valid_licence:
                invalid_licences.append(rider)
        except Exception as e:
            pass  # TODO: Dodělat zprávu o chybě

    for check24 in check_24_entries:
        try:
            rider = Rider.objects.get(uci_id=check24.rider)
            if not rider.valid_licence:
                invalid_licences.append(rider)
        except Exception as e:
            pass  # TODO: Dodělat zprávu o chybě

    invalid_licences = set(invalid_licences)  # odstranění duplicit, pokud jezdec jede 20" i 24"

    return invalid_licences


def qualify_riders_to_cn(year, rider):
    """ Function for resolve qualify to CN"""
    qualify = 0
    settings = SeasonSettings.objects.get(year=datetime.today().year)
    entries_20 = Entry.objects.filter(event__type_for_ranking="Český pohár", event__date__year=year, checkout=False,
                                       is_20=True, is_beginner=False, payment_complete=True)

    for entry in entries_20:
        if entry.rider == rider:
            qualify += 1

    if qualify >= settings.qualify_to_cn:
        rider.is_qualify_20 = True
    else:
        rider.is_qualify_20 = False

    entries_24 = Entry.objects.filter(event__type_for_ranking="Český pohár", event__date__year=year, checkout=False,
                                   is_24=True, payment_complete=True)

    for entry in entries_24:
        if entry.rider == rider:
            qualify += 1

    if qualify >= settings.qualify_to_cn:
        rider.is_qualify_24 = True
    else:
        rider.is_qualify_24 = False

    return rider




