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
from rider.rider import get_api_token

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


def get_rider_data(uci_id):
    print(f"\U0001f50d Načítám data pro UCI ID: {uci_id}")

    token = get_api_token()
    if not token:
        print("❌ Nepodařilo se získat access token.")
        return None, "Nepodařilo se získat token k API ČSC."

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    url = f"https://portal.api.czechcyclingfederation.com/api/services/licenseinfo?uciId={uci_id}"

    print(f"🌐 Odesílám požadavek na: {url}")
    print(f"➡️ Hlavičky: {headers}")

    try:
        response = requests.get(url, headers=headers, verify=True)
        print(f"📡 Status kód: {response.status_code}")
        print(f"📥 Tělo odpovědi: {response.text}")

        if response.status_code == 404 or "Http_NotFound" in response.text:
            print("❌ Licence nebyla nalezena v databázi ČSC.")
            return None, f"Licence UCI ID: {uci_id} nebyla nalezena."

        if not response.ok:
            print(f"⚠️ Neočekávaná odpověď: {response.status_code}")
            return None, f"Nastala chyba: {response.status_code}"

        data = response.json()
        print(f"✅ Úspěšně načteno: {data}")
        return data, None

    except Exception as e:
        print(f"❌ Výjimka při volání API ČSC: {e}")
        return None, f"Chyba při komunikaci s API ČSC: {e}"



def rider_new_view(request):
    if request.method == "POST":
        clubs = Club.objects.filter(is_active=True)
        used_plates = list(Rider.objects.filter(is_active=True).values_list('plate', flat=True))
        free_plates = [plate for plate in range(10, 1000) if plate not in used_plates]

        # FÁZE 1: Načtení dat z UCI API pomocí UCI ID
        if 'num11' in request.POST and 'first-name' not in request.POST:
            uci_id = ''.join([request.POST.get(f'num{i}', '') for i in range(1, 12)])
            data_json, error_msg = get_rider_data(uci_id)

            if error_msg or not data_json:
                return render(request, 'rider/rider-new-error.html', {'message': error_msg})

            first_name = data_json.get('firstName')
            last_name = data_json.get('lastName')
            birth = data_json.get('birth', '')[:10]
            gender_code = data_json.get('sex', {}).get('code', 'M')
            gender = "Žena" if gender_code == "F" else "Muž"

            if Rider.objects.filter(uci_id=uci_id).exists():
                existing = Rider.objects.get(uci_id=uci_id)
                msg = f"Jezdec/jezdkyně {existing.first_name} {existing.last_name}, UCI ID {uci_id}, již má přidělené číslo."
                return render(request, 'rider/rider-new-error.html', {'message': msg})

            # Uložíme do session pro další krok
            request.session['first_name'] = first_name
            request.session['last_name'] = last_name.capitalize() if last_name else ""
            request.session['date_of_birth'] = birth
            request.session['gender'] = gender
            request.session['uci_id'] = uci_id

            return render(request, 'rider/rider-new-2.html', {
                'first_name': first_name,
                'last_name': last_name,
                'date_of_birth': birth,
                'gender': gender,
                'clubs': clubs,
                'free_plates': free_plates,
                'uci_id': uci_id,
            })

        # FÁZE 2: Uložení formuláře do databáze
        else:
            required_fields = ['plate', 'club', 'emergency-contact', 'emergency-phone']
            for field in required_fields:
                if not request.POST.get(field) or request.POST.get(field) in ["", "Vyber..."]:
                    messages.error(request, f"Pole {field} je povinné.")
                    return render(request, 'rider/rider-new-2.html', {
                        'first_name': request.session['first_name'],
                        'last_name': request.session['last_name'],
                        'date_of_birth': request.session['date_of_birth'],
                        'gender': request.session['gender'],
                        'clubs': clubs,
                        'free_plates': free_plates,
                        'uci_id': request.session['uci_id'],
                    })

            if 'is20' not in request.POST and 'is24' not in request.POST:
                messages.error(request, 'Musíš vybrat, zda budeš jezdit 20" nebo 24" kolo.')
                return render(request, 'rider/rider-new-2.html', {
                    'first_name': request.session['first_name'],
                    'last_name': request.session['last_name'],
                    'date_of_birth': request.session['date_of_birth'],
                    'gender': request.session['gender'],
                    'clubs': clubs,
                    'free_plates': free_plates,
                    'uci_id': request.session['uci_id'],
                })

            # Vytvoření záznamu jezdce
            new_rider = Rider.objects.create(
                first_name=request.session['first_name'],
                last_name=request.session['last_name'],
                date_of_birth=datetime.datetime.strptime(request.session['date_of_birth'], "%Y-%m-%d"),
                gender=request.session['gender'],
                uci_id=request.session['uci_id'],
                is_20='is20' in request.POST,
                is_24='is24' in request.POST,
                is_elite='elite' in request.POST,
                have_girl_bonus='bonus' in request.POST,
                plate=request.POST['plate'],
                club=Club.objects.get(id=request.POST['club']),
                is_active=True,
                is_approwe=False,
                emergency_contact=request.POST['emergency-contact'],
                emergency_phone=request.POST['emergency-phone'],
            )

            return render(request, 'rider/rider-new-3.html')

    # GET metoda – první krok
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
