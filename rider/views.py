import os

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.mail import send_mail
from django.views.decorators.cache import cache_control
from django.contrib.admin.views.decorators import staff_member_required

from bmx import settings
from .models import Rider
from .rider import two_years_inactive, CheckValidLicenceThread, Participation, Cruiser, RiderSetClassesThread, \
    first_line_riders_by_club_and_class, RiderQualifyToCNThread
from func.rider import set_all_riders_classes
from club.models import Club
import json
from event.models import Result
from ranking.ranking import RankPositionCount
import datetime
from datetime import date
import requests
import requests.packages
from decouple import config
from openpyxl import Workbook

# Global variables
now = date.today().year


# Create your views here.

def riders_list_view(request):
    riders = Rider.objects.filter(is_active=True, is_approwe=True)
    data = {'riders': riders}

    return render(request, 'rider/riders-list.html', data)


def rider_detail_view(request, pk):
    rider = get_object_or_404(Rider, uci_id=pk)
    results = Result.objects.filter(rider=rider.uci_id,
                                    date__gte=datetime.datetime.now() - datetime.timedelta(days=365)).order_by('date')
    data = {'rider': rider, 'results': results}
    return render(request, 'rider/rider-detail.html', data)


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@staff_member_required
def rider_admin(request):
    total_riders = Rider.objects.filter().count()
    active_riders = Rider.objects.filter(is_active=True).count()
    data = {'total_riders': total_riders, 'active_riders': active_riders}
    return render(request, 'rider/rider-admin.html', data)


def rider_new_view(request):
    """ View for new rider form """

    # User fill data and send form
    if request.method == "POST":

        clubs = Club.objects.filter(is_active=True)

        # getting all used plates list
        used_plates = []
        riders = Rider.objects.filter(is_active=True)

        for rider in riders:
            used_plates += [rider.plate]

        # create free plates list
        free_plates = [plate for plate in range(10, 1000) if plate not in used_plates]
        print(free_plates)

        # get data from UCI API and put this data to the second form
        if 'num11' in request.POST and 'first-name' not in request.POST:

            num1 = request.POST['num1']
            num2 = request.POST['num2']
            num3 = request.POST['num3']
            num4 = request.POST['num4']
            num5 = request.POST['num5']
            num6 = request.POST['num6']
            num7 = request.POST['num7']
            num8 = request.POST['num8']
            num9 = request.POST['num9']
            num10 = request.POST['num10']
            num11 = request.POST['num11']
            uci_id = str(num1) + str(num2) + str(num3) + str(num4) + str(num5) + str(num6) + str(num7) + str(
                num8) + str(num9) + str(num10) + str(num11)
            # url_uci = f"https://ucibws.uci.ch/api/contacts/riders?filter.uciid={uci_id}"

            username = config('LICENCE_USERNAME')
            password = config('LICENCE_PASSWORD')

            basicAuthCredentials = (username, password)
            url_uciid = f"https://data.ceskysvazcyklistiky.cz/licence-api/get-by?uciId={uci_id}"
            data_json = requests.get(url_uciid, auth=basicAuthCredentials, verify=False)
            data_json = data_json.text

            if "\Http_NotFound" in data_json:
                print("Tato licence neexistuje")
                message = f"Licence UCI ID: {uci_id} nebyla Českým svazem cyklistiky vystavena. Zkuste to znovu se správným číslem nebo kontaktujte Komisi BMX Českého svazu cyklistiky."
                data = {'message': message}
                return render(request, 'rider/rider-new-error.html', data)
            data_json = json.loads(data_json)

            gender = data_json['sex']
            if gender['code'] == "F":
                gender = "Žena"
            else:
                gender = "Muž"

            try:
                data_new_rider = {'first_name': data_json['firstname'], 'last_name': data_json['lastname'],
                                  'date_of_birth': data_json['birth'][0:10], 'clubs': clubs,
                                  'free_plates': free_plates, 'uci_id': data_json['uci_id'], 'gender': gender}
                request.session['first_name'] = data_json['firstname']
                request.session['last_name'] = data_json['lastname'].capitalize()
                request.session['date_of_birth'] = data_json['birth'][0:10]
                request.session['gender'] = gender
                request.session['uci_id'] = uci_id
                rider_exist = False
                try:
                    rider = Rider.objects.get(uci_id=request.session['uci_id'])
                    rider_exist = True
                except:
                    pass

                if rider_exist:
                    message = f"Jezdec/jezdkyně {rider.first_name} {rider.last_name}, UCI ID {rider.uci_id}, již má přiděleno permanentní startovní číslo. Kontatujte Komisi BMX Českého svazu cyklistiky."
                    data = {'message': message}
                    return render(request, 'rider/rider-new-error.html', data)

                return render(request, 'rider/rider-new-2.html', data_new_rider)
            except Exception as error:
                print(f"Chyba v session - {error}")

        # get data from form and save new rider
        else:
            # TODO: Dodělat ověření vyplnění všech údajů, v případě chyby zobrazit alert

            if request.POST['email'].strip() == "":
                print("Není vyplněn e-mail")
                messages.error(request, "Nevyplnil/a jsi e-mailovou adresu. Jedná se o povinný údaj.")
                data_new_rider = {'first_name': request.session['first_name'],
                                  'last_name': request.session['last_name'],
                                  'date_of_birth': request.session['date_of_birth'],
                                  'gender': request.session['gender'],
                                  'clubs': clubs, 'free_plates': free_plates, 'uci_id': request.session['uci_id'],
                                  }
                return render(request, 'rider/rider-new-2.html', data_new_rider)
            else:
                # TODO: Dodělat ověření správnosti e-mailové adresy
                pass

            if request.POST['plate'] == "Vyber...":
                print("Není vybráno startovní číslo")
                messages.error(request, "Nevybral/a jsi startovní číslo. Jedná se o povinný údaj.")
                data_new_rider = {'first_name': request.session['first_name'],
                                  'last_name': request.session['last_name'],
                                  'date_of_birth': request.session['date_of_birth'],
                                  'gender': request.session['gender'],
                                  'clubs': clubs, 'free_plates': free_plates, 'uci_id': request.session['uci_id'],
                                  }
                return render(request, 'rider/rider-new-2.html', data_new_rider)

            if ('is20') not in request.POST and ('is24') not in request.POST:
                print("Není vybrána kategorie")
                messages.error(request,
                               "Nevyplnil/a jsi, zda budeš jezdit na 20-ti palcovém kole či na Cruiseru. Jedná se o povinný údaj.")
                data_new_rider = {'first_name': request.session['first_name'],
                                  'last_name': request.session['last_name'],
                                  'date_of_birth': request.session['date_of_birth'],
                                  'gender': request.session['gender'],
                                  'clubs': clubs, 'free_plates': free_plates, 'uci_id': request.session['uci_id'],
                                  }
                return render(request, 'rider/rider-new-2.html', data_new_rider)

            if request.POST['club'] == "Vyber...":
                print("Není vybrán klub")
                messages.error(request, "Nevybral jsi svůj klub. Jedná se o povinný údaj.")
                data_new_rider = {'first_name': request.session['first_name'],
                                  'last_name': request.session['last_name'],
                                  'date_of_birth': request.session['date_of_birth'],
                                  'gender': request.session['gender'],
                                  'clubs': clubs, 'free_plates': free_plates, 'uci_id': request.session['uci_id'],
                                  }
                return render(request, 'rider/rider-new-2.html', data_new_rider)

            is_20 = 1 if 'is20' in request.POST else 0
            is_24 = 1 if 'is24' in request.POST else 0
            have_girls_bonus = 1 if 'bonus' in request.POST else 0
            is_elite = 1 if 'elite' in request.POST else 0
            new_rider = Rider.objects.create(
                first_name=request.session['first_name'],
                last_name=request.session['last_name'],
                date_of_birth=datetime.datetime.strptime(request.session['date_of_birth'], "%Y-%m-%d"),
                gender=request.session['gender'],
                street=request.POST['street_address'],
                city=request.POST['city'],
                zip=request.POST['zip'],
                uci_id=request.session['uci_id'],
                is_20=is_20,
                is_24=is_24,
                is_elite=is_elite,
                have_girl_bonus=have_girls_bonus,
                email=request.POST['email'],
                plate=request.POST['plate'],
                club=Club.objects.get(id=request.POST['club']),
                is_active=1,
                is_approwe=0,
                emergency_contact=request.POST['emergency-contact'],
                emergency_phone=request.POST['emergency-phone'],
            )
            new_rider.save()

            # TODO: Vylepšit odeslání e-mailového potvrzení HTML
            # send_mail (
            #     subject = "NOVÁ ŽÁDOST O PERMANENTNÍ STARTOVNÍ ČÍSLO",
            #     message = f"V aplikaci www.czechbmx.cz byla podána nová žádost o startovní číslo jezdce {request.session['first_name']} {request.session['last_name']}. Prosím o její vyřízení",
            #     from_email = "bmx@ceskysvazcyklistiky.cz",
            #     recipient_list = ["david@black-ops.eu"],)

        return render(request, 'rider/rider-new-3.html')

    # rendering in GET method
    return render(request, 'rider/rider-new.html')


@staff_member_required
def inactive_riders_views(request):
    """ Function for views inactive riders, only request params"""
    inactive_riders = two_years_inactive()
    data = {'riders': inactive_riders, 'sum': len(inactive_riders)}
    return render(request, 'rider/rider-inactive.html', data)


@staff_member_required
def licence_check_views(request):
    """ Function for checking valid licence"""
    CheckValidLicenceThread().start()
    messages.success(request, "Ověřování platnosti licencí probíhá na pozadí.")
    data = {}
    return render(request, 'rider/rider-success.html', data)


@staff_member_required
def ranking_count_views(request):
    """ Function for recount ranking"""
    RankPositionCount().count_ranking_position()
    return render(request, 'rider/rider-rank.html')


def participation_riders_on_event(request):
    participation = Participation().count()

    file_path = os.path.join(settings.MEDIA_ROOT, 'participation/participation.xlsx')
    if os.path.exists(file_path):
        with open(file_path, 'rb') as fh:
            response = HttpResponse(fh.read(), content_type="application/vnd.ms-excel")
            response['Content-Disposition'] = 'inline; filename=' + os.path.basename(file_path)
            return response


@staff_member_required
def recalculate_riders_classes(request):
    # set_all_riders_classes()
    RiderSetClassesThread().start()
    messages.success(request, "Kategorie jezdců jsou přepočítávány na pozadí.")
    data = {}
    return render(request, 'rider/rider-success.html', data)


@staff_member_required
def calculate_cruiser_median(request):
    cruiser = Cruiser()
    cruiser.set_number_of_cups(5)
    cruiser_results = cruiser.calculate_median()
    count_cruiser_results = len(cruiser_results)

    data = {'cruisers': cruiser_results, 'sum': count_cruiser_results}
    return render(request, 'rider/rider-cruiser.html', data)


@login_required
def riders_by_class_and_club(request):
    if not request.user.is_admin or not request.user.is_superuser:
        return redirect('news:homepage')

    clubs = Club.objects.filter(is_active=True).order_by('team_name')
    file_name = 'RIDERS_BY_CLUB_AND_CLASS.xlsx'

    response = HttpResponse(content_type='application/ms-excel')
    response['Content-Disposition'] = f'attachment; filename="{file_name}"'

    wb = Workbook()
    ws = wb.active

    first_line_riders_by_club_and_class(ws)

    row = 2
    for club in clubs:
        ws.cell(row, 1, club.team_name)
        ws.cell(row, 2, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Boys 6").count())
        ws.cell(row, 3, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Boys 7").count())
        ws.cell(row, 4, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Girls 7").count())
        ws.cell(row, 5, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Boys 8").count())
        ws.cell(row, 6, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Girls 8").count())
        ws.cell(row, 7, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Boys 9").count())
        ws.cell(row, 8, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Girls 9").count())
        ws.cell(row, 9, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Boys 10").count())
        ws.cell(row, 10, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Girls 10").count())
        ws.cell(row, 11, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Boys 11").count())
        ws.cell(row, 12, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Girls 11").count())
        ws.cell(row, 13, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Boys 12").count())
        ws.cell(row, 14, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Girls 12").count())
        ws.cell(row, 15, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Boys 13").count())
        ws.cell(row, 16, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Girls 13").count())
        ws.cell(row, 17, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Boys 14").count())
        ws.cell(row, 18, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Girls 14").count())
        ws.cell(row, 19, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Boys 15").count())
        ws.cell(row, 20, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Girls 15").count())
        ws.cell(row, 21, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Boys 16").count())
        ws.cell(row, 22, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Girls 16").count())
        ws.cell(row, 23, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Men 17-24").count())
        ws.cell(row, 24,
                Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Women 17-24").count())
        ws.cell(row, 25, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Men 25-29").count())
        ws.cell(row, 26,
                Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Women 25 and over").count())
        ws.cell(row, 27, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Men 30-34").count())
        ws.cell(row, 28,
                Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Men 35 and over").count())
        ws.cell(row, 29,
                Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Men Junior").count())
        ws.cell(row, 30,
                Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Women Junior").count())
        ws.cell(row, 31,
                Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Men Under 23").count())
        ws.cell(row, 32,
                Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Women Under 23").count())
        ws.cell(row, 33, Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Men Elite").count())
        ws.cell(row, 34,
                Rider.objects.filter(is_active=True, is_approwe=True, club=club, class_20="Women Elite").count())

        row += 1
    wb.save(response)

    return response

def qualify_to_cn(request):
    RiderQualifyToCNThread().start()
    messages.success(request, "Kvalifikace na Mistrovství České republiky je počítána na pozadí.")
    data = {}
    return render(request, 'rider/rider-success.html', data)
