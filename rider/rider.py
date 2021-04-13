from datetime import date
import requests
import os

class Licence:
    def __init__(self, uci_id):
        self.uci_id = uci_id
    
    def check_valid_licence(self):

        valid = True

        basicAuthCredentials = ("", "")

        now = date.today().year
        url_uciid = (f'https://data.ceskysvazcyklistiky.cz/licence-api/is-valid?uciId={self.uci_id}&year={now}')

        try:
            dataJSON = requests.get(url_uciid, auth=basicAuthCredentials)
            if dataJSON.text == "false":
                print("neplatná licence")
                valid = False

            elif dataJSON.status_code == 404:
                print("neplatná licence")
                valid = False
        except:
            print("Chyba v připojení JSON: ", sys.exc_info()[0])

        return valid
        