from django.contrib.auth import login, logout, authenticate
from django.shortcuts import render, redirect
from .models import Account
from django.contrib import messages


def sign_up(request):
    if request.method == 'POST':
        print(request.POST)
        first_name = request.POST['firstname']
        last_name = request.POST['lastname']
        username = request.POST['username']
        email = request.POST['username']
        password = request.POST['password']
        password2 = request.POST['password2']
        if password == password2:
            user = Account.objects.create_user(first_name, last_name, username, email, password)
            user.is_active = True
            user.save()
            login(request, user)
            return redirect('news:home')
        else:
            # TODO: Dodělat chybové hlášení
            messages.success(request, "Heslo není shodné s heslem pro kontrolu. Zadejte registrační údaje znovu")
            return render(request, 'accounts/signup.html')
            pass
        return redirect('news:home')
    else:
        data = {}
        return render(request, 'accounts/signup.html', data)


def sign_in(request):
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        print(user)
        if user is not None:
            login(request, user)
            return redirect('news:home')
    return render(request, 'accounts/signin.html')


def sign_out(request):
    logout(request)
    return redirect('news:home')
