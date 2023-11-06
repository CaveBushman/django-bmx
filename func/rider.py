from rider.models import Rider
from datetime import date
import threading

def set_all_riders_classes():
    """ Function for setting classes for all riders """
    riders = Rider.objects.all()
    for rider in riders:
        threading.Thread(target=rider.set_class_beginner(rider)).start()
        threading.Thread(target=rider.set_class_20(rider)).start()
        threading.Thread(target=rider.set_class_24(rider)).start()
    print("Kategorie jezdců nastaveny")

def clear_transponders():
    """ Function for clearing transponders field from nan value """
    riders = Rider.objects.all()
    for rider in riders:
        if rider.transponder_20 == "nan":
            rider.transponder_20 = ""
        if rider.transponder_24 == "nan":
            rider.transponder_24 = ""
        rider.created = date.today()
        rider.save()
