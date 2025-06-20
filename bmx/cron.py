from rider.models import Rider
from rider.rider import valid_licence
import threading

def valid_licence_scheduled():
    
    """ Function for controling validations licence """
    riders = Rider.objects.filter(is_active = True)

    for rider in riders:
        threading.Thread(target = valid_licence(rider.uci_id), daemon = True).start()