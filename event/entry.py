import os
import pandas as pd
from django.conf import settings
import event
from .models import Entry, Event
from rider.models import Rider
from .func import *
from datetime import date, datetime, time, timezone
import stripe
import json
from openpyxl import Workbook


class EntryClass:
    """ Class for saving entries to the Entry table in database """

    def __init__(self):
        self.transaction_id = None
        self.event = None
        self.rider: Rider = None
        self.is_beginner: bool = False
        self.is_20: bool = False
        self.is_24: bool = False
        self.class_beginner: str = None
        self.class_20: str = None
        self.class_24: str = None
        self.fee_beginner: int = 0
        self.fee_20: int = 0
        self.fee_24: int = 0

    def save(self):
        new_entry = Entry.objects.create(
            transaction_id=self.transaction_id,
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
        )
        new_entry.save()


class SendConfirmEmail:
    """ Class for sending e-mail about registration """
    stripe.api_key = settings.STRIPE_SECRET_KEY

    def __init__(self, transaction_id):
        self.transaction_id = transaction_id

    def get_customers_email(self):
        """ Method for getting customer e-mail from stripe transaction """
        transaction_detail = stripe.checkout.Session.retrieve(self.transaction_id, )
        transaction_json = json.loads(str(transaction_detail))
        return transaction_json['customer_details']['email']

    def get_event_id(self):
        """ Method for getting event ID from Entry database table"""
        transaction = Entry.objects.filter(transaction_id=self.transaction_id)
        return transaction[0].event

    def get_message_body(self):
        """ Method for setting e-mail MESSAGE_BODY """
        entries_beginner = Entry.objects.filter(transaction_id=self.transaction_id, is_beginner=True)
        entries_20 = Entry.objects.filter(transaction_id=self.transaction_id, is_20=True)
        entries_24 = Entry.objects.filter(transaction_id=self.transaction_id, is_24=True)

        # list of UCI ID of riders in the same transaction ID
        list_beginner = []
        list_20 = []
        list_24 = []

        for entry_beginner in entries_beginner:
            list_beginner.append(entry_beginner)

        for entry_20 in entries_20:
            list_20.append(entry_20.rider)

        for entry_24 in entries_24:
            list_24.append(entry_24.rider)

        riders_beginner = Rider.objects.filter(uci_id__in=list_beginner)
        riders_20 = Rider.objects.filter(uci_id__in=list_20)
        riders_24 = Rider.objects.filter(uci_id__in=list_24)

        message_body = ""

        if riders_beginner:
            message_body += " \r\n"
            message_body += " \r\n"
            message_body += "- do kategorie Příchozích byly přihlášeni tito jezdci: "
            for rider_beginner in riders_beginner:
                message_body += f"{rider_beginner.last_name.upper()} {rider_beginner.first_name}, UCI ID: {rider_beginner.uci_id}, v kategorii {rider_beginner.class_beginner}, "
        del entries_beginner

        if riders_20:
            message_body += " \r\n"
            message_body += " \r\n"
            message_body += "- do kategorie Challenge, Junior, Under a Elite byly přihlášeni tito jezdci: "
            for rider_20 in riders_20:
                message_body += f"{rider_20.last_name.upper()} {rider_20.first_name}, UCI ID: {rider_20.uci_id}, v kategorii {rider_20.class_20}, "
        del entries_20

        if riders_24:
            message_body += " \r\n"
            message_body += " \r\n"
            message_body += "- do kategorie Cruiser byly přihlášeni tito jezdci: "
            for rider_24 in riders_24:
                message_body += f"{rider_24.last_name.upper()} {rider_24.first_name}, UCI ID: {rider_24.uci_id}, v kategorii {rider_24.class_20}, "
        del entries_24
        return message_body

    def send_email(self):
        """ Method for sending e-mail with confirm registration - transaction ID required at creating instance """
        recipient = self.get_customers_email()
        message = self.get_message_body()
        event = Event.objects.get(id=self.get_event_id())
        MESSAGE_SUBJECT = f"TEST!!! Potvrzení o registraci jezdců na závod BMX race - {event.name}"
        MESSAGE_BODY = f"Do závodu -- {event.name} -- konaného dne {event.date} byly registrováni: " + message + "\r\n \r\n David Průša "

        # TODO: Dodělat pdf potvrzení přílohou
        # TODO: Dodělat MESSAGE_BODY v HTML

        # send an email
        # send_mail (
        #      subject = MESSAGE_SUBJECT,
        #      message = MESSAGE_BODY,
        #      from_email = "bmx@ceskysvazcyklistiky.cz",
        #      recipient_list = [recipient],)
        del event


class NumberInEvent:
    """ Class for number on-line registration riders in event """

    def __init__(self):
        self.riders_in_category = 0
        self.event = 0
        self.category_name = ""

    def count_beginners(self):
        self.riders_in_category = Entry.objects.filter(event=self.event, class_beginner=self.category_name,
                                                       is_beginner=True, payment_complete=True, checkout=False).count()

    def count_riders_20(self):
        """ function for count riders in class """
        self.riders_in_category = Entry.objects.filter(event=self.event, class_20=self.category_name, is_20=True,
                                                       payment_complete=True, checkout=False).count()

    def count_riders_24(self):
        """ function for count riders in class """
        self.riders_in_category = Entry.objects.filter(event=self.event, class_24=self.category_name, is_24=True,
                                                       payment_complete=True, checkout=False).count()


class REMRiders:
    """ Class for create all riders file for REM"""

    def __init__(self):
        self.event = None
        self.file_name = None
        self.wb = Workbook()
        self.wb.encoding = "utf-8"
        self.ws = self.wb.active
        self.ws.title = "REM5_EXT"
        self.riders = Rider.objects.filter(is_active=True, is_approwe=True)

    def remove_temp_file(self):
        try:
            os.remove(f"{self.file_name}")
        except Exception as e:
            print(f"Nebyl nalezen soubor {self.file_name}")

    def first_line(self):
        self.ws.cell(1, 1, "CLUB_DESCRIPTION")
        self.ws.cell(1, 2, "TEAM_DESCRIPTION")
        self.ws.cell(1, 3, "RIDER_FIRST")
        self.ws.cell(1, 4, "RIDER_LAST")
        self.ws.cell(1, 5, "RIDER_SEX")
        self.ws.cell(1, 6, "RIDER_BIRTHDATE")
        self.ws.cell(1, 7, "RIDER_MAIL")
        self.ws.cell(1, 8, "RIDER_TYPE")
        self.ws.cell(1, 9, "RIDER_LICENCE_TYPE")
        self.ws.cell(1, 10, "RIDER_UCIID")
        self.ws.cell(1, 11, "RIDER_UCIID_EXP_DATE")
        self.ws.cell(1, 12, "RIDER_PLATE1")
        self.ws.cell(1, 13, "RIDER_CHAMP_PLATE1")
        self.ws.cell(1, 14, "RIDER_TRANSPONDER1")
        self.ws.cell(1, 15, "RIDER_PLATE2")
        self.ws.cell(1, 16, "RIDER_CHAMP_PLATE2")
        self.ws.cell(1, 17, "RIDER_TRANSPONDER2")
        self.ws.cell(1, 18, "RIDER_PLATE3")
        self.ws.cell(1, 19, "RIDER_CHAMP_PLATE3")
        self.ws.cell(1, 20, "RIDER_TRANSPONDER3")
        self.ws.cell(1, 21, "RIDER_IDENT")
        self.ws.cell(1, 22, "RIDER_ACTIVE")
        self.ws.cell(1, 23, "RIDER_LOCKED")

    def first_line_entries(self):
        """ set first line in REM online entries excel file """
        self.ws.cell(1, 1, "uci_id")
        self.ws.cell(1, 2, "uci_code")
        self.ws.cell(1, 3, "first_name")
        self.ws.cell(1, 4, "last_name")
        self.ws.cell(1, 5, "email")
        self.ws.cell(1, 6, "club")
        self.ws.cell(1, 7, "country")
        self.ws.cell(1, 8, "date_of_birth")
        self.ws.cell(1, 9, "sex")
        self.ws.cell(1, 10, "event")
        self.ws.cell(1, 11, "event_date")
        self.ws.cell(1, 12, "paid")
        self.ws.cell(1, 13, "event_price")
        self.ws.cell(1, 14, "admin_fee")
        self.ws.cell(1, 15, "transponder_hire_price")
        self.ws.cell(1, 16, "team_sponsor")
        self.ws.cell(1, 17, "class_0")
        self.ws.cell(1, 18, "transponder_0")
        self.ws.cell(1, 19, "transponderhire_0")
        self.ws.cell(1, 20, "plate_0")
        self.ws.cell(1, 21, "class_1")
        self.ws.cell(1, 22, "transponder_1")
        self.ws.cell(1, 23, "transponderhire_1")
        self.ws.cell(1, 24, "plate_1")

    def create_all_riders_list(self):
        self.file_name = f'media/rem_riders/REM_RIDERS_LIST_FOR_RACE_ID-{self.event.id}.xlsx'
        self.first_line()

        line: int = 2
        for rider in self.riders:
            self.ws.cell(line, 1, rider.club.team_name)
            self.ws.cell(line, 3, rider.first_name)
            self.ws.cell(line, 4, rider.last_name)
            if rider.gender == "Žena":
                self.ws.cell(line, 5, "F")
            else:
                self.ws.cell(line, 5, "M")
            self.ws.cell(line, 6, event.func.date_of_birth_resolve(rider))
            self.ws.cell(line, 7, )
            if rider.is_elite:
                self.ws.cell(line, 8, "E")
            else:
                self.ws.cell(line, 8, "C")
            self.ws.cell(line, 9, "U")
            self.ws.cell(line, 10, rider.uci_id)
            self.ws.cell(line, 11, event.func.rem_expire_licence())
            self.ws.cell(line, 12, rider.plate)
            self.ws.cell(line, 13, rider.plate_champ_20)
            self.ws.cell(line, 14, rider.transponder_20)
            self.ws.cell(line, 15, rider.plate)
            self.ws.cell(line, 16, rider.plate_champ_24)
            self.ws.cell(line, 17, rider.transponder_24)
            self.ws.cell(line, 18, rider.plate)
            self.ws.cell(line, 19, )
            self.ws.cell(line, 20, )
            self.ws.cell(line, 21, )
            self.ws.cell(line, 22, )
            self.ws.cell(line, 23, )
            line += 1

        self.wb.save(self.file_name)

        # export to tab delimited txt file for import in REM
        file = pd.read_excel(self.file_name)
        file_name_to_txt = self.file_name[:-4] + "txt"
        file.to_csv(file_name_to_txt, sep="\t", index=False)

        self.event.rem_riders_list = file_name_to_txt
        self.event.rem_riders_created = datetime.now()
        self.event.save()

        self.remove_temp_file()

    def create_entries_list(self):
        file_name = f'media/rem_entries/REM_FOR_RACE_ID-{self.event.id}.xlsx'
        self.first_line_entries()
        entries_20 = Entry.objects.filter(event=self.event.id, is_20=True, payment_complete=1, checkout=False)
        row: int = 2
        for entry_20 in entries_20:
            try:
                rider = Rider.objects.get(uci_id=entry_20.rider.uci_id)
                self.ws.cell(row, 1, rider.uci_id)
                self.ws.cell(row, 2, rider.uci_id)
                self.ws.cell(row, 3, rider.first_name)
                self.ws.cell(row, 4, rider.last_name)
                self.ws.cell(row, 5, rider.email)
                self.ws.cell(row, 6, event.func.team_name_resolve(rider.club))
                self.ws.cell(row, 7, "CZE")
                self.ws.cell(row, 8, date_of_birth_resolve_rem_online(rider.date_of_birth))
                self.ws.cell(row, 9, event.func.gender_resolve_small_letter(rider.gender))
                self.ws.cell(row, 10, )
                self.ws.cell(row, 11, )
                self.ws.cell(row, 12, "True")
                self.ws.cell(row, 13, entry_20.fee_20)
                self.ws.cell(row, 14, )
                self.ws.cell(row, 15, )
                self.ws.cell(row, 16, event.func.team_name_resolve(rider.club))
                self.ws.cell(row, 17, entry_20.class_20)
                self.ws.cell(row, 18, rider.transponder_20)
                self.ws.cell(row, 19, )
                if rider.plate_champ_20:
                    world_plate = "W" + str(rider.plate_champ_20)
                    self.ws.cell(row, 20, world_plate)
                else:
                    self.ws.cell(row, 20, rider.plate)
                self.ws.cell(row, 21, )
                self.ws.cell(row, 22, )
                self.ws.cell(row, 23, )
                self.ws.cell(row, 24, )

            except Exception as E:
                print("Chyba při ukládání jezdce do REM: ", E)
            row += 1

        del entries_20

        entries_24 = Entry.objects.filter(event=self.event.id, is_24=True, payment_complete=1, checkout=False)
        for entry_24 in entries_24:
            try:
                rider = Rider.objects.get(uci_id=entry_24.rider.uci_id)
                self.ws.cell(row, 1, rider.uci_id)
                self. ws.cell(row, 2, rider.uci_id)
                self.ws.cell(row, 3, rider.first_name)
                self.ws.cell(row, 4, rider.last_name)
                self.ws.cell(row, 5, rider.email)
                self.ws.cell(row, 6, event.func.team_name_resolve(rider.club))
                self.ws.cell(row, 7, "CZE")
                self.ws.cell(row, 8, date_of_birth_resolve_rem_online(rider.date_of_birth))
                self.ws.cell(row, 9, event.func.gender_resolve_small_letter(rider.gender))
                self.ws.cell(row, 10, )
                self.ws.cell(row, 11, )
                self.ws.cell(row, 12, "True")
                self.ws.cell(row, 13, entry_24.fee_24)
                self.ws.cell(row, 14, )
                self.ws.cell(row, 15, )
                self.ws.cell(row, 16, event.func.team_name_resolve(rider.club))
                self.ws.cell(row, 17, entry_24.class_24)
                self.ws.cell(row, 18, rider.transponder_24)
                self.ws.cell(row, 19, )
                if rider.plate_champ_24:
                    self.ws.cell(row, 20, "W" + str(rider.plate_champ_24))
                else:
                    self.ws.cell(row, 20, rider.plate)
                self.ws.cell(row, 21, )
                self.ws.cell(row, 22, )
                self.ws.cell(row, 23, )
                self.ws.cell(row, 24, rider.plate)

            except Exception as E:
                pass
            row += 1
        del entries_24

        # TODO: Add foreign riders

        self.wb.save(file_name)

        # export to tab delimited txt file for import in REM
        file = pd.read_excel(file_name)
        file_name_to_txt = file_name[:-4] + "txt"
        file.to_csv(file_name_to_txt, sep="\t", index=False)

        self.event.rem_entries = file_name_to_txt
        self.event.rem_entries_created = datetime.now()
        self.event.save()

        self.remove_temp_file()
