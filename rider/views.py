from django.shortcuts import render, get_object_or_404
from django.contrib import messages
from django.core.mail import send_mail
from django.views.decorators.cache import cache_control
from django.contrib.admin.views.decorators import staff_member_required
from .models import Rider
from .rider import valid_licence_control, two_years_inactive, CheckValidLicenceThread
from club.models import Club
import urllib.request, json
from event.models import Result
from ranking.ranking import RankPositionCount
import datetime
from datetime import date
import requests
import requests.packages
import urllib3
import re
import threading
from decouple import config

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

    return render(request, 'rider/rider-admin.html')


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
            uci_id = str(num1)+str(num2)+str(num3)+str(num4)+str(num5)+str(num6)+str(num7)+str(num8)+str(num9)+str(num10)+str(num11)
            # url_uci = f"https://ucibws.uci.ch/api/contacts/riders?filter.uciid={uci_id}"

            username = config('LICENCE_USERNAME')
            password = config('LICENCE_PASSWORD')

            print(username)
            basicAuthCredentials = (username, password)
            url_uciid = f"https://data.ceskysvazcyklistiky.cz/licence-api/get-by?uciId={uci_id}"
            print(url_uciid)
            data_json = requests.get(url_uciid, auth=basicAuthCredentials, verify=False)
            print(data_json)
            data_json = data_json.text
            data_json = json.loads(data_json)
            print(data_json)
            print(data_json['lastname'])
            print(data_json['sex'])

            gender = data_json['sex']
            if gender['code'] == "F":
                gender = "Žena"
            else:
                gender = "Muž"

            try:
                data_new_rider = {'first_name': data_json['firstname'], 'last_name': data_json['lastname'],
                                 'date_of_birth': data_json['birth'][0:10], 'clubs': clubs,
                                 'free_plates': free_plates, 'uci_id': data_json['uci_id'], 'gender': gender}
                print(data_new_rider)
                request.session['first_name'] = data_json['firstname']
                request.session['last_name'] = data_json['lastname'].capitalize()
                request.session['date_of_birth'] = data_json['birth'][0:10]
                request.session['gender'] = gender
                request.session['uci_id'] = uci_id

                return render(request, 'rider/rider-new-2.html', data_new_rider)
            except:
                print("Chyba")

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
                messages.error(request, "Nevyplnil/a jsi, zda budeš jezdit na 20-ti palcovém kole či na Cruiseru. Jedná se o povinný údaj.")
                data_new_rider = {'first_name': request.session['first_name'],
                                  'last_name': request.session['last_name'],
                                  'date_of_birth': request.session['date_of_birth'],
                                  'gender': request.session['gender'],
                                  'clubs': clubs, 'free_plates': free_plates, 'uci_id': request.session['uci_id'],
                                  }
                return render(request, 'rider/rider-new-2.html', data_new_rider)

            if request.POST['club'] == "Vyber...":
                print("Není vybrán klub")
                messages.error(request,  "Nevybral jsi svůj klub. Jedná se o povinný údaj.")
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
            #     message = "V aplikaci www.czechbmx,cz byla podána nová žádost o startovní číslo. Prosím o její vyřízení",
            #     from_email = "bmx@ceskysvazcyklistiky.cz",
            #     recipient_list = ["david@black-ops.eu"],
            #)
        return render(request, 'rider/rider-new-3.html')

    # rendering in GET method
    return render(request, 'rider/rider-new.html')


@staff_member_required
def inactive_riders_views(request):
    """ Function for views inactive riders, only request params"""
    inactive_riders = two_years_inactive()

    data={'riders': inactive_riders}

    return render(request, 'rider/rider-inactive.html', data)


@staff_member_required
def licence_check_views(request):
    
    #valid_licence_control()

    CheckValidLicenceThread().start()

    data={}
    return render (request, 'rider/rider-licence.html', data)


@staff_member_required
def ranking_count_views(request):
    """ Function for recount ranking"""
    # threading.Thread(target=RankPositionCount().count_ranking_position(), daemon=True).start()
    RankPositionCount().count_ranking_position()
    return render(request, 'rider/rider-rank.html')