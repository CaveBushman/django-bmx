import datetime
import json
import requests
import re
from decouple import config
from openpyxl.workbook import Workbook
from rider.models import Rider
from event.models import Result, Event, Entry, SeasonSettings
import threading
from django.utils import timezone
from django.db.models import Q, Exists, OuterRef

now = datetime.date.today().year
INACTIVE_YEARS = 2  # for inactive riders function


class CheckValidLicenceThread(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        riders = Rider.objects.filter(is_active=True)
        for rider in riders:

            if rider.fix_valid_licence:
                rider.valid_licence = True
                rider.save()

            else:
                valid_licence(rider)


class RiderSetClassesThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        riders = Rider.objects.filter(is_active=True)
        for rider in riders:
            rider.class_beginner = rider.set_class_beginner(rider)
            rider.class_20 = rider.set_class_20(rider)
            rider.class_24 = rider.set_class_24(rider)
            rider.save()


def valid_licence(rider):
    """ Function for checking valid UCI ID in API ČSC,  PARAMS: UCI ID """

    __LICENCE_USERNAME = config('LICENCE_USERNAME')
    __LICENCE_PASSWORD = config('LICENCE_PASSWORD')
    basicAuthCredentials = (__LICENCE_USERNAME, __LICENCE_PASSWORD)

    url_uciid = (f'https://data.ceskysvazcyklistiky.cz/licence-api/is-valid?uciId={rider.uci_id}&year={now}')

    try:
        requests.packages.urllib3.disable_warnings()
        dataJSON = requests.get(url_uciid, auth=basicAuthCredentials, verify=False)
        if dataJSON.text == "false" or dataJSON.status_code != 200:
            print(
                f"UCI ID {rider.uci_id}, jezdec {rider.first_name} {rider.last_name} NEEXISTUJE V DATABÁZI ČSC NEBO NEMÁ PLATNOU LICENCI")
            print(dataJSON.text)
            rider.valid_licence = False
            rider.save()
        elif re.search("Http_NotFound", dataJSON.text):
            print(f"UCI ID {rider.uci_id} NEEXISTUJE V DATABÁZI ČSC")
            rider.valid_licence = False
            rider.save()
        else:
            url_uciid = f"https://data.ceskysvazcyklistiky.cz/licence-api/get-by?uciId={rider.uci_id}"
            data_json = requests.get(url_uciid, auth=basicAuthCredentials, verify=False)
            data_json = data_json.text
            data_json = json.loads(data_json)
            rider.street = data_json['street']
            rider.city = data_json['city']
            rider.zip = data_json['postcode']
            rider.valid_licence = True
            rider.save()
    except Exception as e:
        print(f"CHYBA PŘI OVĚŘOVÁNÍ PLATNOSTI LICENCE: {e}")


def two_years_inactive():
    """ Function for inactive riders """
    two_years_ago = timezone.now() - datetime.timedelta(days=INACTIVE_YEARS * 365)

    # Filtrovat aktivní jezdce
    riders = Rider.objects.filter(
        is_active=True, 
        is_approwe=True
    ).exclude(
        created__gte=timezone.now() - datetime.timedelta(days=365)
    )

    # Subdotaz na kontrolu existence výsledků za poslední dva roky
    recent_results = Result.objects.filter(
        rider=OuterRef('uci_id'),
        event__date__gte=two_years_ago
    )

    # Vrátí pouze jezdce, kteří nemají žádný recentní výsledek
    inactive_riders = riders.annotate(
        has_results=Exists(recent_results)
    ).filter(has_results=False).order_by('club')

    return list(inactive_riders)


class Participation:
    """ Class for count participation riders on events with export to excel file """

    def __init__(self):
        self.wb = Workbook()
        self.ws = self.wb.active

    def first_line(self):
        self.ws.cell(1, 1, "Last_name")
        self.ws.cell(1, 2, "First_name")
        self.ws.cell(1, 3, "UCI ID")
        self.ws.cell(1, 4, "Class_20")
        self.ws.cell(1, 5, "Class_24")
        self.ws.cell(1, 6, "CLub")
        self.ws.cell(1, 7, "MČR")
        self.ws.cell(1, 8, "ČP")
        self.ws.cell(1, 9, "Ostatní")

    def save(self):
        self.wb.save(filename='media/participation/participation.xlsx')

    def calculate(self):
        self.first_line()
        line = 2
        riders = Rider.objects.filter(is_active=True)
        for rider in riders:
            mcr: int = 0
            cp: int = 0
            others: int = 0
            participation = Result.objects.filter(rider=rider.uci_id, date__year=now)
            for part in participation:
                if part.event_type == "Mistrovství ČR jednotlivců":
                    mcr = 1
                elif part.event_type == "Český pohár":
                    cp += 1
                else:
                    others += 1
            self.ws.cell(line, 1, rider.last_name)
            self.ws.cell(line, 2, rider.first_name)
            self.ws.cell(line, 3, rider.uci_id)
            self.ws.cell(line, 4, rider.class_20)
            self.ws.cell(line, 5, rider.class_24)
            self.ws.cell(line, 6, str(rider.club))
            self.ws.cell(line, 7, mcr)
            self.ws.cell(line, 8, cp)
            self.ws.cell(line, 9, others)

            line += 1

    def count(self):
        self.first_line()
        self.calculate()
        self.save()


class Cruiser:
    def __init__(self):
        self.__NUMBER_OF_CUPS = 0
        self.__NUMBER_OF_PCS = 0
        self.year = now

    def set_number_of_cups(self, number):
        self.__NUMBER_OF_CUPS = number

    def set_number_of_peaces(self, number):
        self.__NUMBER_OF_PCS = number

    def calculate_median(self):
        entries = Entry.objects.filter(event__type_for_ranking="Český pohár", is_24=True, event__date__year=self.year,
                                       payment_complete=True, checkout=False).order_by('-rider__date_of_birth')
        cruisers_in_events = []
        for entry in entries:
            if entry.rider not in cruisers_in_events:
                cruisers_in_events.append(entry.rider)
        cruiser_results = []
        ages = []
        position: int = 1
        for cruiser in cruisers_in_events:
            participations = Entry.objects.filter(rider=cruiser, event__type_for_ranking="Český pohár", is_24=True,
                                                  event__date__year=self.year, payment_complete=True, checkout=False)
            if len(participations) >= self.__NUMBER_OF_CUPS:
                cruiser_results.append(cruiser)
                age = cruiser.get_age(cruiser) + 1
                cruiser.age = age
                cruiser.position = position
                ages.append(age)
                position += 1
        return cruiser_results


def first_line_riders_by_club_and_class(ws):
    ws.cell(1, 1, "TEAM NAME")
    ws.cell(1, 2, "BOYS 6")
    ws.cell(1, 3, "BOYS 7")
    ws.cell(1, 4, "GIRLS 7")
    ws.cell(1, 5, "BOYS 8")
    ws.cell(1, 6, "GIRLS 8")
    ws.cell(1, 7, "BOYS 9")
    ws.cell(1, 8, "GIRLS 9")
    ws.cell(1, 9, "BOYS 10")
    ws.cell(1, 10, "GIRLS 10")
    ws.cell(1, 11, "BOYS 11")
    ws.cell(1, 12, "GIRLS 11")
    ws.cell(1, 13, "BOYS 12")
    ws.cell(1, 14, "GIRLS 12")
    ws.cell(1, 15, "BOYS 13")
    ws.cell(1, 16, "GIRLS 13")
    ws.cell(1, 17, "BOYS 14")
    ws.cell(1, 18, "GIRLS 14")
    ws.cell(1, 19, "BOYS 15")
    ws.cell(1, 20, "GIRLS 15")
    ws.cell(1, 21, "BOYS 16")
    ws.cell(1, 22, "GIRLS 16")
    ws.cell(1, 23, 'MEN 17-24')
    ws.cell(1, 24, 'WOMEN 17-24')
    ws.cell(1, 25, 'MEN 25-29')
    ws.cell(1, 26, 'WOMEN 25 AND OVER')
    ws.cell(1, 27, 'MEN 30-34')
    ws.cell(1, 28, 'MEN 35 AND OVER')
    ws.cell(1, 29, 'MEN JUNIOR')
    ws.cell(1, 30, 'WOMEN JUNIOR')
    ws.cell(1, 31, 'MEN UNDER 23')
    ws.cell(1, 32, 'WOMEN UNDER 23')
    ws.cell(1, 33, 'MEN ELITE')
    ws.cell(1, 34, 'WOMEN ELITE')


class RiderQualifyToCNThread(threading.Thread):
    """ Class for set qualify to CN rider's status"""
    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):

        riders = Rider.objects.filter(is_active=True, is_approwe=True)
        year = datetime.datetime.today().year
        settings = SeasonSettings.objects.get(year=year)

        for rider in riders:

            entries_20 = Entry.objects.filter(event__type_for_ranking="Český pohár", event__date__year=year,
                                           checkout=False, rider=rider, is_20=True, is_beginner=False).count()
            entries_24 = Entry.objects.filter(event__type_for_ranking="Český pohár", event__date__year=year,
                                              checkout=False, rider=rider, is_24=True).count()

            rider.is_qualify_to_cn_20 = False
            if entries_20 >= settings.qualify_to_cn:
                rider.is_qualify_to_cn_20 = True

            rider.is_qualify_to_cn_24 = False
            if entries_24 >= settings.qualify_to_cn:
                rider.is_qualify_to_cn_24 = True
            rider.save()
