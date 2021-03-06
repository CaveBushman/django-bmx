from django.conf import settings
from django.core.mail import send_mail
from .models import Entry, Event
from rider.models import Rider
from .func import *
from datetime import date, datetime, time, timezone
import stripe
import os
import json


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
    """ Class for sending e-mail about registration """
    stripe.api_key = settings.STRIPE_SECRET_KEY

    def __init__(self, transaction_id):
        self.transaction_id = transaction_id

    def get_customers_email(self):
        """ Method for getting customer e-mail from stripe transaction """
        transaction_detail = stripe.checkout.Session.retrieve(self.transaction_id,)
        transaction_json = json.loads(str(transaction_detail))
        return transaction_json['customer_details']['email']

    def get_event_id(self):
        """ Method for getting event ID from Entry database table"""
        transaction = Entry.objects.filter(transaction_id=self.transaction_id)
        return transaction[0].event

    def get_message_body(self):
        """ Method for setting e-mail MESSAGE_BODY """
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
            message_body += " \r\n"
            message_body += " \r\n"
            message_body += "- do kategorie Challenge, Junior, Under a Elite byly p??ihl????eni tito jezdci: "
            for rider_20 in riders_20:
                message_body += f"{rider_20.last_name.upper()} {rider_20.first_name}, UCI ID: {rider_20.uci_id}, v kategorii {rider_20.class_20}, "
        del entries_20

        if riders_24:
            message_body += " \r\n"
            message_body += " \r\n"
            message_body += "- do kategorie Cruiser byly p??ihl????eni tito jezdci: "
            for rider_24 in riders_24:
                message_body += f"{rider_24.last_name.upper()} {rider_24.first_name}, UCI ID: {rider_24.uci_id}, v kategorii {rider_24.class_20}, "
        del entries_24
        return message_body

    def send_email(self):
        """ Method for sending e-mail with confirm registration - transaction ID required at creating instance """
        recipient = self.get_customers_email()
        message = self.get_message_body()
        event = Event.objects.get(id=self.get_event_id())
        MESSAGE_SUBJECT = f"TEST!!! Potvrzen?? o registraci jezdc?? na z??vod BMX race - {event.name}"
        MESSAGE_BODY = f"Do z??vodu -- {event.name} -- konan??ho dne {event.date} byly registrov??ni: " + message + "\r\n \r\n David Pr????a "

        # TODO: Dod??lat pdf potvrzen?? p????lohou
        # TODO: Dod??lat MESSAGE_BODY v HTML

        # send an email
        send_mail (
             subject = MESSAGE_SUBJECT,
             message = MESSAGE_BODY,
             from_email = "bmx@ceskysvazcyklistiky.cz",
             recipient_list = [recipient],)
        del event
