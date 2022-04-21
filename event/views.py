import json
import os
from django.shortcuts import render, get_object_or_404
from .models import EntryClasses, Event, Result, Entry
from rider.models import Rider, ForeignRider
from django.shortcuts import render, reverse, HttpResponseRedirect
from django.conf import settings
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.views.decorators.csrf import csrf_exempt
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import cache_control
import pandas as pd
from .result import GetResult
from .func import *
from bmx.sec import * 
from .entry import EntryClass, SendConfirmEmail
from datetime import date, datetime
from ranking.ranking import RankingCount, RankPositionCount, Categories
import re
from django.core import serializers
from django.http import JsonResponse, HttpResponse
from openpyxl import Workbook
import stripe


# Create your views here.

def EventsListView(request):
    events = Event.objects.filter(date__year=date.today().year).order_by('date')

    for event in events:
        if event.canceled:
            event.reg_open = False
        else:
            event.reg_open = is_registration_open(event.id)

        if event.classes_and_fees_like.event_name == "Dosud nenastaveno":
            event.reg_open = False
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
        
        print(event.classes_and_fees_like.event_name)
        if event.classes_and_fees_like.event_name == "Dosud nenastaveno":
            print("Kategorie závodů nebyla stanovena")
            event.reg_open = False
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

        fee = EntryClasses.objects.get(id=event.classes_and_fees_like.id)

        for rider_20 in riders_20:
            if rider_20.class_20 == "Boys 6":
                sum_fee+=fee.boys_6_fee 
            elif rider_20.class_20 == "Boys 7":
                sum_fee+=fee.boys_7_fee       
            elif rider_20.class_20 == "Boys 8":
                sum_fee+=fee.boys_8_fee
            elif rider_20.class_20 == "Boys 9":
                sum_fee+=fee.boys_9_fee
            elif rider_20.class_20 == "Boys 10":
                sum_fee+=fee.boys_10_fee
            elif rider_20.class_20 == "Boys 11":
                sum_fee+=fee.boys_11_fee
            elif rider_20.class_20 == "Boys 12":
                sum_fee+=fee.boys_12_fee
            elif rider_20.class_20 == "Boys 13":
                sum_fee+=fee.boys_13_fee
            elif rider_20.class_20 == "Boys 14":
                sum_fee+=fee.boys_14_fee
            elif rider_20.class_20 == "Boys 15":
                sum_fee+=fee.boys_15_fee
            elif rider_20.class_20 == "Boys 16":
                sum_fee+=fee.boys_16_fee
            elif rider_20.class_20 == "Men 17-24":
                sum_fee+=fee.men_17_24_fee
            elif rider_20.class_20 == "Men 25-29":
                sum_fee+=fee.men_25_29_fee
            elif rider_20.class_20 == "Men 30-34":
                sum_fee+=fee.men_30_34_fee
            elif rider_20.class_20 == "Men 35 and over":
                sum_fee+=fee.men_35_over_fee
            elif rider_20.class_20 == "Men Junior":
                sum_fee+=fee.men_junior_fee
            elif rider_20.class_20 == "Men Under 23":
                sum_fee+=fee. men_u23_fee
            elif rider_20.class_20 == "Men Elite":
                sum_fee+=fee.men_elite_fee
            elif rider_20.class_20 == "Girls 7":
                sum_fee+=fee.girls_7_fee
            elif rider_20.class_20 == "Girls 8":
                sum_fee+=fee.girls_8_fee
            elif rider_20.class_20 == "Girls 9":
                sum_fee+=fee.girls_9_fee
            elif rider_20.class_20 == "Girls 10":
                sum_fee+=fee.girls_10_fee 
            elif rider_20.class_20 == "Girls 11":
                sum_fee+=fee.girls_11_fee
            elif rider_20.class_20 == "Girls 12":
                sum_fee+=fee.girls_12_fee
            elif rider_20.class_20 == "Girls 13":
                sum_fee+=fee.girls_13_fee
            elif rider_20.class_20 == "Girls 14":
                sum_fee+=fee.girls_14_fee
            elif rider_20.class_20 == "Girls 15":
                sum_fee+=fee.girls_15_fee
            elif rider_20.class_20 == "Girls 16":
                sum_fee+=fee.girls_16_fee
            elif rider_20.class_20 == "Women 17-24":
                sum_fee+=fee. women_17_24_fee
            elif rider_20.class_20 == "Women 25 and over":
                sum_fee+=fee. women_25_over_fee  

        for rider_24 in riders_24:
            if rider_24.class_24 == "Boys 12 and under":
                sum_fee+=fee.cr_boys_12_and_under_fee  
            elif rider_24.class_24 == "Boys 13 and 14":
                sum_fee+=fee.cr_boys_13_14_fee
            elif rider_24.class_24 == "Boys 15 and 16":
                sum_fee+=fee.cr_boys_15_16_fee
            elif rider_24.class_24 == "Men 17-24":
                sum_fee+=fee.cr_men_17_24_fee
            elif rider_24.class_24 == "Men 25-29":
                sum_fee+=fee.cr_men_25_29_fee
            elif rider_24.class_24 == "Men 30-34":
                sum_fee+=fee.cr_men_30_34_fee
            elif rider_24.class_24 == "Men 35-39":
                sum_fee+=fee.cr_men_35_39_fee
            elif rider_24.class_24 == "Men 40-49":
                sum_fee+=fee.cr_men_40_49_fee
            elif rider_24.class_24 == "Men 50 and over":
                sum_fee+=fee.cr_men_50_and_over_fee
            elif rider_24.class_24 == "Girls 12 and under":
                sum_fee+=fee. cr_girls_12_and_under_fee
            elif rider_24.class_24 == "Girls 13-16":
                sum_fee+=fee.cr_girls_13_16_fee
            elif rider_24.class_24 == "Women 17-29":
                sum_fee+=fee.cr_women_17_29_fee
            elif rider_24.class_24 == "Women 30-39":
                sum_fee+=fee.cr_women_30_39_fee
            elif rider_24.class_24 == "Women 40 and over":
                sum_fee+=fee.cr_women_40_and_over_fee

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
        return render(request, 'event/checkout.html', data)

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


def EntryRidersView(request,pk):
    """ View for registrated riders in event"""
    event = Event.objects.get(id=pk)
    entries_20 = Entry.objects.filter(event=pk, is_20=1, payment_complete=1)
    entries_24 = Entry.objects.filter(event=pk, is_24=1, payment_complete=1)
    riders_20=[]
    riders_24=[]

    for entry_20 in entries_20:
        rider_20 = Rider.objects.get(uci_id = entry_20.rider)
        rider_20.class_20 = entry_20.class_20

        riders_20.append(rider_20)
    
    for entry_24 in entries_24:
        rider_24 = Rider.objects.get(uci_id = entry_24.rider)
        rider_24.class_24 = entry_24.class_24
        print(rider_24.class_24)
        riders_24.append(rider_24)

    data={'event':event, 'riders_20':riders_20, 'riders_24':riders_24}
    return render(request, 'event/entry-riders.html', data)


def ConfirmView(request):

    event = json.loads(request.session['event'])
    this_event = Event.objects.get(id=event['event'])
    riders_20 = json.loads(request.session['riders_20'])
    riders_24 = json.loads(request.session['riders_24'])

    current_event = Event.objects.get(id=event['event'])

    entry_fee = EntryClasses.objects.get(id=current_event.classes_and_fees_like.id)

    if request.method == "POST":
        fee=0
  
        # data for checkout session
        line_items = []
        for rider_20 in riders_20:
            if rider_20['fields']['class_20'] == "Boys 6":
               fee = entry_fee.boys_6_fee
            elif rider_20['fields']['class_20'] == "Boys 7":
               fee = entry_fee.boys_7_fee
            elif rider_20['fields']['class_20'] == "Boys 8":
               fee = entry_fee.boys_8_fee
            elif rider_20['fields']['class_20'] == "Boys 9":
               fee = entry_fee.boys_9_fee
            elif rider_20['fields']['class_20'] == "Boys 10":
               fee = entry_fee.boys_10_fee
            elif rider_20['fields']['class_20'] == "Boys 11":
               fee = entry_fee.boys_11_fee
            elif rider_20['fields']['class_20'] == "Boys 12":
               fee = entry_fee.boys_12_fee
            elif rider_20['fields']['class_20'] == "Boys 13":
               fee = entry_fee.boys_13_fee
            elif rider_20['fields']['class_20'] == "Boys 14":
               fee = entry_fee.boys_14_fee
            elif rider_20['fields']['class_20'] == "Boys 15":
               fee = entry_fee.boys_15_fee
            elif rider_20['fields']['class_20'] == "Boys 16":
               fee = entry_fee.boys_16_fee
            elif rider_20['fields']['class_20'] == "Men 17-24":
               fee = entry_fee.men_17_24_fee
            elif rider_20['fields']['class_20'] == "Men 25-29":
               fee = entry_fee.men_25_29_fee
            elif rider_20['fields']['class_20'] == "Men 30-34":
               fee = entry_fee.men_30_34_fee
            elif rider_20['fields']['class_20'] == "Men 35 and over":
               fee = entry_fee.men_35_over_fee
            elif rider_20['fields']['class_20'] == "Men Junior":
               fee = entry_fee.men_junior_fee
            elif rider_20['fields']['class_20'] == "Men Under 23":
               fee = entry_fee.men_u23_fee
            elif rider_20['fields']['class_20'] == "Men Elite":
               fee = entry_fee.men_elite_fee
            elif rider_20['fields']['class_20'] == "Girls 7":
               fee = entry_fee.girls_7_fee
            elif rider_20['fields']['class_20'] == "Girls 8":
               fee = entry_fee.girls_8_fee
            elif rider_20['fields']['class_20'] == "Girls 9":
               fee = entry_fee.girls_9_fee
            elif rider_20['fields']['class_20'] == "Girls 10":
               fee = entry_fee.girls_10_fee
            elif rider_20['fields']['class_20'] == "Girls 11":
               fee = entry_fee.girls_11_fee
            elif rider_20['fields']['class_20'] == "Girls 12":
               fee = entry_fee.girls_12_fee
            elif rider_20['fields']['class_20'] == "Girls 13":
               fee = entry_fee.girls_13_fee
            elif rider_20['fields']['class_20'] == "Girls 14":
               fee = entry_fee.girls_14_fee
            elif rider_20['fields']['class_20'] == "Girls 15":
               fee = entry_fee.girls_15_fee
            elif rider_20['fields']['class_20'] == "Girls 16":
               fee = entry_fee.girls_16_fee
            elif rider_20['fields']['class_20'] == "Women 17-24":
               fee = entry_fee.women_17_24_fee
            elif rider_20['fields']['class_20'] == "Women 25 and over":
               fee = entry_fee. women_25_over_fee
            elif rider_20['fields']['class_20'] == "Women Junior":
               fee = entry_fee.women_junior_fee
            elif rider_20['fields']['class_20'] == "Women Under 23":
               fee = entry_fee.women_u23_fee
            elif rider_20['fields']['class_20'] == "Women Elite":
               fee = entry_fee.women_elite_fee
            
    
            line_items += {
                'price_data': {
                        'currency': 'czk',
                        'unit_amount': fee * 100,
                        'product_data': {
                            'name': rider_20['fields']['last_name'] + " " + rider_20['fields'][
                                'first_name'] + ", " +rider_20['fields']['class_20'],
                            'images': [],
                            'description': "UCI ID: " + str(rider_20['fields']['uci_id']) + ", " + this_event.name
                        },
                    },
                    'quantity': 1,
                },

        # add fees for cruiser
        for rider_24 in riders_24:
            if rider_24['fields']['class_24'] == "Boys 12 and under":
                fee=entry_fee.cr_boys_12_and_under_fee
            elif rider_24['fields']['class_24'] == "Boys 13 and 14":
                fee=entry_fee.cr_boys_13_14_fee
            elif rider_24['fields']['class_24'] == "Boys 15 and 16":
                fee=entry_fee.cr_boys_15_16_fee
            elif rider_24['fields']['class_24'] == "Men 17-24":
                fee=entry_fee.cr_men_17_24_fee
            elif rider_24['fields']['class_24'] == "Men 25-29":
                fee=entry_fee.cr_men_25_29_fee
            elif rider_24['fields']['class_24'] == "Men 30-34":
                fee=entry_fee.cr_men_30_34_fee
            elif rider_24['fields']['class_24'] == "Men 35-39":
                fee=entry_fee.cr_men_35_39_fee
            elif rider_24['fields']['class_24'] == "Men 40-49":
                fee=entry_fee.cr_men_40_49_fee
            elif rider_24['fields']['class_24'] == "Men 50 and over":
                fee=entry_fee.cr_men_50_and_over_fee
            elif rider_24['fields']['class_24'] == "Girls 12 and under":
                fee=entry_fee.cr_girls_12_and_under_fee
            elif rider_24['fields']['class_24'] == "Girls 13-16":
                fee=entry_fee.cr_girls_13_16_fee
            elif rider_24['fields']['class_24'] == "Women 17-29":
                fee=entry_fee.cr_women_17_29_fee
            elif rider_24['fields']['class_24'] == "Women 30-39":
                fee=entry_fee.cr_women_30_39_fee
            elif rider_24['fields']['class_24'] == "Women 40 and over":
                fee=entry_fee.cr_women_40_and_over_fee

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
            print("Zkouším checkout")
            
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=line_items,
                mode='payment',
                success_url= settings.YOUR_DOMAIN + '/event/success/'+str(this_event.id),
                cancel_url=settings.YOUR_DOMAIN + '/event/cancel',
            )
            # TODO: Need last check for registration in the same time

            # save entry riders to database
            for rider_20 in riders_20:
                current_rider = Rider.objects.get(uci_id=rider_20['fields']['uci_id'])
                current_fee = resolve_event_fee(this_event.id, current_rider.gender, current_rider.have_girl_bonus, current_rider.class_20, 1)
                entry = EntryClass(transaction_id=checkout_session.id, event=this_event.id,
                                    rider=rider_20['fields']['uci_id'], is_20=True, is_24=False,
                                    class_20=rider_20['fields']['class_20'], class_24="", fee_20 = current_fee)
                entry.save()
    
            for rider_24 in riders_24:
                current_rider = Rider.objects.get(uci_id=rider_24['fields']['uci_id'])
                current_fee = resolve_event_fee(this_event.id, current_rider.gender, current_rider.have_girl_bonus, current_rider.class_24, 0)
                entry = EntryClass(transaction_id=checkout_session.id, event=this_event.id,
                                    rider=rider_24['fields']['uci_id'], is_20=False, is_24=True,
                                    class_24=rider_24['fields']['class_24'], class_20="", fee_24 = current_fee)
                entry.save()
                
            del entry
            return JsonResponse({'id': checkout_session.id})
        except Exception as e:
            return JsonResponse(error=str(e)), 403


def SuccessView(request, pk):
    transactions = Entry.objects.filter(transaction_date__year=date.today().year,
                                        transaction_date__month=date.today().month,
                                        transaction_date__day__lte=date.today().day,
                                        payment_complete=False,).filter(transaction_date__day__gte=date.today().day-2,)
    transactions_to_email = []

    # check, if fees was paid
    for transaction in transactions:
        try:
            confirm = stripe.checkout.Session.retrieve(
                transaction.transaction_id, )
            if confirm['payment_status'] == "paid":
                transaction.payment_complete = True
                transaction.save()
                # fill list for confirm transaction via email
                if transaction.transaction_id not in transactions_to_email:
                    transactions_to_email.append(transaction.transaction_id)
        except Exception as e:
            pass
    # clear duplitates
            
    transactions_to_email = set(transactions_to_email)

    # send e-mail about confirm registrations
    for transaction_to_email in transactions_to_email:
        # threading.Thread (target = SendConfirmEmail(transaction_to_email).send_email()).start()
        pass
 
    data = {'event_id':pk}
    return render(request, 'event/success.html', data)


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
            payload, sig_header, STRIPE_ENDPOINT_SECRET
        )
    except ValueError as e:
        # Invalid payload
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return HttpResponse(status=400)

    # Passed signature verification
    return HttpResponse(status=200)


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@staff_member_required
def EventAdminView(request, pk):
    """ Function for Event admin page view"""
    event = Event.objects.get(id=pk)

    if 'btn-upload-result' in request.POST:

        if 'result-file' not in request.FILES: # if xls file is not selected
            messages.error(request, "Musíš vybrat soubor s výsledky závodu")
            return  HttpResponseRedirect(reverse('event:event-admin', kwargs={'pk': pk}))

        else:
            result_file = request.FILES.get('result-file')
            result_file_name = result_file.name
            fs = FileSystemStorage('static/results')
            filename = fs.save(result_file_name, result_file)
            uploaded_file_url = fs.url(filename)
            event = Event.objects.get(id=pk)
            ranking_code = GetResult.ranking_code_resolve(type=event.type_for_ranking)
            data = pd.read_excel('static/results' + uploaded_file_url, sheet_name="Results")
            for i in range(1, len(data.index)):
                uci_id = str(data.iloc[i][1])
                category = data.iloc[i][5]
                place = str(data.iloc[i][0])
                first_name = data.iloc[i][2]
                last_name = data.iloc[i][3]
                club = data.iloc[i][6]

                # Kategorie Příchozích neboduje do rankingu
                if category.find("Příchozí") == -1 and category.find("Prichozi") == -1:
                    result = GetResult(event.date, event.id, event.name, ranking_code, uci_id, place, category, first_name,
                                last_name, club, event.organizer.team_name, event.type_for_ranking)
                    result.write_result()
                      
            event.xml_results = uploaded_file_url
            event.save()
            RankingCount.set_ranking_points()
            ranking = RankPositionCount()
            ranking.count_ranking_position()

            return  HttpResponseRedirect(reverse('event:event-admin', kwargs={'pk': pk}))

    if 'btn-upload-pdf' in request.POST:
        
        if 'result-file-pdf' not in request.FILES: # if pdf file is not selected
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
            os.remove(f"static/results/{event.xml_results}")
        except Exception as e:
            print (f"Nebyl nalezen soubor {event.xml_results}")
        
        Result.objects.filter(event=pk).delete()

        RankingCount.set_ranking_points()
        RankPositionCount().count_ranking_position()

        event.xml_results=""
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
            ws.cell(x,7,"BMX-RACE")
            ws.cell(x,9,str(rider.date_of_birth).replace('-', '/'))
            ws.cell(x,10,rider.first_name)
            ws.cell(x,11,rider.last_name.upper())
            ws.cell(x,12,rider.email)
            ws.cell(x,13,rider.phone)
            ws.cell(x,14,rider.emergency_contact)
            ws.cell(x,15,rider.emergency_phone)
            ws.cell(x,16,gender_resolve(rider.gender))
            ws.cell(x,17,team_name_resolve(rider.club))
            ws.cell(x,18,"CZE")
            ws.cell(x,19,"CZE")
            ws.cell(x,20,entry_20.class_20)
            ws.cell(x,24,rider.plate)
            ws.cell(x,25,rider.plate)
            ws.cell(x,32,rider.transponder_20)
            # ws.cell(x,33,rider.transponder_24)
            ws.cell(x,36,"T1")
            ws.cell(x,37,"T1")
            ws.cell(x,45,team_name_resolve(rider.club).upper())
            if rider.have_valid_licence:
                ws.cell(x,46,"")
            else:
                ws.cell(x,46,"NEPLATNÁ LICENCE")

            x += 1

            #TODO: Dodělat zobrazení přihlášených jezdců s neplatnou licencí

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
            ws.cell(x,9,str(rider.date_of_birth).replace('-', '/'))
            ws.cell(x,10,rider.first_name)
            ws.cell(x,11,rider.last_name.upper())
            ws.cell(x,12,rider.email)
            ws.cell(x,13,rider.phone)
            ws.cell(x,14,rider.emergency_contact)
            ws.cell(x,15,rider.emergency_phone)
            ws.cell(x,16,gender_resolve(rider.gender))
            ws.cell(x,17,team_name_resolve(rider.club))
            ws.cell(x,18,"CZE")
            ws.cell(x,19,"CZE")
            ws.cell(x,21,"Cruiser " +rider.class_24)
            ws.cell(x,25,rider.plate)
            # ws.cell(x,32,rider.transponder_20)
            ws.cell(x,33,rider.transponder_24)
            ws.cell(x,36,"T1")
            ws.cell(x,37,"T2")
            ws.cell(x,45,team_name_resolve(rider.club))
            if rider.have_valid_licence:
                ws.cell(x,46,"")
            else:
                ws.cell(x,46,"NEPLATNÁ LICENCE")
   
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

        riders = Rider.objects.filter(is_active=True, is_approwe=True)
        x = 2
        for rider in riders:
            ws.cell(x,1,rider.uci_id)
            ws.cell(x,2,rider.uci_id)
            ws.cell(x,3,rider.uci_id)
            ws.cell(x,4,rider.uci_id)
            ws.cell(x,5,rider.uci_id)
            ws.cell(x,6,expire_licence())
            ws.cell(x,7,"BMX-RACE")
            ws.cell(x,9,str(rider.date_of_birth).replace('-', '/'))
            ws.cell(x,10,rider.first_name)
            ws.cell(x,11,rider.last_name.upper())
            ws.cell(x,12,rider.email)
            ws.cell(x,13,rider.phone)
            ws.cell(x,14,rider.emergency_contact)
            ws.cell(x,15,rider.emergency_phone)
            ws.cell(x,16,gender_resolve(rider.gender))
            ws.cell(x,17,team_name_resolve(rider.club))
            ws.cell(x,18,"CZE")
            ws.cell(x,19,"CZE")
            if rider.is_20:
                ws.cell(x,20,resolve_event_classes(event.id,rider.gender,rider.have_girl_bonus,rider.class_20,1))
            if rider.is_24:
                ws.cell(x,21,resolve_event_classes(event.id,rider.gender,rider.have_girl_bonus,rider.class_24,0))
            ws.cell(x,28,"")
            ws.cell(x,29,"")
            ws.cell(x,24,rider.plate)
            ws.cell(x,25,rider.plate)
            ws.cell(x,32,rider.transponder_20)
            ws.cell(x,33,rider.transponder_24)
            ws.cell(x,36,"T1")
            ws.cell(x,37,"T2")
            ws.cell(x,45,team_name_resolve(rider.club).upper())
            if rider.have_valid_licence:
                ws.cell(x,46,"")
            else:
                ws.cell(x,46,"NEPLATNÁ LICENCE")

            x += 1
        del riders

        foreign_riders = ForeignRider.objects.all()
        for foreign_rider in foreign_riders:
            ws.cell(x,1,foreign_rider.uci_id)
            ws.cell(x,2,foreign_rider.uci_id)
            ws.cell(x,3,foreign_rider.uci_id)
            ws.cell(x,4,foreign_rider.uci_id)
            ws.cell(x,5,foreign_rider.uci_id)
            ws.cell(x,6,expire_licence())
            ws.cell(x,7,"BMX-RACE")
            ws.cell(x,9,str(foreign_rider.date_of_birth).replace('-', '/'))
            ws.cell(x,10,foreign_rider.first_name)
            ws.cell(x,11,foreign_rider.last_name.upper())
            ws.cell(x,16,gender_resolve(foreign_rider.gender))
            ws.cell(x,17,foreign_club_resolve(foreign_rider.state))
            ws.cell(x,18,foreign_rider.state)
            ws.cell(x,19,foreign_rider.state)
            if foreign_rider.is_20:
                ws.cell(x,20,resolve_event_classes(event.id,foreign_rider.gender,True,foreign_rider.class_20,1))
            if foreign_rider.is_24:
                ws.cell(x,21,resolve_event_classes(event.id,foreign_rider.gender,False,foreign_rider.class_24,0))
            ws.cell(x,28,"")
            ws.cell(x,29,"")
            ws.cell(x,24,foreign_rider.plate)
            ws.cell(x,25,foreign_rider.plate)
            ws.cell(x,32,foreign_rider.transponder_20)
            ws.cell(x,33,foreign_rider.transponder_24)
            ws.cell(x,36,"T1")
            ws.cell(x,37,"T2")
            ws.cell(x,45,foreign_rider.club.upper())
            x+=1
        del foreign_riders

        wb.save(file_name)
        event.bem_riders_list = file_name
        event.bem_riders_created = datetime.now()
        event.save()

    # zjištění jezdců přihlášených na závod s neplatnou licencí

    check_20_entries = Entry.objects.filter(event = event.id, is_20=True, payment_complete=1)
    check_24_entries = Entry.objects.filter(event = event.id, is_24=True, payment_complete=1)

    invalid_licences = []
    sum_of_fees = 0
    sum_of_riders = 0
    organizer_fee = 0

    for check20 in check_20_entries:
        try:
            rider = Rider.objects.get(uci_id=check20.rider)
            if not rider.have_valid_licence:
                invalid_licences.append(rider)
        except Exception as e:
            pass    #TODO: Dodělat zprávu o chybě

    for check24 in check_24_entries:
        try:
            rider = Rider.objects.get(uci_id=check24.rider)
            if not rider.have_valid_licence:
                invalid_licences.append(rider)
        except Exception as e:
            pass    #TODO: Dodělat zprávu o chybě
        
    invalid_licences =  set(invalid_licences) #odstranění duplicit, pokud jezdec jede 20" i 24" 

    # summary fees on event
    entries = Entry.objects.filter(event = event.id, payment_complete=1)

    for entry in entries:
        sum_of_fees += entry.fee_20
        sum_of_fees += entry.fee_24
        sum_of_riders+=1

    organizer_fee = int(sum_of_fees - ( sum_of_fees * event.commission_fee /100))

    print(f"Vybrané startovné činní částku {sum_of_fees} Kč.")

    data = {'event':event, "invalid_licences": invalid_licences, "sum_of_fees": sum_of_fees, "sum_of_riders":sum_of_riders, 'organizer_fee':organizer_fee}
    return render(request, 'event/event-admin.html', data)
