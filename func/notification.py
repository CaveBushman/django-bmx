from rider.models import Rider


def update_plate_notify(request):
    plates = Rider.objects.filter(is_approved=False)
    if plates:
        request.session['plate'] = True
    else:
        request.session['plate'] = False
