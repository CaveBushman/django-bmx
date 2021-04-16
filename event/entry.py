from django.conf import settings
from django.core.mail import send_mail
from .models import Entry, Event
from rider.models import Rider
from .func import *
from datetime import date
import stripe
import os


class EntryClass:
    """ Class for saving entries to the Entry table in database """

    def __init__(self, transaction_id, event, rider, is_20, is_24, class_20, class_24, fee_20=0, fee_24=0):
        self.transaction_id = transaction_id
        self.event = event
        self.rider = rider
        self.is_20 = is_20
        self.is_24 = is_24
        self.class_20 = class_20
        self.class_24 = class_24

    def save(self):

        new_entry = Entry.objects.create(
            transaction_id=self.transaction_id,
            event=self.event,
            rider=self.rider,
            is_20=self.is_20,
            is_24=self.is_24,
            )
        if self.is_20:
            new_entry.class_20 = resolve_event_classes(self.event, self.rider, is_20=True)
        if self.is_24:
            new_entry.class_24 = resolve_event_classes(self.event, self.rider, is_20=False)
        new_entry.save()


class SendConfirmEmail:

    stripe.api_key = settings.STRIPE_SECRET_KEY

    def __init__(self, transaction_id):

        self.transaction_id = transaction_id


    def get_customers_email(self):
        transaction_detail = stripe.checkout.Session.retrieve(
            self.transaction_id,)
        print(transaction_detail)
        return transaction_detail['customer_email']


    def get_message_body(self):
        entries_20 = Entry.objects.filter(transaction_id=self.transaction_id, is_20=True)
        entries_24 = Entry.objects.filter(transaction_id=self.transaction_id, is_24=True)

        # list of UCI ID of riders in the same transaction ID
        list_20 = []
        list_24 = []
        for entry_20 in entries_20:
            list_20.append(entry_20.rider)

        for entry_24 in entries_24:
            list_24.append(entry_24.rider)

        riders_20 = Rider.objects.filter(uci_id__in = list_20)
        riders_24 = Rider.objects.filter(uci_id__in = list_24)

        message_body = ""
        if riders_20:
            message_body += "Do kategorie Challenge, Junior, Under a Elite byly přihlášeni tito jezdci: "
            for rider_20 in riders_20:
                message_body += f"{rider_20.last_name.upper()} {rider_20.first_name}, UCI ID: {rider_20.uci_id}, v kategorii {rider_20.class_20}; "
        message_body += " --- "
        if riders_24:
            message_body += "Do kategorie Cruiser byly přihlášeni tito jezdci: "
            for rider_24 in riders_24:
                message_body += f"{rider_24.last_name.upper()} {rider_24.first_name}, UCI ID: {rider_24.uci_id}, v kategorii {rider_24.class_20}; "

        print(message_body)
        return message_body


    def send_email_about_registration(self):
        recipient = self.get_customers_email
        message = self.get_message_body
        MESSAGE_SUBJECT = "Potvrzení o registraci jezdců na závod BMX race"

        print(f"Příjemce zprávy je {recipient}")

        # send an email
        send_mail (
            subject = MESSAGE_SUBJECT,
            message = message,
            from_email = "bmx@ceskysvazcyklistiky.cz",
            recipient_list = [recipient],
        )
