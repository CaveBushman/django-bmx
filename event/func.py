
from datetime import date
import re
from openpyxl import load_workbook
from club.models import Club
from event.models import Event
from rider.models import Rider


def expire_licence():
    year = date.today().year
    return f"{year}/12/31"


def team_name_resolve(club):
    club = Club.objects.get(team_name=club)
    return club.team_name


def gender_resolve(rider):
    if rider == "Muž" or rider == "Ostatní":
        return "M"
    else:
        return "F"


def excel_first_line(ws):

    ws.cell(1, 1, "Licence_num")
    ws.cell(1, 2, "UCI_ID")
    ws.cell(1, 3, "UCIcode")
    ws.cell(1, 4, "FederationID")
    ws.cell(1, 5, "International Licence Code")
    ws.cell(1, 6, "Expiry_date")
    ws.cell(1, 7, "Licence_type")
    ws.cell(1, 8, "Dob")
    ws.cell(1, 9, "First_name")
    ws.cell(1, 10, "Surname")
    ws.cell(1, 11, "Sex")
    ws.cell(1, 12, "CLUB")
    ws.cell(1, 13, "State")
    ws.cell(1, 14, "UCI_Country")
    ws.cell(1, 15, "Class")
    ws.cell(1, 16, "Class2")
    ws.cell(1, 17, "Class3")
    ws.cell(1, 18, "Class4")
    ws.cell(1, 19, "Plate")
    ws.cell(1, 20, "Plate2")
    ws.cell(1, 21, "Plate3")
    ws.cell(1, 22, "Plate4")
    ws.cell(1, 23, "Ranking")
    ws.cell(1, 24, "Ranking2")
    ws.cell(1, 25, "Ranking3")
    ws.cell(1, 26, "Ranking4")
    ws.cell(1, 27, "Transponder")
    ws.cell(1, 28, "Transponder2")
    ws.cell(1, 29, "Transponder3")
    ws.cell(1, 30, "Transponder4")
    ws.cell(1, 31, "Tlabel")
    ws.cell(1, 32, "Tlabel2")
    ws.cell(1, 33, "Tlabel3")
    ws.cell(1, 34, "Tlabel4")
    ws.cell(1, 35, "Reference")
    ws.cell(1, 36, "Team_No")
    ws.cell(1, 37, "Team2_No")
    ws.cell(1, 38, "Team3_No")
    ws.cell(1, 39, "Team24_No")
    ws.cell(1, 40, "Sponsor")
    ws.cell(1, 41, "Comment")
    ws.cell(1, 42, "Medical Suspension")
    ws.cell(1, 43, "Disciplinary Suspension")
    ws.cell(1, 44, "Other Suspension")

    return ws


def is_registration_open(event_id):
    event = Event.objects.get(id=event_id)
    this_date = date.today()

    # if results is uploaded, registraion is close
    if event.results_uploaded:
        return False

    if (this_date >= event.reg_open_from) and (this_date <= event.reg_open_to):
        return True
    return False


def resolve_event_class_20(event, rider):
    event = Event.objects.get(id=event)
    rider = Rider.objects.get(uci_id=rider)

    print("Volám komponentu na kategorii")

    if event.event_type == "Mistrovství ČR jednotlivců":

        if rider.class_20 == "Girls 7" and rider.have_girl_bonus == True:
            return "Boys 6"
        elif (rider.class_20 == "Girls 7" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 8" and rider.have_girl_bonus == True):
            return "Boys 7"
        elif (rider.class_20 == "Girls 8" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 9" and rider.have_girl_bonus == True):
            return "Boys 8"
        elif (rider.class_20 == "Girls 9" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 10" and rider.have_girl_bonus == True):
            return "Boys 9"
        elif (rider.class_20 == "Girls 10" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 11" and rider.have_girl_bonus == True):
            return "Boys 10"
        elif (rider.class_20 == "Girls 11" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 12" and rider.have_girl_bonus == True):
            return "Boys 11"
        elif (rider.class_20 == "Girls 12" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 13" and rider.have_girl_bonus == True):
            return "Boys 12"
        elif (rider.class_20 == "Girls 13" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 14" and rider.have_girl_bonus == True):
            return "Boys 13"
        elif (rider.class_20 == "Girls 14" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 15" and rider.have_girl_bonus == True):
            return "Boys 14"
        elif (rider.class_20 == "Girls 15" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 16" and rider.have_girl_bonus == True):
            return "Boys 15"
        elif (rider.class_20 == "Girls 16" and rider.have_girl_bonus == False):
            return "Boys 16"
        elif re.search("Woman", rider.class_20):
            return "Boys 16"
        elif re.search("Women Under 23", rider.class_20):
            return "Women Elite"
        elif re.search("Men Under 23", rider.class_20):
            return "Men Elite"
        elif rider.class_20 == "Men 17-24" or rider.class_20 == "Men 25-29":
            return "Men 17+"
        elif rider.class_20 =="'Men 30-34" or rider.class_20 == "Men 35 and over":
            return "Men Master 30+"
        else:
            return rider.class_20

    elif event.event_type == "Český pohár":
        if rider.class_20 == "Boys 13" or rider.class_20 == "Boys 14":
            return "Boys 13/14"
        elif rider.class_20 == "Boys 15" or rider.class_20 == "Boys 16" or re.search("Woman", rider.class_20):
            return "Boys 15/16"
        elif re.search("Men Junior", rider.class_20) or re.search("Men Under", rider.class_20) or re.search("Men Elite", rider.class_20):
            if event.is_uci_race:
                return rider.class_20
            else:
                return "Men Junior/Elite"
        elif re.search("Women Junior", rider.class_20) or re.search("Women Under", rider.class_20) or re.search("Women Elite", rider.class_20):
            if event.is_uci_race:
                return rider.class_20
            else:
                return "Boys 15/16"
        elif re.search("Men", rider.class_20):
            return "Men 17+"
        elif rider.class_20 == "Girls 7" and rider.have_girl_bonus == True:
            return "Boys 6"
        elif (rider.class_20 == "Girls 7" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 8" and rider.have_girl_bonus == True):
            return "Boys 7"
        elif (rider.class_20 == "Girls 8" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 9" and rider.have_girl_bonus == True):
            return "Boys 8"
        elif (rider.class_20 == "Girls 9" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 10" and rider.have_girl_bonus == True):
            return "Boys 9"
        elif (rider.class_20 == "Girls 10" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 11" and rider.have_girl_bonus == True):
            return "Boys 10"
        elif (rider.class_20 == "Girls 11" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 12" and rider.have_girl_bonus == True):
            return "Boys 11"
        elif (rider.class_20 == "Girls 12" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 13" and rider.have_girl_bonus == True):
            return "Boys 12"
        elif (rider.class_20 == "Girls 13" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 14" and rider.have_girl_bonus == True):
            return "Boys 13/14"
        elif (rider.class_20 == "Girls 14" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 15" and rider.have_girl_bonus == True):
            return "Boys 13/14"
        elif (rider.class_20 == "Girls 15" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 16" and rider.have_girl_bonus == True):
            return "Boys 15/16"
        elif (rider.class_20 == "Girls 16" and rider.have_girl_bonus == False):
            return "Boys 15/16"
        else:
            return rider.class_20

    elif event.event_type == "Česká liga" or event.event_type == "Moravská liga" or event.event_type == "Mistrovství ČR družstev":
        
        if rider.class_20 == "Boys 11" or rider.class_20 == "Boys 12":
            return "Boys 11/12"
        elif rider.class_20 == "Boys 13" or rider.class_20 == "Boys 14":
            return "Boys 13/14"
        elif rider.class_20 == "Boys 15" or rider.class_20 == "Boys 16" or re.search("Woman", rider.class_20):
            return "Boys 15/16"
        elif re.search("Junior", rider.class_20) or re.search("Under", rider.class_20) or re.search("Elite", rider.class_20):
            return "Men Junior/Elite"
        elif re.search("Men", rider.class_20):
            return "Men 17+"
        elif rider.class_20 == "Girls 7" and rider.have_girl_bonus == True:
            return "Boys 6"
        elif (rider.class_20 == "Girls 7" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 8" and rider.have_girl_bonus == True):
            return "Boys 7"
        elif (rider.class_20 == "Girls 8" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 9" and rider.have_girl_bonus == True):
            return "Boys 8"
        elif (rider.class_20 == "Girls 9" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 10" and rider.have_girl_bonus == True):
            return "Boys 9"
        elif (rider.class_20 == "Girls 10" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 11" and rider.have_girl_bonus == True):
            return "Boys 10"
        elif (rider.class_20 == "Girls 11" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 12" and rider.have_girl_bonus == True):
            return "Boys 11/12"
        elif (rider.class_20 == "Girls 12" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 13" and rider.have_girl_bonus == True):
            return "Boys 11/12"
        elif (rider.class_20 == "Girls 13" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 14" and rider.have_girl_bonus == True):
            return "Boys 13/14"
        elif (rider.class_20 == "Girls 14" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 15" and rider.have_girl_bonus == True):
            return "Boys 13/14"
        elif (rider.class_20 == "Girls 15" and rider.have_girl_bonus == False) or (rider.class_20 == "Girls 16" and rider.have_girl_bonus == True):
            return "Boys 15/16"
        elif (rider.class_20 == "Girls 16" and rider.have_girl_bonus == False):
            return "Boys 15/16"
        else:
            return rider.class_20
    else:
        return rider.class_20


def resolve_event_class_24(event, rider):
    event = Event.objects.get(id=event)
    rider = Rider.objects.get(uci_id=rider)

    if event.event_type == "Mistrovství ČR jednotlivců":
        if rider.class_24 == "Boys 12 and under" or rider.class_24 == "Boys 13 and 14" or rider.class_24 =="Boys 15 a 16" or rider.class_24 =="Girls 12 and under" or rider.class_24 =="Girls 13-16":
            return "Cruiser Mini" 
        elif rider.class_24 == "Men 17-24" or rider.class_24 == "Men 25-29" or rider.class_24 == "Women 17-29":
            return "Cruiser TOP"
        elif rider.class_24 == "Men 30-34" or rider.class_24 == "Men 35-39" or rider.class_24 == "Women 30-39":
            return "Cruiser Master 30+"
        else:
            return "Cruiser Master 40+"

    elif event.event_type == "Český pohár":
        return "Cruiser"

    elif event.event_type == "Česká liga" or event.event_type == "Moravská liga" or event.event_type == "Mistrovství ČR družstev":
        return "Cruiser"
    else:
        return rider.class_24

def resolve_event_classes(event, rider, is_20):

    wb = load_workbook('static/classes/classes.xlsx')
    sheet_range = wb[event.classes_code]   

    if is_20:

        if rider.gender == "Žena" and rider.have_girl_bonus:
            column = 3
        else:
            column = 2

        for row in range (3, 35):
              if rider.class_24 == sheet_range [row][1]:
                  return sheet_range[row][column]


