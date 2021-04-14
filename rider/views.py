from django.shortcuts import render, get_object_or_404
from django.contrib import messages
from .models import Rider
from club.models import Club
import urllib.request, json
from event.models import Result
import datetime


# Create your views here.

def RidersListView(request):
    riders = Rider.objects.filter(is_active=True)
    data = {'riders': riders}

    return render(request, 'rider/riders-list.html', data)


def RiderDetailView(request, pk):
    rider = get_object_or_404(Rider, pk=pk)
    rider.set_class_20()
    rider.set_class_24()

    results = Result.objects.filter(rider=rider.uci_id,
                                    date__gte=datetime.datetime.now() - datetime.timedelta(days=365)).order_by('date')
    data = {'rider': rider, 'results': results}
    return render(request, 'rider/rider-detail.html', data)


def RiderNewView(request):
    """View for new rider form"""
    clubs = Club.objects.filter(is_active=True)

    # getting all used plates list
    used_plates = []
    riders = Rider.objects.filter(is_active=True)
    for rider in riders:
        used_plates += [rider.plate]

    # create free plates list
    free_plates = [plate for plate in range(10, 1000) if plate not in used_plates]

    # User fill data and send form
    if request.method == "POST":
        # get data from UCI API and put this data to the second form
        if 'num11' in request.POST and 'InputFirstName' not in request.POST:

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
            url_uci = f"https://ucibws.uci.ch/api/contacts/riders?filter.uciid={uci_id}"
            print(f"Url je {url_uci}")
            with urllib.request.urlopen(url_uci) as url:
                data_json = json.loads(url.read().decode())
                # TODO: Dodělat časové omezení alertu
                # check, if UCI ID exist
                if len(data_json) == 0:
                    messages.error(request, "Toto UCI ID v databázi UCI neexistuje. Zkontrolujte prosím jeho správnost.")
                    data = {}
                    return render(request, 'rider/rider-new.html', data)
                else:
                    # check, if rider is CZE nationality
                    if data_json[0]['Nationality'] != "CZE":
                        messages.error(request, "Držitel tohoto UCI ID nemá českou národnost. Pokud jste cizinec a chcete mít české startovní číslo, kontaktujte Komisi BMX Českého svazu cyklisitky.")
                        data = {}
                        return render(request, 'rider/rider-new.html', data)

                    # check, if rider have plate now
                    rider_check = Rider.objects.filter(uci_id=uci_id)
                    if len(rider_check) == 1:
                        messages.error(request, f"UCI ID: {uci_id} je přiděleno jezdci {rider_check[0].first_name} {rider_check[0].last_name} a ten již má přiděleno startovní číslo {rider_check[0].plate}.")
                        data = {}
                        return render(request, 'rider/rider-new.html', data)

                    if data_json[0]['Gender'] == "Male":
                        gender = "Muž"
                    else:
                        gender = "Žena"
                    data_new_rider = {'first_name': data_json[0]['FirstName'], 'last_name': data_json[0]['LastName'],
                                      'date_of_birth': data_json[0]['Birthdate'][0:10], 'gender': gender,}
                    request.session['first_name'] = data_json[0]['FirstName']
                    request.session['last_name'] = data_json[0]['LastName'].capitalize()
                    request.session['date_of_birth'] = data_json[0]['Birthdate'][0:10]
                    request.session['gender'] = gender
                    request.session['uci_id'] = uci_id

                    return render(request, 'rider/rider-new-2.html', data_new_rider)

        # get data form form and save new rider
        else:
            # TODO: Dodělat ověření vyplnění všech údajů, v případě chyby zobrazit alert
            print(request.POST)
            if request.POST['InputEmail'].strip() == "":
                print("Není vyplněn e-mail")
                messages.error(request, "Nevyplnil/a jsi e-mailovou adresu. Jedná se o povinný údaj.")
                data_new_rider = {'first_name': request.session['first_name'],
                                  'last_name': request.session['last_name'],
                                  'date_of_birth': request.session['date_of_birth'],
                                  'gender': request.session['gender'],
                                  'clubs': clubs, 'free_plates': free_plates, 'uci_id': request.session['uci_id'],
                }
                return render(request, 'rider/rider-new-2.html', data_new_rider)

            if request.POST['SelectFreePlate'] == "Vyber...":
                print("Není vybráno startovní číslo")
                messages.error(request, "Nevybral/a jsi startovní číslo. Jedná se o povinný údaj.")
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

            if ('CheckIs20' or 'CheckIs24') not in request.POST:
                print("Není vybrána kategorie")
                messages.error(request, "Nevyplnil/a jsi, zda budeš jezdit na 20-ti palcovém kole či na Cruiseru. Jedná se o povinný údaj.")
                data_new_rider = {'first_name': request.session['first_name'],
                                  'last_name': request.session['last_name'],
                                  'date_of_birth': request.session['date_of_birth'],
                                  'gender': request.session['gender'],
                                  'clubs': clubs, 'free_plates': free_plates, 'uci_id': request.session['uci_id'],
                                  }
                return render(request, 'rider/rider-new-2.html', data_new_rider)

            if request.POST['SelectClub'] == "Vyber...":
                print("Není vybrán klub")
                messages.error(request,  "Nevybral jsi svůj klub. Jedná se o povinný údaj.")
                data_new_rider = {'first_name': request.session['first_name'],
                                  'last_name': request.session['last_name'],
                                  'date_of_birth': request.session['date_of_birth'],
                                  'gender': request.session['gender'],
                                  'clubs': clubs, 'free_plates': free_plates, 'uci_id': request.session['uci_id'],
                                  }
                return render(request, 'rider/rider-new-2.html', data_new_rider)

            is_20 = 1 if 'CheckIs20' in request.POST else 0
            is_24 = 1 if 'CheckIs24' in request.POST else 0
            have_girls_bonus = 1 if 'CheckBonus' in request.POST else 0
            is_elite = 1 if 'CheckElite' in request.POST else 0
            new_rider = Rider.objects.create(
                first_name=request.session['first_name'],
                last_name=request.session['last_name'],
                date_of_birth=datetime.datetime.strptime(request.session['date_of_birth'], "%Y-%m-%d"),
                gender=request.session['gender'],
                uci_id=request.session['uci_id'],
                is_20=is_20,
                is_24=is_24,
                is_elite=is_elite,
                have_girl_bonus=have_girls_bonus,
                email=request.POST['InputEmail'],
                plate=request.POST['SelectFreePlate'],
                club=Club.objects.get(id=request.POST['SelectClub']),
                is_active=1,
                is_approwe=0,
                emergency_contact=request.POST['InputEmergencyContact'],
                emergency_phone=request.POST['InputEmergencyPhone'],
            )
            new_rider.save()
            new_rider.set_class_20()
            new_rider.set_class_24()

            # TODO: Dodělat odeslání e-mailového potvrzení

        return render(request, 'rider/rider-new-3.html')

    # rendering in GET method

    return render(request, 'rider/rider-new.html')
