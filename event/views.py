import json
import os
from django.shortcuts import render, get_object_or_404, redirect
from .models import Event, Result, Entry
from rider.models import Rider
from django.shortcuts import render, reverse, HttpResponseRedirect
from django.conf import settings
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.views.decorators.csrf import csrf_exempt
from django.contrib.admin.views.decorators import staff_member_required
import pandas as pd
from .result import GetResult
from .func import *
from .entry import EntryClass, SendConfirmEmail
from datetime import date, datetime
from ranking.ranking import RankingCount, RankPositionCount, Categories
import re
from django.core import serializers
from django.http import JsonResponse, HttpResponse
from openpyxl import Workbook
import stripe
import threading

stripe.api_key = settings.STRIPE_SECRET_KEY
endpoint_secret = 'whsec_DXwaMbmEKvJzk8SVlZ0Fgz2CGzMMEtj'


# Create your views here.

def EventsListView(request):
    events = Event.objects.filter(date__year=date.today().year).order_by('date')

    for event in events:
        if event.canceled:
            event.reg_open = False
        else:
            event.reg_open = is_registration_open(event.id)
        event.save()

    year = date.today().year
    next_year = int(year) + 1
    last_year = int(year) - 1
    data = {'events': events, 'year': year, 'next_year': next_year, 'last_year': last_year}

    return render(request, 'event/events-list.html', data)


def EventsListByYearView(request, pk):
    events = Event.objects.filter(date__year=pk).order_by('date')
    for event in events:
        if event.canceled:
            event.reg_open = False
        else:
            event.reg_open = is_registration_open(event.id)
        event.save()
    year = pk
    next_year = int(year) + 1
    last_year = int(year) - 1
    data = {'events': events, 'year': year, 'next_year': next_year, 'last_year': last_year}

    return render(request, 'event/events-list.html', data)


def EventDetailViews(request, pk):
    event = get_object_or_404(Event, pk=pk)
    categories = Categories.get_categories(pk)
    print(categories)
    riders=""
    select_category=""
    alert = False
    riders_sum = 0
    reg_open = is_registration_open(pk)

    if 'categoryInput' in request.POST:
        select_category = request.POST['categoryInput']

        # check, if category is Cruiser
        if re.search("Cruiser", select_category):
            cruiser = 1
        else:
            cruiser = 0

        # get Cruiser entry riders in selected category
        if cruiser:
            entries_24 = Entry.objects.filter(event=event.id, class_24 = select_category, payment_complete=True)
            list_24=[]
            for entry_24 in entries_24:
                list_24.append(entry_24.rider)
            riders = Rider.objects.filter(uci_id__in = list_24)

         # get 20" bike entry riders in selected category
        else:
            entries_20 = Entry.objects.filter(event=event.id, class_20 = select_category, payment_complete=True)
            list_20=[]
            for entry_20 in entries_20:
                list_20.append(entry_20.rider)
            riders = Rider.objects.filter(uci_id__in = list_20)

        riders_sum = riders.count()
        if  riders_sum == 0:
            alert = True

    data = {'event': event, 'categories':categories, 'riders': riders, 'alert': alert, 'select_category': select_category, 'riders_sum': riders_sum, 'reg_open': reg_open}
    return render(request, 'event/event-detail.html', data)


def ResultsView(request, pk):
    event = get_object_or_404(Event, pk=pk)
    results = Result.objects.filter(event=pk)
    data = {'results': results, 'event': event}
    return render(request, 'event/results.html', data)


def EntryView(request, pk):
    event = get_object_or_404(Event, id=pk)
    riders = Rider.objects.filter(is_active=True, is_approwe=True)
    sum_fee = 0
    if request.POST:
        event = Event.objects.get(id=event.id)
        riders_20 = Rider.objects.filter(uci_id__in=request.POST.getlist('checkbox_20'))
        riders_24 = Rider.objects.filter(uci_id__in=request.POST.getlist('checkbox_24'))
        sum_20 = riders_20.count()
        sum_24 = riders_24.count()

        # read xlsx file due to feesgit
        wb = load_workbook('static/classes/classes.xlsx')
        sheet_range = wb[str(event.classes_code)]

        # add fees for cruiser
        for rider_20 in riders_20:
            for row in range (3, 35):
                if rider_20.class_20 == sheet_range.cell(row,1).value:
                    if rider_20.gender == "Žena" and rider_20.have_girl_bonus:
                        sum_fee+= int(sheet_range.cell(row,4).value)
                    else:
                        sum_fee+= int(sheet_range.cell(row,5).value)
        # add fees for cruiser
        for rider_24 in riders_24:
            for row in range (3, 16):
                if rider_24.class_24 == sheet_range.cell(row,6).value:
                    sum_fee+= int(sheet_range.cell(row,8).value)

        # convert to json format (need for sessions)
        sum_fee_json = json.dumps({'sum_fee': sum_fee})
        event_json = json.dumps({'event': event.id})

        # save sessions
        request.session['sum_fee'] = sum_fee_json
        request.session['event'] = event_json
        request.session['riders_20'] = serializers.serialize('json', riders_20)
        request.session['riders_24'] = serializers.serialize('json', riders_24)

        data = {'event': event, 'riders_20': riders_20, 'riders_24': riders_24, 'sum_fee': sum_fee, 'sum_20': sum_20,
                'sum_24': sum_24}
        return render(request, 'event/entry_2.html', data)

    # disable riders, who was registered in event
    for rider in riders:
        was_registered = Entry.objects.filter(event=event.id, rider=rider.uci_id, payment_complete=True)

        if was_registered.count() == 1:
            if was_registered[0].is_20:
                rider.class_20 += 'registered'
            if was_registered[0].is_24:
                rider.class_24 += "registered"
        elif was_registered.count() >= 2:
            rider.class_20 += 'registered'
            rider.class_24 += "registered"

    data = {'event': event, 'riders': riders}
    return render(request, 'event/entry.html', data)


def ConfirmView(request):

    event = json.loads(request.session['event'])
    this_event = Event.objects.get(id=event['event'])
    riders_20 = json.loads(request.session['riders_20'])
    riders_24 = json.loads(request.session['riders_24'])

    if request.method == "POST":

        # read xlsx file due to fees
        wb = load_workbook('static/classes/classes.xlsx')
        sheet_range = wb[str(this_event.classes_code)]

        fee=0

        # data for checkout session
        line_items = []
        for rider_20 in riders_20:
            for row in range (3, 35):
                if rider_20['fields']['class_20'] == sheet_range.cell(row,1).value:
                    if rider_20['fields']['gender']== "Žena" and rider_20['fields']['have_girl_bonus']:
                        fee = int(sheet_range.cell(row,4).value)
                        cat = sheet_range.cell(row,2).value
                        print(cat)
                    else:
                        fee = int(sheet_range.cell(row,5).value)
                        cat = sheet_range.cell(row,3).value
                        print(cat)
            line_items += {
                'price_data': {
                    'currency': 'czk',
                    'unit_amount': fee * 100,
                    'product_data': {
                        'name': rider_20['fields']['last_name'] + " " + rider_20['fields'][
                            'first_name'] + ", " + cat,
                        'images': [],
                        'description': "UCI ID: " + str(rider_20['fields']['uci_id']) + ", " + this_event.name
                    },
                },
                'quantity': 1,
            },

        # add fees for cruiser
        for rider_24 in riders_24:
            for row in range (3, 16):
                if rider_24['fields']['class_24'] == sheet_range.cell(row,6).value:
                    fee = int(sheet_range.cell(row,8).value)
            line_items += {
                'price_data': {
                    'currency': 'czk',
                    'unit_amount': fee * 100,
                    'product_data': {
                        'name': rider_24['fields']['last_name'] + " " + rider_24['fields'][
                            'first_name'] + ", (Cruiser) " + rider_24['fields']['class_24'],
                        'images': [],
                        'description': "UCI ID: " + str(rider_24['fields']['uci_id']) + ", " + this_event.name
                    },
                },
                'quantity': 1,
            },

        try:
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=line_items,
                mode='payment',
                success_url= settings.YOUR_DOMAIN + '/event/success',
                cancel_url=settings.YOUR_DOMAIN + '/event/cancel',
            )

            # TODO: Need last check for registration in the same time

            # save entry riders to database
            for rider_20 in riders_20:
                entry = EntryClass(transaction_id=checkout_session.id, event=this_event.id,
                                   rider=rider_20['fields']['uci_id'], is_20=True, is_24=False,
                                   class_20=rider_20['fields']['class_20'], class_24="")
                entry.save()
            for rider_24 in riders_24:
                entry = EntryClass(transaction_id=checkout_session.id, event=this_event.id,
                                   rider=rider_24['fields']['uci_id'], is_20=False, is_24=True,
                                   class_24=rider_24['fields']['class_24'], class_20="")
                entry.save()
            del entry
            return JsonResponse({'id': checkout_session.id})
        except Exception as e:
            return JsonResponse(error=str(e)), 403


def SuccessView(request):
    transactions = Entry.objects.filter(transaction_date__year=date.today().year,
                                        transaction_date__month=date.today().month,
                                        transaction_date__day=date.today().day,
                                        payment_complete=False,)
    transactions_to_email = []

    # check, if fees was paid
    for transaction in transactions:
        confirm = stripe.checkout.Session.retrieve(
            transaction.transaction_id, )
        if confirm['payment_status'] == "paid":
            transaction.payment_complete = True
            transaction.save()
            # fill list for confirm transaction via email
            if transaction.transaction_id not in transactions_to_email:
                transactions_to_email.append(transaction.transaction_id)

    # clear duplitates
    transactions_to_email = set(transactions_to_email)

    # send e-mail about confirm registrations
    for transaction_to_email in transactions_to_email:
        # threading.Thread (target = SendConfirmEmail(transaction_to_email).send_email()).start()
        pass
    return render(request, 'event/success.html')


def CancelView(request):
    return render(request, 'event/cancel.html')


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    print(payload)
    sig_header = request.META['HTTP_STRIPE_SIGNATURE']
    event = None

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        # Invalid payload
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return HttpResponse(status=400)

    # Passed signature verification
    return HttpResponse(status=200)

@staff_member_required
def EventAdminView(request, pk):
    """ Function for Event admin page view"""
    event = Event.objects.get(id=pk)

    if 'btn-upload-result' in request.POST:

        if 'result-file' not in request.FILES:
            messages.error(request, "Musíš vybrat soubor s výsledky závodu")

            return  HttpResponseRedirect(reverse('event:event-admin', kwargs={'pk': pk}))

        else:
            result_file = request.FILES.get('result-file')
            result_file_name = result_file.name
            fs = FileSystemStorage('static/results')
            filename = fs.save(result_file_name, result_file)
            uploaded_file_url = fs.url(filename)
            event = Event.objects.get(id=pk)
            ranking_code = GetResult.ranking_code_resolve(type=event.type)
            data = pd.read_excel('static/results' + uploaded_file_url, sheet_name="Results")
            for i in range(1, len(data.index)):
                uci_id = str(data.iloc[i][1])
                category = data.iloc[i][4]
                place = str(data.iloc[i][0])
                first_name = data.iloc[i][2]
                last_name = data.iloc[i][3]
                club = data.iloc[i][6]
                result = GetResult(event.date, event.id, event.name, ranking_code, uci_id, place, category, first_name,
                                last_name, club, event.organizer.team_name, event.type)
                result.write_result()
            event.results_uploaded = 1
            event.results_path_to_file = uploaded_file_url
            event.save()
            RankingCount.set_ranking_points()

            ranking = RankPositionCount()
            ranking.count_ranking_position()

            return  HttpResponseRedirect(reverse('event:event-admin', kwargs={'pk': pk}))

    if 'btn-upload-pdf' in request.POST:
        # if pdf file is not selected
        if 'result-file-pdf' not in request.FILES:
            messages.error(request, "Musíš vybrat soubor s výsledky závodu s časy")

            return  HttpResponseRedirect(reverse('event:event-admin', kwargs={'pk': pk}))
        else:
            print("Nahrávám soubor s výsledky ve formátu pdf")
            pdf_file = request.FILES.get('result-file-pdf')
            pdf_file_name = pdf_file.name
            fs = FileSystemStorage('static/full_results')
            filename = fs.save(pdf_file_name, pdf_file)
            uploaded_file_url = fs.url(filename)

            # TODO: Copy pdf file with results

        return  HttpResponseRedirect(reverse('event:event-admin', kwargs={'pk': pk}))

    if 'btn-delete-xls' in request.POST:
        print("Mažu XLS výsledky")
        try:
            os.remove(f"static/results/{event.results_path_to_file}")
        except:
            print (f"Nebyl nalezen soubor {event.results_path_to_file}")
        
        Result.objects.filter(event=pk).delete()

        RankingCount.set_ranking_points()
        RankPositionCount().count_ranking_position()

        event.results_uploaded=False
        print("Výsledky vymazány")
        event.save()

        return  HttpResponseRedirect(reverse('event:event-admin', kwargs={'pk': pk}))

    if 'btn-delete-pdf' in request.POST:
        print("Mažu PDF výsledky")
        # TODO: Delete file with PDF results
        event.results_uploaded = False
        event.full_results_path =""
        event.full_results_uploaded=None
        event.save()

        return  HttpResponseRedirect(reverse('event:event-admin', kwargs={'pk': pk}))

    if 'btn-bem-file' in request.POST:
        print("Vytvoř startovku")
        file_name = f'static/bem-files/BEM_FOR_RACE_ID-{event.id}-{event.name}.xlsx'
        wb = Workbook()
        ws = wb.active
        ws.title="BEM5_EXT"
        ws = excel_first_line(ws)

        entries_20 = Entry.objects.filter(event = event.id, is_20=True, payment_complete=1)
        x = 2
        for entry_20 in entries_20:
            rider = Rider.objects.get(uci_id=entry_20.rider)
            ws.cell(x,1,rider.uci_id)
            ws.cell(x,2,rider.uci_id)
            ws.cell(x,3,rider.uci_id)
            ws.cell(x,4,rider.uci_id)
            ws.cell(x,5,rider.uci_id)
            ws.cell(x,6,expire_licence())
            ws.cell(x,7,"BMX RACE")

            ws.cell(x,8,str(rider.date_of_birth).replace('-', '/'))
            ws.cell(x,9,rider.first_name)
            ws.cell(x,10,rider.last_name)
            ws.cell(x,11,gender_resolve(rider.gender))
            ws.cell(x,12,team_name_resolve(rider.club))
            ws.cell(x,13,"CZE")
            ws.cell(x,14,"CZE")

            ws.cell(x,15,entry_20.class_20)

            ws.cell(x,16,"")
            ws.cell(x,17,"")
            ws.cell(x,18,"")
            ws.cell(x,19,rider.plate)
            ws.cell(x,20,rider.plate)
            ws.cell(x,21,"")
            ws.cell(x,22,"")
            ws.cell(x,23,"")
            ws.cell(x,24,"")
            ws.cell(x,25,"")
            ws.cell(x,26,"")
            ws.cell(x,27,rider.transponder_20)
            ws.cell(x,28,rider.transponder_24)
            ws.cell(x,29,"")
            ws.cell(x,30,"")
            ws.cell(x,31,"T1")
            ws.cell(x,32,"")
            ws.cell(x,33,"")
            ws.cell(x,34,"")
            ws.cell(x,35,"")
            ws.cell(x,36,"")
            ws.cell(x,37,"")
            ws.cell(x,38,"")
            ws.cell(x,39,"")
            ws.cell(x,40,"")
            ws.cell(x,41,"")
            ws.cell(x,42,"")
            ws.cell(x,43,"")
            ws.cell(x,44,"")

            x += 1
        del entries_20

        entries_24 = Entry.objects.filter(event = event.id, is_24=True, payment_complete=1)
        for entry_24 in entries_24:
            rider = Rider.objects.get(uci_id=entry_24.rider)
            ws.cell(x,1,rider.uci_id)
            ws.cell(x,2,rider.uci_id)
            ws.cell(x,3,rider.uci_id)
            ws.cell(x,4,rider.uci_id)
            ws.cell(x,5,rider.uci_id)
            ws.cell(x,6,expire_licence())
            ws.cell(x,7,"BMX RACE")

            ws.cell(x,8,str(rider.date_of_birth).replace('-', '/'))
            ws.cell(x,9,rider.first_name)
            ws.cell(x,10,rider.last_name)
            ws.cell(x,11,gender_resolve(rider.gender))
            ws.cell(x,12,team_name_resolve(rider.club))
            ws.cell(x,13,"CZE")
            ws.cell(x,14,"CZE")
            ws.cell(x,15,"")
            ws.cell(x,16,"Cruiser " +rider.class_24)
            ws.cell(x,17,"")
            ws.cell(x,18,"")
            ws.cell(x,19,"")
            ws.cell(x,20,rider.plate)
            ws.cell(x,21,"")
            ws.cell(x,22,"")
            ws.cell(x,23,"")
            ws.cell(x,24,"")
            ws.cell(x,25,"")
            ws.cell(x,26,"")
            ws.cell(x,27,rider.transponder_20)
            ws.cell(x,28,rider.transponder_24)
            ws.cell(x,29,"")
            ws.cell(x,30,"")
            ws.cell(x,31,"")
            ws.cell(x,32,"T2")
            ws.cell(x,33,"")
            ws.cell(x,34,"")
            ws.cell(x,35,"")
            ws.cell(x,36,"")
            ws.cell(x,37,"")
            ws.cell(x,38,"")
            ws.cell(x,39,"")
            ws.cell(x,40,"")
            ws.cell(x,41,"")
            ws.cell(x,42,"")
            ws.cell(x,43,"")
            ws.cell(x,44,"")

            x += 1
        del entries_24

        # TODO: Add foreign riders

        wb.save(file_name)
        event.bem_entries = file_name
        event.bem_entries_created = datetime.now()
        event.save()

    if 'btn-riders-list' in request.POST:
        print("Vytvoř riders list")
        file_name = f'static/riders-list/RIDERS_LIST_FOR_RACE_ID-{event.id}.xlsx'
        wb = Workbook()
        ws = wb.active
        ws.title="BEM5_EXT"
        ws = excel_first_line(ws)

        riders = Rider.objects.filter(is_active=True, is_approwe=True, is_20=True)
        x = 2
        for rider in riders:
            ws.cell(x,1,rider.uci_id)
            ws.cell(x,2,rider.uci_id)
            ws.cell(x,3,rider.uci_id)
            ws.cell(x,4,rider.uci_id)
            ws.cell(x,5,rider.uci_id)
            ws.cell(x,6,expire_licence())
            ws.cell(x,7,"BMX RACE")

            ws.cell(x,8,str(rider.date_of_birth).replace('-', '/'))
            ws.cell(x,9,rider.first_name)
            ws.cell(x,10,rider.last_name)
            ws.cell(x,11,gender_resolve(rider.gender))
            ws.cell(x,12,team_name_resolve(rider.club))
            ws.cell(x,13,"CZE")
            ws.cell(x,14,"CZE")
            ws.cell(x,15,rider.class_20)
            ws.cell(x,16,rider.class_24)
            ws.cell(x,17,"")
            ws.cell(x,18,"")
            ws.cell(x,19,rider.plate)
            ws.cell(x,20,rider.plate)
            ws.cell(x,21,"")
            ws.cell(x,22,"")
            ws.cell(x,23,"")
            ws.cell(x,24,"")
            ws.cell(x,25,"")
            ws.cell(x,26,"")
            ws.cell(x,27,rider.transponder_20)
            ws.cell(x,28,rider.transponder_24)
            ws.cell(x,29,"")
            ws.cell(x,30,"")
            ws.cell(x,31,"T1")
            ws.cell(x,32,"T2")
            ws.cell(x,33,"")
            ws.cell(x,34,"")
            ws.cell(x,35,"")
            ws.cell(x,36,"")
            ws.cell(x,37,"")
            ws.cell(x,38,"")
            ws.cell(x,39,"")
            ws.cell(x,40,"")
            ws.cell(x,41,"")
            ws.cell(x,42,"")
            ws.cell(x,43,"")
            ws.cell(x,44,"")

            x += 1
        del riders

        wb.save(file_name)
        event.bem_riders_list = file_name
        event.bem_riders_created = datetime.now()
        event.save()

    data = {'event':event}
    return render(request, 'event/event-admin.html', data)
