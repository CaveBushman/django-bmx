from datetime import date
import requests
import re


def valid_licence(uci_id, username, password):
    """ Function for checking valid UCI ID in API ČSC,  PARAMS: UCI ID """
    basicAuthCredentials = (username, password)
    now = date.today().year
    url_uciid = (f'https://data.ceskysvazcyklistiky.cz/licence-api/is-valid?uciId={uci_id}&year={now}')

    try:
        dataJSON = requests.get(url_uciid, auth=basicAuthCredentials)
        if dataJSON.text == "false":
            return False
        elif re.search("Http_NotFound", dataJSON.text):
            print(f"UCI ID {uci_id} NEEXISTUJE V DATABÁZI ČSC")
            return False
        else:
            return True
    except:
        print("CHYBA PŘI OVĚŘOVÁNÍ PLATNOSTI LICENCE")
        return False
