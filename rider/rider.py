import datetime
import requests
import re
from decouple import config
from rider.models import Rider
from event.models import Result, Event
import threading
from django.utils import timezone

now = datetime.date.today().year

class CheckValidLicenceThread (threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)
    
    def run(self):
        riders = Rider.objects.filter(is_active = True)
        for rider in riders:
            LICENCE_USERNAME = config('LICENCE_USERNAME')
            LICENCE_PASSWORD = config('LICENCE_PASSWORD')
            basicAuthCredentials = (LICENCE_USERNAME, LICENCE_PASSWORD)
 
            url_uciid = (f'https://data.ceskysvazcyklistiky.cz/licence-api/is-valid?uciId={rider.uci_id}&year={now}')
            print (f"Kontroluji platnost licence jezdce {rider.first_name} {rider.last_name}")
            try:
                dataJSON = requests.get(url_uciid, auth=basicAuthCredentials, verify=False)
                if dataJSON.text == "false":
                    rider.valid_licence = False
                    rider.save()
                elif re.search("Http_NotFound", dataJSON.text):
                    print(f"UCI ID {rider.uci_id} NEEXISTUJE V DATABÁZI ČSC")
                    rider.valid_licence = False
                    rider.save()
                else:
                    rider.valid_licence = True
                    rider.save()
            except:
                print("CHYBA PŘI OVĚŘOVÁNÍ PLATNOSTI LICENCE")

def valid_licence(uci_id):
    """ Function for checking valid UCI ID in API ČSC,  PARAMS: UCI ID """
    rider = Rider.objects.get(uci_id=uci_id)

    LICENCE_USERNAME = config('LICENCE_USERNAME')
    LICENCE_PASSWORD = config('LICENCE_PASSWORD')
    basicAuthCredentials = (LICENCE_USERNAME, LICENCE_PASSWORD)
 
    url_uciid = (f'https://data.ceskysvazcyklistiky.cz/licence-api/is-valid?uciId={rider.uci_id}&year={now}')

    try:
        dataJSON = requests.get(url_uciid, auth=basicAuthCredentials, verify=False)
        if dataJSON.text == "false":
            rider.valid_licence = False
            rider.save()
        elif re.search("Http_NotFound", dataJSON.text):
            print(f"UCI ID {uci_id} NEEXISTUJE V DATABÁZI ČSC")
            rider.valid_licence = False
            rider.save()
        else:
            rider.valid_licence = True
            rider.save()
    except:
        print("CHYBA PŘI OVĚŘOVÁNÍ PLATNOSTI LICENCE")
        

def valid_licence_control():
    """ Function for controling validations licence """
    riders = Rider.objects.filter(is_active = True)

    for rider in riders:
        threading.Thread(target = valid_licence(rider.uci_id), daemon = True).start()

def two_years_inactive():
    """ Function for find two years inactive riders """
    # riders = Rider.objects.filter(is_active=True, is_approwe=True, created__lt = timezone.now()-datetime.timedelta(days=730))
    riders = Rider.objects.filter(is_active=True, is_approwe=True)
    last_two_years_events = Event.objects.filter(date__gte=timezone.now() - datetime.timedelta(days=730))
    print(f"Počet závodů za poslední dva roky: {last_two_years_events.count()}")
    inactive_riders = []
    for rider in riders:
        active = False
        for event in last_two_years_events:
            activities = Result.objects.filter(rider=rider.uci_id, event = event.id )
            if activities.count()>0:
                active=True
            if active:
                break   
        if not active:
            inactive_riders.append(rider)
            print(f"Neaktivní jezdec {rider.last_name} {rider.first_name}")
    print (inactive_riders)
    return inactive_riders