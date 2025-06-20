from django.db.models import Sum
from django.apps import apps
from concurrent.futures import ThreadPoolExecutor

def calculate_user_balance(user_id):
    """Spočítá zůstatek uživatele jako rozdíl mezi kredity a debety."""
    from .models import CreditTransaction, DebetTransaction  # Import uvnitř funkce

    # Sečteme všechny kredity pro daného uživatele
    credit = CreditTransaction.objects.filter(user_id=user_id, payment_complete=True).aggregate(total_credit=Sum('amount'))['total_credit'] or 0

    # Sečteme všechny debety pro daného uživatele
    debit = DebetTransaction.objects.filter(user_id=user_id, payment_valid=True).aggregate(total_debit=Sum('amount'))['total_debit'] or 0

    return credit - debit  # Vrací čistý zůstatek uživatele

def recalculate_all_balances():
    """Hromadně přepočítá zůstatky pro všechny aktivní uživatele."""
    Account = apps.get_model('accounts', 'Account')  # Dynamický import modelu
    
    active_users = Account.objects.filter(is_active=True)  # Aktivní uživatelé

    def process_user(user):
        new_balance = calculate_user_balance(user.id)  # Spočítáme nový kredit
        
        if user.credit != new_balance:  # Aktualizujeme pouze pokud je rozdíl
            old_balance = user.credit
            user.credit = new_balance
            user.save(update_fields=['credit'])  # Uložíme pouze změněné pole
            
            print(f"⚠️ Změna kreditu pro {user.id} ({user.username}): {old_balance} → {new_balance} Kč")  

    with ThreadPoolExecutor(max_workers=5) as executor:  # Paralelní výpočet
        executor.map(process_user, active_users)