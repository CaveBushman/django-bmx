import json
import os
from django.shortcuts import render, get_object_or_404, redirect
from .models import EntryClasses, Event, Result, Entry
from rider.models import Rider, ForeignRider
from club.models import Club
from django.shortcuts import render, reverse, HttpResponseRedirect
from django.conf import settings
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.views.decorators.csrf import csrf_exempt
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import cache_control
from django.db.models import Q
import pandas as pd
from .func import *
from .entry import EntryClass, SendConfirmEmail, NumberInEvent, REMRiders
from datetime import date, datetime
from ranking.ranking import RankingCount, RankPositionCount, Categories, SetRanking
from django.core import serializers
from django.http import FileResponse, JsonResponse, HttpResponse
from openpyxl import Workbook
from openpyxl import load_workbook
import stripe
from decouple import config
from django.utils import timezone
from event.func import update_cart


# Create your views here.

def events_list_view(request):
    events = Event.objects.filter(date__year=date.today().year).order_by('date')

    for event in events:
        if event.canceled:
            event.reg_open = False
        else:
            event.reg_open = is_registration_open(event)

        if event.classes_and_fees_like.event_name == "Dosud nenastaveno":
            event.reg_open = False
        event.save()
    year = date.today().year
    next_year = int(year) + 1
    last_year = int(year) - 1
    data = {'events': events, 'year': year, 'next_year': next_year, 'last_year': last_year}

    return render(request, 'event/events-list_new.html', data)


def events_list_by_year_view(request, pk):
    events = Event.objects.filter(date__year=pk).order_by('date')
    for event in events:
        if event.canceled or event.classes_and_fees_like.event_name == "Dosud nenastaveno":
            event.reg_open = False
        else:
            event.reg_open = is_registration_open(event)
        event.save()
    year = pk
    next_year = int(year) + 1
    last_year = int(year) - 1
    data = {'events': events, 'year': year, 'next_year': next_year, 'last_year': last_year}

    return render(request, 'event/events-list_new.html', data)


def event_detail_views(request, pk):
    event = get_object_or_404(Event, pk=pk)
    select_category = ""
    alert = False
    riders_sum = 0
    reg_open = is_registration_open(event)

    data = {'event': event, 'alert': alert, 'select_category': select_category,
            'riders_sum': riders_sum, 'reg_open': reg_open}
    return render(request, 'event/event-detail.html', data)


def results_view(request, pk):
    event = get_object_or_404(Event, pk=pk)
    results = Result.objects.filter(event=pk).order_by('category', 'place')
    data = {'results': results, 'event': event}
    return render(request, 'event/results.html', data)


def add_entries_view(request, pk):
    event = get_object_or_404(Event, id=pk)
    riders = Rider.objects.filter(is_active=True, is_approwe=True, valid_licence=True)
    sum_fee = 0

    # Přesměrování po datu registrace - CHYBOVÁ HLÁŠKA
    if event.canceled or not event.reg_open or (event.reg_open_to < timezone.now()):
        return render(request, 'event/reg-close.html')

    if request.POST:
        riders_beginner = Rider.objects.filter(uci_id__in=request.POST.getlist('checkbox_beginner'))
        riders_20 = Rider.objects.filter(uci_id__in=request.POST.getlist('checkbox_20'))
        riders_24 = Rider.objects.filter(uci_id__in=request.POST.getlist('checkbox_24'))
        sum_beginners = riders_beginner.count()
        sum_20 = riders_20.count()
        sum_24 = riders_24.count()

        for rider in riders_beginner:
            sum_fee += resolve_event_fee(event, rider, is_20=True, is_beginner=True)

            # TODO: Dodělat uložení do košíku
            if "btn_add" in request.POST:
                cart = Cart()
                cart.user = Account.objects.get(id=request.user.id)
                cart.event = event
                cart.rider = rider
                cart.is_beginner = True
                cart.fee_beginner = resolve_event_fee(event, rider, is_20=True, is_beginner=True)
                cart.class_beginner = resolve_event_classes(event, rider, is_20=True, is_beginner=True)
                if not Entry.objects.filter(rider=rider, event=event, is_beginner=True, payment_complete=True):
                    cart.save()

        for rider_20 in riders_20:
            sum_fee += resolve_event_fee(event, rider_20, is_20=True)
            # TODO: Dodělat uložení do košíku
            if "btn_add" in request.POST:
                cart = Cart()
                cart.user = Account.objects.get(id=request.user.id)
                cart.event = event
                cart.rider = rider_20
                cart.is_20 = True
                cart.fee_20 = resolve_event_fee(event, rider_20, is_20=True)
                cart.class_20 = resolve_event_classes(event, rider_20, is_20=True)
                if not Entry.objects.filter(rider=rider_20, event=event, is_20=True, payment_complete=True):
                    cart.save()

        for rider_24 in riders_24:
            sum_fee += resolve_event_fee(event, rider_24, is_20=False)
            # TODO: Dodělat uložení do košíku
            if "btn_add" in request.POST:
                cart = Cart()
                cart.user = Account.objects.get(id=request.user.id)
                cart.event = event
                cart.rider = rider_24
                cart.is_24 = True
                cart.fee_24 = resolve_event_fee(event, rider_24, is_20=False)
                cart.class_24 = resolve_event_classes(event, rider_24, is_20=False)
                if not Entry.objects.filter(rider=rider_24, event=event, is_24=True, payment_complete=True):
                    cart.save()

        if "btn_add" in request.POST:
            update_cart(request)
            return redirect('event:events')

        # convert to json format (need for sessions)
        sum_fee_json = json.dumps({'sum_fee': sum_fee})
        event_json = json.dumps({'event': event.id})

        # save sessions
        request.session.set_expiry(300)

        request.session['sum_fee'] = sum_fee_json
        request.session['event'] = event_json
        request.session['riders_beginner'] = serializers.serialize('json', riders_beginner)
        request.session['riders_20'] = serializers.serialize('json', riders_20)
        request.session['riders_24'] = serializers.serialize('json', riders_24)

        for rider_beginner in riders_beginner:
            rider_beginner.class_beginner = resolve_event_classes(event, rider_beginner, is_20=True, is_beginner=True)

        for rider_20 in riders_20:
            rider_20.class_20 = resolve_event_classes(event, rider_20, is_20=True)

        for rider_24 in riders_24:
            rider_24.class_24 = resolve_event_classes(event, rider_24, is_20=False)

        data = {'event': event, 'riders_20': riders_20, 'riders_24': riders_24, 'riders_beginner': riders_beginner,
                'sum_fee': sum_fee, 'sum_beginners': sum_beginners, 'sum_20': sum_20,
                'sum_24': sum_24}

        response = render(request, 'event/checkout.html', data)
        # response.set_cookie()
        return response

    # disable riders, who was registered in event

    if event.is_beginners_event():
        event.is_beginners_race = True
    else:
        event.is_beginners_race = False

    for rider in riders:
        was_registered = Entry.objects.filter(event=event, rider=rider, payment_complete=True)

        # classes for Beginners
        if event.is_beginners_race and is_beginner(rider):
            rider.is_beginner = True
            rider.class_beginner = resolve_event_classes(event, rider, is_20=True, is_beginner=True)

        rider.class_20 = resolve_event_classes(event, rider, is_20=True)
        rider.class_24 = resolve_event_classes(event, rider, is_20=False)
        if rider.is_elite:
            rider.class_24 = "NELZE PŘIHLÁSIT"

        if was_registered.count() > 0:
            if was_registered[0].is_beginner:
                rider.class_beginner += 'registered'
            if was_registered[0].is_20:
                rider.class_20 += 'registered'
            if was_registered[0].is_24:
                rider.class_24 += "registered"

    data = {'event': event, 'riders': riders}
    return render(request, 'event/entry.html', data)


def entry_riders_view(request, pk):
    """ View for registered riders in event"""
    event = Event.objects.get(id=pk)
    entries = Entry.objects.filter(event=pk, payment_complete=1, checkout=0)
    checkout = Entry.objects.filter(event=pk, payment_complete=1, checkout=1)

    categories = []

    for entry in entries:
        if entry.class_20 not in categories:
            categories.append(entry.class_20)
        elif entry.class_24 not in categories:
            categories.append(entry.class_24)

    try:
        categories.sort()
        categories.remove('')
    except Exception as e:
        pass

    data = {'event': event, 'entries': entries, 'checkout': checkout, 'categories': categories}
    return render(request, 'event/entry-list.html', data)


def confirm_view(request):
    this_event = json.loads(request.session['event'])
    event = Event.objects.get(id=this_event['event'])
    riders_beginner_list = json.loads(request.session['riders_beginner'])
    riders_20_list = json.loads(request.session['riders_20'])
    riders_24_list = json.loads(request.session['riders_24'])

    if 'btn-add-event' in request.POST:
        pass

    if request.method == "POST":

        # add entries for 20" bikes
        line_items = []

        for rider_beginner in riders_beginner_list:
            rider = Rider.objects.get(uci_id=rider_beginner['fields']['uci_id'])
            line_items += generate_stripe_line(event, rider, is_20=True, is_beginner=True)

        for rider_20_list in riders_20_list:
            rider = Rider.objects.get(uci_id=rider_20_list['fields']['uci_id'])
            line_items += generate_stripe_line(event, rider, is_20=True)

        # add entries for cruiser
        for rider_24_list in riders_24_list:
            rider = Rider.objects.get(uci_id=rider_24_list['fields']['uci_id'])
            line_items += generate_stripe_line(event, rider, is_20=False)

        print(line_items)
        try:
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=line_items,
                mode='payment',
                success_url=settings.YOUR_DOMAIN + '/event/success/' + str(event.id),
                cancel_url=settings.YOUR_DOMAIN + '/event/cancel',
            )
            # TODO: Need last check for registration in the same time
            # save entries riders to database
            for rider in riders_beginner_list:
                current_rider = Rider.objects.get(uci_id=rider['fields']['uci_id'])
                current_fee = resolve_event_fee(event, current_rider, 1)
                current_class = resolve_event_classes(event, current_rider, is_20=True, is_beginner=True)
                entry = Entry(transaction_id=checkout_session.id, event=event,
                              rider=current_rider, is_beginner=True, is_20=False, is_24=False,
                              class_beginner=current_class, class_20="", class_24="", fee_beginner=current_fee)
                entry.save()

            for rider in riders_20_list:
                current_rider = Rider.objects.get(uci_id=rider['fields']['uci_id'])
                current_fee = resolve_event_fee(event, current_rider, 1)
                current_class = resolve_event_classes(event, current_rider, is_20=True)
                print(checkout_session.id)
                entry = Entry(transaction_id=checkout_session.id, event=event,
                              rider=current_rider, is_20=True, is_24=False, is_beginner=False,
                              class_beginner="", class_20=current_class, class_24="", fee_20=current_fee)
                entry.save()

            for rider in riders_24_list:
                current_rider = Rider.objects.get(uci_id=rider['fields']['uci_id'])
                current_fee = resolve_event_fee(event, current_rider, 0)
                current_class = resolve_event_classes(event, current_rider, is_20=False)
                entry = Entry(transaction_id=checkout_session.id, event=event,
                              rider=current_rider, is_20=False, is_24=True, is_beginner=False,
                              class_beginner="", class_24=current_class, class_20="", fee_24=current_fee)
                entry.save()
            del entry

            return JsonResponse({'id': checkout_session.id})
        except Exception as e:
            print(e)
            return JsonResponse(error=str(e)), 403


def success_view(request, pk):
    transactions = Entry.objects.filter(Q(transaction_date__year=date.today().year,
                                          transaction_date__month=date.today().month,
                                          transaction_date__day=date.today().day,
                                          event=pk,
                                          payment_complete=False, ) |
                                        (Q(transaction_date__year=date.today().year,
                                           transaction_date__month=date.today().month,
                                           transaction_date__day=date.today().day - 1,
                                           event=pk,
                                           payment_complete=False, )))

    transactions_to_email = []
    # check, if fees was paid

    for transaction in transactions:
        try:
            confirm = stripe.checkout.Session.retrieve(
                transaction.transaction_id, )
            if confirm['payment_status'] == "paid":
                transaction.payment_complete = True
                transaction.customer_name = confirm['customer_details']['name']
                transaction.customer_email = confirm['customer_details']['email']
                transaction.save()
                # fill list for confirm transaction via email
                # if transaction.transaction_id not in transactions_to_email:
                #    transactions_to_email.append(transaction.transaction_id)
        except Exception as e:
            print(transaction.id)
            print(e)

    # clear duplitates
    transactions_to_email = set(transactions_to_email)

    # send e-mail about confirm registrations
    for transaction_to_email in transactions_to_email:
        # threading.Thread (target = SendConfirmEmail(transaction_to_email).send_email()).start()
        pass

    # vymaž sessions
    try:
        if request.session.get('sum_fee'):
            del request.session['sum_fee']
        else:
            print("Session sum_fee neexistuje")

        if request.session.get('event'):
            del request.session['event']
        else:
            print("Session event neexistuje")

        if request.session.get('riders_20'):
            del request.session['riders_20']
        else:
            print("Session riders_20 neexistuje")

        if request.session.get('riders_24'):
            del request.session['riders_24']
        else:
            print("Session riders_24 neexistuje")

    except Exception as e:
        print("Chyba " + str(e))

    data = {'event_id': pk}
    return render(request, 'event/success.html', data)


def cancel_view(request):
    return render(request, 'event/cancel.html')


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    print(payload)
    sig_header = request.META['HTTP_STRIPE_SIGNATURE']
    event = None

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_ENDPOINT_SECRET
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
def event_admin_view(request, pk):
    """ Function for Event admin page view"""
    event = Event.objects.get(id=pk)
    __LICENCE_USERNAME = config('LICENCE_USERNAME')
    __LICENCE_PASSWORD = config('LICENCE_PASSWORD')

    # Admin page for European Cup
    if event.type_for_ranking == "Evropský pohár" or event.type_for_ranking == "Mistrovství Evropy":

        payments = 0

        entries_20 = Entry.objects.filter(event=event.id, is_20=True, payment_complete=1, checkout=0)
        entries_24 = Entry.objects.filter(event=event.id, is_24=True, payment_complete=1, checkout=0)

        sum_entiries = entries_20.count() + entries_24.count()

        file_name = f'media/ec-files/EC_RACE_ID-{event.id}-{event.name}.xlsx'
        if event.type_for_ranking == "Evropský pohár":
            wb = load_workbook(filename='media/ec-files/Entries example - UEC.xlsx')
        else:
            wb = load_workbook(filename='media/ec-files/Entries_upload_UEC_Champ_2024.xlsx')
        ws = wb.active

        x = 3


        for entry_20 in entries_20:
            try:
                rider = Rider.objects.get(uci_id=entry_20.rider.uci_id)
                ws.cell(x, 2, rider.uci_id)
                ws.cell(x, 3, rider.date_of_birth)
                ws.cell(x, 4, rider.first_name)
                ws.cell(x, 5, rider.last_name)
                ws.cell(x, 6, gender_resolve_small_letter(rider.gender))
                ws.cell(x, 7, rider.transponder_20)
                if rider.is_elite:
                    ws.cell(x, 9, "x")
                if rider.class_20 == "Women Under 23" or rider.class_20 == "Men Under 23":
                    ws.cell(x, 10, "x")

                x = x + 1
            except:
                pass

            payments += entry_20.fee_20

        for entry_24 in entries_24:
            try:
                rider = Rider.objects.get(uci_id=entry_24.rider.uci_id)
                ws.cell(x, 2, rider.uci_id)
                ws.cell(x, 3, rider.date_of_birth)
                ws.cell(x, 4, rider.first_name)
                ws.cell(x, 5, rider.last_name)
                ws.cell(x, 6, gender_resolve_small_letter(rider.gender))
                ws.cell(x, 7, rider.transponder_24)
                ws.cell(x, 8, "x")

                x = x + 1
            except:
                pass

            payments += entry_24.fee_24

        wb.save(file_name)
        event.ec_file = file_name
        event.ec_file_created = datetime.now()
        event.save()

        # File for insurance company
        file_name = f'media/ec-files/INSURANCE_FOR_RACE_ID-{event.id}-{event.name}.xlsx'
        wb = Workbook()
        wb.encoding = "utf-8"
        ws = wb.active
        ws.title = "INSURANCE"

        ws = insurance_first_line(ws)

        x = 2
        for entry_20 in entries_20:
            try:
                rider = Rider.objects.get(uci_id=entry_20.rider.uci_id, have_valid_insurance=False)

                rider_address = rider.street + ", " + rider.city + ", PSČ: " + rider.zip

                ws.cell(x, 1, rider.class_20)
                ws.cell(x, 2, rider.first_name)
                ws.cell(x, 3, rider.last_name)
                ws.cell(x, 4, date_of_birth_resolve_rem_online(rider.date_of_birth))
                ws.cell(x, 5, rider_address)
                x = x + 1
            except Exception as e:
                print(f"Chyba souboru pojištění: {e}")

        for entry_24 in entries_24:
            try:
                rider = Rider.objects.get(uci_id=entry_24.rider.uci_id, have_valid_insurance=False)

                rider_address = rider.street + ", " + rider.city + ", PSČ: " + rider.zip

                ws.cell(x, 1, rider.class_24)
                ws.cell(x, 2, rider.first_name)
                ws.cell(x, 3, rider.last_name)
                ws.cell(x, 4, date_of_birth_resolve_rem_online(rider.date_of_birth))
                ws.cell(x, 5, rider_address)
                x = x + 1
            except Exception as e:
                print(f"Chyba souboru pojištění: {e}")

        wb.save(file_name)
        event.ec_insurance_file = file_name
        event.ec_insurance_file_created = datetime.now()
        event.save()

        data = {'event': event, "sum_entries": sum_entiries, "payments": payments}
        return render(request, 'event/event-admin-ec.html', data)

    if event.type_for_ranking == "Mistrovství světa":
        pass
    # Admin page for Czech events
    if 'btn-upload-result' in request.POST:
        print("Stisknuto tlačítko nahrát výsledky v BEM")

        if 'result-file' not in request.FILES:  # if xls file is not selected
            messages.error(request, "Musíš vybrat soubor s výsledky závodu")
            return HttpResponseRedirect(reverse('event:event-admin', kwargs={'pk': pk}))

        else:
            print("Nahrávám výsledky")
            result_file = request.FILES.get('result-file')
            result_file_name = result_file.name
            fs = FileSystemStorage('media/xls_results')
            filename = fs.save(result_file_name, result_file)
            uploaded_file_url = fs.url(filename)[6:]
            event = Event.objects.get(id=pk)
            ranking_code = GetResult.ranking_code_resolve(type=event.type_for_ranking)
            data = pd.read_excel('media/xls_results' + uploaded_file_url, sheet_name="Results")
            for i in range(1, len(data.index)):
                uci_id = str(data.iloc[i][1])
                category = data.iloc[i][5]
                place = str(data.iloc[i][0])
                first_name = data.iloc[i][2]
                last_name = data.iloc[i][3]
                club = data.iloc[i][6]
                result = GetResult(event.date, event.id, event.name, ranking_code, uci_id, place, category,
                                   first_name,
                                   last_name, club, event.organizer.team_name, event.type_for_ranking)
                result.write_result()
            event.xls_results = "xls_results" + uploaded_file_url
            event.save()

            SetRanking().start()
            return HttpResponseRedirect(reverse('event:event-admin', kwargs={'pk': pk}))

    if 'btn-delete-xls' in request.POST:
        print("Mažu XLS výsledky")

        Result.objects.filter(event=pk).delete()
        print("Výsledky vymazány")
        SetRanking().start()
        print("Ranking přepočítán")

        xls_file = event.xls_results
        print(f"Budu mazat xls_results {xls_file}")

        try:
            os.remove(f"{xls_file}")
        except Exception as e:
            print(f"Nebyl nalezen soubor {xls_file}")

        event.xls_results.delete(save=True)

        return HttpResponseRedirect(reverse('event:event-admin', kwargs={'pk': pk}))

    # ON LINE ENTRIES FOR BEM
    if 'btn-bem-file' in request.POST:
        print("Vytvoř startovku")
        file_name = f'media/bem-files/BEM_FOR_RACE_ID-{event.id}-{event.name}.xlsx'
        wb = Workbook()
        wb.encoding = "utf-8"
        ws = wb.active
        ws.title = "BEM5_EXT"
        ws = excel_first_line(ws)

        # TODO: entries beginners classes

        entries_20 = Entry.objects.filter(event=event.id, is_20=True, payment_complete=1, checkout=0)
        x = 2
        for entry_20 in entries_20:
            try:
                rider = Rider.objects.get(uci_id=entry_20.rider.uci_id)
                ws.cell(x, 1, rider.uci_id)
                ws.cell(x, 2, rider.uci_id)
                ws.cell(x, 3, rider.uci_id)
                ws.cell(x, 4, rider.uci_id)
                ws.cell(x, 5, rider.uci_id)
                ws.cell(x, 6, expire_licence())
                ws.cell(x, 7, "BMX-RACE")
                ws.cell(x, 9, str(rider.date_of_birth).replace('-', '/'))
                ws.cell(x, 10, rider.first_name)
                ws.cell(x, 11, rider.last_name.upper())
                ws.cell(x, 12, rider.email)
                ws.cell(x, 13, rider.phone)
                ws.cell(x, 14, rider.emergency_contact)
                ws.cell(x, 15, rider.emergency_phone)
                ws.cell(x, 16, gender_resolve(rider))
                ws.cell(x, 17, team_name_resolve(rider.club))
                ws.cell(x, 18, "CZE")
                ws.cell(x, 19, "CZE")
                ws.cell(x, 20, resolve_event_classes(event, rider, is_20=True))
                ws.cell(x, 25, rider.plate)  # plate for cruiser

                if rider.plate_champ_20:
                    world_plate = "W" + str(rider.plate_champ_20)
                else:
                    world_plate = rider.plate

                ws.cell(x, 24, world_plate)
                ws.cell(x, 32, rider.transponder_20)
                ws.cell(x, 33, rider.transponder_24)
                ws.cell(x, 36, "T1")
                ws.cell(x, 37, "T2")
                ws.cell(x, 45, team_name_resolve(rider.club).upper())
                if rider.valid_licence:
                    ws.cell(x, 46, "")
                else:
                    ws.cell(x, 46, "NEPLATNÁ LICENCE")
            except Exception as E:
                pass
            x += 1

            # TODO: Dodělat zobrazení přihlášených jezdců s neplatnou licencí

        del entries_20

        entries_24 = Entry.objects.filter(event=event.id, is_24=True, payment_complete=1, checkout=0)
        for entry_24 in entries_24:
            rider = Rider.objects.get(uci_id=entry_24.rider.uci_id)
            ws.cell(x, 1, rider.uci_id)
            ws.cell(x, 2, rider.uci_id)
            ws.cell(x, 3, rider.uci_id)
            ws.cell(x, 4, rider.uci_id)
            ws.cell(x, 5, rider.uci_id)
            ws.cell(x, 6, expire_licence())
            ws.cell(x, 7, "BMX RACE")
            ws.cell(x, 9, str(rider.date_of_birth).replace('-', '/'))
            ws.cell(x, 10, rider.first_name)
            ws.cell(x, 11, rider.last_name.upper())
            ws.cell(x, 12, rider.email)
            ws.cell(x, 13, rider.phone)
            ws.cell(x, 14, rider.emergency_contact)
            ws.cell(x, 15, rider.emergency_phone)
            ws.cell(x, 16, gender_resolve(rider))
            ws.cell(x, 17, team_name_resolve(rider.club))
            ws.cell(x, 18, "CZE")
            ws.cell(x, 19, "CZE")
            ws.cell(x, 21, resolve_event_classes(event, rider, is_20=False))
            ws.cell(x, 24, rider.plate)

            if rider.plate_champ_24:
                world_plate = "W" + str(rider.plate_champ_24)
            else:
                world_plate = str(rider.plate)

            ws.cell(x, 25, world_plate)
            ws.cell(x, 32, rider.transponder_20)
            ws.cell(x, 33, rider.transponder_24)
            ws.cell(x, 36, "T1")
            ws.cell(x, 37, "T2")
            ws.cell(x, 45, team_name_resolve(rider.club).upper())
            if rider.valid_licence:
                ws.cell(x, 46, "")
            else:
                ws.cell(x, 46, "NEPLATNÁ LICENCE")

            x += 1
        del entries_24

        # TODO: Add foreign riders

        wb.save(file_name)
        event.bem_entries = file_name
        event.bem_entries_created = datetime.now()
        event.save()

    # ALL RIDERS FOR BEM 
    if 'btn-riders-list' in request.POST:
        file_name = f'media/riders-list/RIDERS_LIST_FOR_RACE_ID-{event.id}.xlsx'
        wb = Workbook()
        wb.encoding = "utf-8"
        ws = wb.active
        ws.title = "BEM5_EXT"
        ws = excel_first_line(ws)

        riders = Rider.objects.filter(is_active=True, is_approwe=True)
        x = 2
        for rider in riders:
            ws.cell(x, 1, rider.uci_id)
            ws.cell(x, 2, rider.uci_id)
            ws.cell(x, 3, rider.uci_id)
            ws.cell(x, 4, rider.uci_id)
            ws.cell(x, 5, rider.uci_id)
            ws.cell(x, 6, expire_licence())
            ws.cell(x, 7, "BMX-RACE")
            ws.cell(x, 9, str(rider.date_of_birth).replace('-', '/'))
            ws.cell(x, 10, rider.first_name)
            ws.cell(x, 11, rider.last_name.upper())
            ws.cell(x, 12, rider.email)
            ws.cell(x, 13, rider.phone)
            ws.cell(x, 14, rider.emergency_contact)
            ws.cell(x, 15, rider.emergency_phone)
            ws.cell(x, 16, gender_resolve(rider))
            ws.cell(x, 17, team_name_resolve(rider.club))
            ws.cell(x, 18, "CZE")
            ws.cell(x, 19, "CZE")
            if rider.is_20:
                ws.cell(x, 20, resolve_event_classes(event, rider,  is_20=True))
            if rider.is_24:
                ws.cell(x, 21, resolve_event_classes(event, rider, is_20=False))
            ws.cell(x, 28, "")
            ws.cell(x, 29, "")

            if rider.plate_champ_20:
                rider.plate = rider.plate_champ_20

            ws.cell(x, 24, rider.plate)

            if rider.plate_champ_24:
                rider.plate = rider.plate_champ_24

            ws.cell(x, 25, rider.plate)
            ws.cell(x, 32, rider.transponder_20)
            ws.cell(x, 33, rider.transponder_24)
            ws.cell(x, 36, "T1")
            ws.cell(x, 37, "T2")
            ws.cell(x, 45, team_name_resolve(rider.club).upper())
            if rider.valid_licence:
                ws.cell(x, 46, "")
            else:
                ws.cell(x, 46, "NEPLATNÁ LICENCE")
            x += 1

        del riders
        print("Čeští jezdci přidány")
        # foreign_riders = ForeignRider.objects.all()
        # for foreign_rider in foreign_riders:
        #     ws.cell(x, 1, foreign_rider.uci_id)
        #     ws.cell(x, 2, foreign_rider.uci_id)
        #     ws.cell(x, 3, foreign_rider.uci_id)
        #     ws.cell(x, 4, foreign_rider.uci_id)
        #     ws.cell(x, 5, foreign_rider.uci_id)
        #     ws.cell(x, 6, expire_licence())
        #     ws.cell(x, 7, "BMX-RACE")
        #     ws.cell(x, 9, str(foreign_rider.date_of_birth).replace('-', '/'))
        #     ws.cell(x, 10, foreign_rider.first_name)
        #     ws.cell(x, 11, foreign_rider.last_name.upper())
        #     ws.cell(x, 16, gender_resolve(foreign_rider))
        #     ws.cell(x, 17, foreign_club_resolve(foreign_rider.state))
        #     ws.cell(x, 18, foreign_rider.state)
        #     ws.cell(x, 19, foreign_rider.state)
        #     if foreign_rider.is_20:
        #         ws.cell(x, 20, resolve_event_classes(event.id, foreign_rider.gender, True, foreign_rider.class_20, 1))
        #     if foreign_rider.is_24:
        #         ws.cell(x, 21, resolve_event_classes(event.id, foreign_rider.gender, False, foreign_rider.class_24, 0))
        #     ws.cell(x, 28, "")
        #     ws.cell(x, 29, "")
        #     ws.cell(x, 24, foreign_rider.plate)
        #     ws.cell(x, 25, foreign_rider.plate)
        #     ws.cell(x, 32, foreign_rider.transponder_20)
        #     ws.cell(x, 33, foreign_rider.transponder_24)
        #     ws.cell(x, 36, "T1")
        #     ws.cell(x, 37, "T2")
        #     ws.cell(x, 45, foreign_rider.club.upper())
        #     x += 1
        # del foreign_riders

        wb.save(file_name)
        event.bem_riders_list = file_name
        event.bem_riders_created = datetime.now()
        event.save()

    # ON LINE ENTRIES FOR REM
    if 'btn-rem-file' in request.POST:
        all_entries = REMRiders()
        all_entries.event = event
        all_entries.create_entries_list()

    # ALL RIDERS FOR REM
    if 'btn-rem-riders-list' in request.POST:
        all_riders = REMRiders()
        all_riders.event = event
        all_riders.create_all_riders_list()

    if 'btn-upload-txt' in request.POST:

        if 'result-file-txt' not in request.FILES:  # if txt file is not selected
            messages.error(request, "Musíš vybrat soubor s výsledky závodu")
            return HttpResponseRedirect(reverse('event:event-admin', kwargs={'pk': pk}))

        if request.POST['btn-upload-txt'] == 'txt':
            print("Nahrávám výsledky z REM")
            result_file = request.FILES.get('result-file-txt')
            result_file_name = result_file.name
            fs = FileSystemStorage('media/rem_results')
            filename = fs.save(result_file_name, result_file)
            uploaded_file_url = fs.url(filename)[6:]
            event = Event.objects.get(id=pk)
            results = SetResults()
            results.setEvent(pk)
            results.setFile(uploaded_file_url)
            results.start()

    if 'btn-txt-delete' in request.POST:
        print("Mažu výsledky závodu")
        Result.objects.filter(event=pk).delete()
        print("Výsledky vymazány")

        SetRanking().start()

        rem_file = event.rem_results
        print(f"Budu mazat rem_results {rem_file}")

        try:
            os.remove(f"{rem_file}")
        except Exception as e:
            print(f"Nebyl nalezen soubor {rem_file}")

        event.rem_results.delete(save=True)

    sum_of_fees: int = 0
    sum_of_riders: int = 0

    # check riders with invalid licences
    invalid_licences = invalid_licence_in_event(event)

    # sum fees on event
    entries = Entry.objects.filter(event=event.id, payment_complete=1, checkout=False)

    for entry in entries:
        sum_of_fees += entry.fee_beginner
        sum_of_fees += entry.fee_20
        sum_of_fees += entry.fee_24
        sum_of_riders += 1

    organizer_fee = int(sum_of_fees - (sum_of_fees * event.commission_fee / 100))

    data = {'event': event, "invalid_licences": invalid_licences, "sum_of_fees": sum_of_fees,
            "sum_of_riders": sum_of_riders, 'organizer_fee': organizer_fee}
    return render(request, 'event/event-admin.html', data)


@staff_member_required
def find_payment_view(request):
    """ Views for find e-mail address recorded in payment status """

    events = Event.objects.filter()

    if 'find-payment' in request.POST:
        rider = request.POST['rider']
        event = request.POST['event']
        try:
            entry = Entry.objects.get(event=event.id, rider=rider.uci_id, payment_complete=True)
            rider = Rider.objects.get(uci_id=rider)
            event = Event.objects.get(id=event)
        except Exception as e:
            pass

        data = {'event': event, 'rider': rider, 'entry': entry}

    data = {'events': events}
    return render(request, 'event/find-payment.html', data)


def ranking_table_view(request):
    """ Function for viewing ranking table of points"""
    data = {}
    return render(request, 'event/ranking-table.html', data)


def entry_foreign_view(request, pk):
    """ View for foreign riders registrations"""
    event = get_object_or_404(Event, pk=pk)
    data = {'event': event}
    views = render(request, 'event/entry-foreign.html', data)
    return views


def ec_by_club_xls(request, pk):
    event = get_object_or_404(Event, pk=pk)
    clubs = Club.objects.filter(is_active=True).order_by('team_name')
    entries = Entry.objects.filter(event=pk, payment_complete=True).order_by('rider')

    file_name = f'media/ec-files/EC_RACE_ID_BY_CLUB-{event.id}-{event.name}.xlsx'

    response = HttpResponse(content_type='application/ms-excel')
    response['Content-Disposition'] = f'attachment; filename="{file_name}"'

    wb = load_workbook(filename='media/ec-files/Club example - UEC.xlsx')
    ws = wb.active

    ws.cell(3, 2, event.name)

    line = 6
    for club in clubs:
        for entry in entries:
            rider = Rider.objects.get(id=entry.rider.id)
            if rider.club.id == club.id:
                ws.cell(line, 1, rider.last_name)
                ws.cell(line, 2, rider.first_name)
                ws.cell(line, 3, rider.uci_id)
                ws.cell(line, 4, rider.club.team_name)

                line += 1
    wb.save(response)

    return response


def summary_riders_in_event(request, pk):
    event = Event.objects.get(id=pk)

    classes_20_24 = clean_classes_on_event(event)
    count_20_24 = []

    for class_20_24 in classes_20_24:
        sum_20_24 = NumberInEvent()
        sum_20_24.event = pk
        sum_20_24.category_name = class_20_24
        if class_20_24 is None:
            pass
        elif ("Cruiser" or "cruiser") in class_20_24:
            sum_20_24.count_riders_24()
        elif "Beginners" in class_20_24:
            sum_20_24.count_beginners()
        else:
            sum_20_24.count_riders_20()
        if class_20_24 is not None and ("NENÍ VYPSÁNO" or "není vypsáno") not in class_20_24:
            count_20_24.append(sum_20_24)

    data = {'count_20': count_20_24}

    return render(request, 'event/riders-sum-event.html', data)


@login_required(login_url="/login/")
def confirm_user_order(request):
    # aktualizuj košík
    update_cart(request)
    # vymaž propadnuté registrace, rigistrace již byla ukončena a nebyla zaplacena
    delete_reg = Entry.objects.filter(user__id=request.user.id, payment_complete=False,
                                      event__reg_open_to__lt=datetime.now())
    if delete_reg:
        delete_reg.delete()
        return redirect('event:order')
    # načti platné registrace v nákupním košíku
    orders = Entry.objects.filter(user__id=request.user.id, payment_complete=False,
                                  event__date__gte=datetime.now()).order_by('event__date', 'rider__last_name',
                                                                            'rider__first_name')
    duplicities = []

    if 'btn-del' in request.POST:
        order = Entry.objects.get(id=request.POST['btn-del'])
        order.delete()
        update_cart(request)
        return redirect('event:order')

    if request.POST:
        line_items = []
        price: int = 0
        for order in orders:
            print(order)
            if order.is_beginner:
                line_items += generate_stripe_line(order.event, order.rider, is_20=True, is_beginner=True)
                if check_entry_duplicity(order.event, order.rider, is_beginner=True):
                    duplicities.append(order)
                    order.delete()
                else:
                    price += order.fee_beginner + order.fee_20 + order.fee_24
            elif order.is_20:
                line_items += generate_stripe_line(order.event, order.rider, is_20=True)
                if check_entry_duplicity(order.event, order.rider, is_20=True):
                    duplicities.append(order)
                    order.delete()
                else:
                    price += order.fee_beginner + order.fee_20 + order.fee_24
            else:
                line_items += generate_stripe_line(order.event, order.rider, is_20=False)
                if check_entry_duplicity(order.event, order.rider, is_24=True):
                    duplicities.append(order)
                    order.delete()
                else:
                    price += order.fee_beginner + order.fee_20 + order.fee_24
        if duplicities:
            orders = Entry.objects.filter(user__id=request.user.id, payment_complete=False).order_by('event__date',
                                                                                                     'rider__last_name')
            sum: int = orders.count()
            data = {'orders': orders, 'price': price, 'sum': sum, "duplicities": duplicities}
            return render(request, 'event/order.html', data)
        print(line_items)
        try:
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=line_items,
                mode='payment',
                success_url=settings.YOUR_DOMAIN + '/event/success',
                cancel_url=settings.YOUR_DOMAIN + '/event/cancel',
            )
            for order in orders:
                order.transaction_id = checkout_session.id
                order.save()
            return redirect(checkout_session.url, code=303)
        except Exception as e:
            return JsonResponse(error=str(e)), 403

    price: int = 0
    sum: int = orders.count()
    for order in orders:
        price += order.fee_beginner + order.fee_20 + order.fee_24
        if order.is_beginner:
            order.event_class = order.class_beginner
        elif order.is_20:
            order.event_class = order.class_20
        else:
            order.event_class = order.class_24
    data = {'orders': orders, 'price': price, 'sum': sum}
    return render(request, 'event/order.html', data)


def check_order_payments(request):
    orders = Entry.objects.filter(Q(updated__year=date.today().year,
                                    updated__month=date.today().month,
                                    updated__day=date.today().day,
                                    payment_complete=False, ) |
                                  Q(updated__year=date.today().year,
                                    updated__month=date.today().month,
                                    updated__day=date.today().day - 1,
                                    payment_complete=False, ))
    for order in orders:
        try:
            confirm = stripe.checkout.Session.retrieve(
                order.stripe_payload, )
            if confirm['payment_status'] == "paid":
                order.confirmed = True
                order.save()
        except Exception as e:
            print(e)

    transactions = Entry.objects.filter(Q(transaction_date__year=date.today().year,
                                          transaction_date__month=date.today().month,
                                          transaction_date__day=date.today().day,
                                          payment_complete=False, ) |
                                        (Q(transaction_date__year=date.today().year,
                                           transaction_date__month=date.today().month,
                                           transaction_date__day=date.today().day - 1,
                                           payment_complete=False, )))
    for transaction in transactions:
        try:
            confirm = stripe.checkout.Session.retrieve(
                transaction.transaction_id, )
            if confirm['payment_status'] == "paid":
                transaction.payment_complete = True
                transaction.customer_name = confirm['customer_details']['name']
                transaction.customer_email = confirm['customer_details']['email']
                transaction.save()
        except:
            pass

    update_cart(request)
    messages.success(request, "Vaše přihláška byla úspěšně přijata.")
    data = {}
    return render(request, 'event/success.html', data)


@login_required(login_url="/login/")
def checkout_view(request):
    user_id = request.user.id
    user = Account.objects.get(id=user_id)
    confirmed_events = Entry.objects.filter(user__id=user_id, payment_complete=True,
                                            event__date__gte=datetime.now()).order_by('event__date', 'rider__last_name',
                                                                                      'rider__first_name')
    for confirmed_event in confirmed_events:
        if is_registration_open(confirmed_event.event):
            confirmed_event.is_visible = True
        else:
            confirmed_event.is_visible = False
    # if user want change status
    if 'btn-change' in request.POST:
        confirmed_event = Entry.objects.get(id=request.POST['btn-change'])
        if confirmed_event.checkout:
            confirmed_event.checkout = False
            confirmed_event.save()
        else:
            confirmed_event.checkout = True
            confirmed_event.save()
        return redirect('event:checkout')

    else:
        data = {'confirmed_events': confirmed_events, 'user': user}
        return render(request, 'event/event-checkout.html', data)


@login_required(login_url="/login/")
def fees_on_event(request, pk):
    """ Function for print fees in event by club"""
    event = Event.objects.get(pk=pk)
    entries = Entry.objects.filter(event=pk, checkout=False)
    clubs = Club.objects.filter(is_active=True).order_by('team_name')
    club_in_event = []
    for club in clubs:
        fee = 0
        for entry in entries:
            if club == entry.rider.club:
                fee += entry.fee_20 + entry.fee_24 + entry.fee_beginner
        if fee > 0:
            club.fee = fee
            club_in_event.append(club)
    data = {"clubs": club_in_event, "event": event}
    return render(request, 'event/fees-on-event.html', data)
