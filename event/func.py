
from datetime import date
from club.models import Club
from event.models import Event

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
    
    ws.cell(1,1,"Licence_num")
    ws.cell(1,2,"UCI_ID")
    ws.cell(1,3,"UCIcode")
    ws.cell(1,4,"FederationID")
    ws.cell(1,5,"International Licence Code")
    ws.cell(1,6,"Expiry_date")
    ws.cell(1,7,"Licence_type")
    ws.cell(1,8,"Dob")
    ws.cell(1,9,"First_name")
    ws.cell(1,10,"Surname")
    ws.cell(1,11,"Sex")
    ws.cell(1,12,"CLUB")
    ws.cell(1,13,"State")
    ws.cell(1,14,"UCI_Country")
    ws.cell(1,15,"Class")
    ws.cell(1,16,"Class2")
    ws.cell(1,17,"Class3")
    ws.cell(1,18,"Class4")
    ws.cell(1,19,"Plate")
    ws.cell(1,20,"Plate2")
    ws.cell(1,21,"Plate3")
    ws.cell(1,22,"Plate4")
    ws.cell(1,23,"Ranking")
    ws.cell(1,24,"Ranking2")
    ws.cell(1,25,"Ranking3")
    ws.cell(1,26,"Ranking4")
    ws.cell(1,27,"Transponder")
    ws.cell(1,28,"Transponder2")
    ws.cell(1,29,"Transponder3")
    ws.cell(1,30,"Transponder4")
    ws.cell(1,31,"Tlabel")
    ws.cell(1,32,"Tlabel2")
    ws.cell(1,33,"Tlabel3")
    ws.cell(1,34,"Tlabel4")
    ws.cell(1,35,"Reference")
    ws.cell(1,36,"Team_No")
    ws.cell(1,37,"Team2_No")
    ws.cell(1,38,"Team3_No")
    ws.cell(1,39,"Team24_No")
    ws.cell(1,40,"Sponsor")
    ws.cell(1,41,"Comment")
    ws.cell(1,42,"Medical Suspension")
    ws.cell(1,43,"Disciplinary Suspension")
    ws.cell(1,44,"Other Suspension")
    
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