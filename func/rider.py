from rider.models import Rider
from datetime import date

def set_all_riders_classes():
    """ Function for setiing classes for all riders """
    riders = Rider.objects.all()
    for rider in riders:
        rider.set_class_20()
        rider.set_class_24()
    print ("Kategorie jezdců nastaveny")

def clear_transponders():
    """ Function for clearing transponders field from nan value"""
    riders = Rider.objects.all()
    for rider in riders:
        if rider.transponder_20 == "nan":
            rider.transponder_20 = ""
        if rider.transponder_24 == "nan":
            rider.transponder_24 = ""
        rider.created = date.today()
        #rider.approwed_by = 1
        rider.save()
