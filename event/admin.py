from django.contrib import admin
from .models import Event, Result, EntryClasses, Entry, EntryForeign, SeasonSettings, CreditTransaction, DebetTransaction, StripeFee

# Register your models here.

class ResultAdmin(admin.ModelAdmin):
    pass

class EventAdmin(admin.ModelAdmin):
    list_display = ('id','name', 'date', 'organizer', 'type_for_ranking', 'classes_and_fees_like','xls_results',)
    list_display_links = ('name',)
    search_fields = ('name', 'organizer',)
    list_filter = ('type_for_ranking',)


class EntryClassesAdmin(admin.ModelAdmin):
    fieldsets = (
        ('Název závodu', {
            "fields": ('event_name',),
        }),

        ('Kategorie příchozí', {
            "fields": (('beginners_1', 'beginners_2', 'beginners_3', 'beginners_4')),
            'description': "Zde vyplň katerogie příchozích, které se pojedou v závodě"
        }),

        ('Kategorie muži', {
            "fields": (('boys_6', 'boys_7'), ('boys_8', 'boys_9'), ('boys_10', 'boys_11'),
            ('boys_12', 'boys_13'), ('boys_14','boys_15'),('boys_16', 'men_17_24'), ('men_25_29','men_30_34'),
            ('men_35_over', 'men_junior'), ('men_u23', 'men_elite')
        ),
        'description': "Zde vyplň katerogie mužů na 20-ti palcových kolech, které se pojedou v závodě"
        }),

        ('Kategorie ženy', {
            "fields": (('girls_7', 'girls_8'), ('girls_9', 'girls_10'), ('girls_11', 'girls_12'),
          ('girls_13', 'girls_14'), ('girls_15','girls_16'),('women_17_24', 'women_25_over'),('women_junior', 'women_u23'),
          ('women_elite')
        ),
        'description': "Zde vyplň katerogie žen na 20-ti palcových kolech, které se pojedou v závodě"
        }),

        ('Kategorie Cruiser', {
            'fields': (('cr_boys_12_and_under', 'cr_boys_13_14'), ('cr_boys_15_16', 'cr_men_17_24'),
            ('cr_men_25_29', 'cr_men_30_34'), ('cr_men_35_39', 'cr_men_40_44'), ('cr_men_45_49', 'cr_men_50_and_over'),
            ('cr_girls_12_and_under', 'cr_girls_13_16'), ('cr_women_17_29', 'cr_women_30_39'), 'cr_women_40_and_over',
            ),
        'description': "Zde vyplň katerogie na 24-ti palcových kolech (cruiserech), které se pojedou v závodě "
        }),

        ('Startovné Příchozí', {
            "fields": ('beginners_1_fee', 'beginners_2_fee', 'beginners_3_fee', 'beginners_4_fee'),
        }),

        ('Startovné muži', {   
            "fields": (('boys_6_fee', 'boys_7_fee','boys_8_fee', 'boys_9_fee'), ('boys_10_fee', 'boys_11_fee', 'boys_12_fee', 'boys_13_fee'), ('boys_14_fee','boys_15_fee','boys_16_fee', 'men_17_24_fee'), ('men_25_29_fee','men_30_34_fee',
            'men_35_over_fee', 'men_junior_fee'), ('men_u23_fee', 'men_elite_fee')),
        }),
        ('Startovné ženy', {
            'fields': ( ('girls_7_fee', 'girls_8_fee', 'girls_9_fee', 'girls_10_fee'),('girls_11_fee', 'girls_12_fee',
          'girls_13_fee', 'girls_14_fee'),('girls_15_fee','girls_16_fee','women_17_24_fee', 'women_25_over_fee'),('women_junior_fee', 'women_u23_fee',
          'women_elite_fee'),
            )
        }),
        ('Startovné Cruiser', {
            'fields': (('cr_boys_12_and_under_fee', 'cr_boys_13_14_fee','cr_boys_15_16_fee', 'cr_men_17_24_fee'),
            ('cr_men_25_29_fee', 'cr_men_30_34_fee','cr_men_35_39_fee', 'cr_men_40_44_fee'), ('cr_men_45_49_fee','cr_men_50_and_over_fee'),
            ('cr_girls_12_and_under_fee', 'cr_girls_13_16_fee', 'cr_women_17_29_fee', 'cr_women_30_39_fee'), 'cr_women_40_and_over_fee',
            )
        }),
        )
    

class EntryAdmin(admin.ModelAdmin):
    list_display =  ('rider', 'event', 'transaction_date', 'payment_complete','user','checkout',)
    list_display_links = ('rider',)
    search_fields = ('rider__last_name', 'event__name', 'user__last_name',)
    list_filter = ('payment_complete','event',)
    list_editable = ('checkout',)

class CreditTransactionAdmin(admin.ModelAdmin):
    list_display=('user', 'amount', 'payment_intent', 'payment_complete', 'transaction_date',)
    list_display_links = ('user',)
    search_fields = ('user__last_name', 'transaction_date', 'payment_intent',)

class DebetTransactionAdmin(admin.ModelAdmin):
    list_display=('user', 'entry', 'amount', 'transaction_date',)
    list_display_links = ('user',)
    search_fields = ('user__last_name', 'transaction_date', 'entry',)

class StripeFeeAdmin(admin.ModelAdmin):
    list_display=('date', 'fee',)
    list_display_links = ('date',)

admin.site.register(Event, EventAdmin)
admin.site.register(Result)
admin.site.register(EntryClasses, EntryClassesAdmin)
admin.site.register(Entry, EntryAdmin)
admin.site.register(EntryForeign)
admin.site.register(SeasonSettings)
admin.site.register(CreditTransaction, CreditTransactionAdmin)
admin.site.register(DebetTransaction, DebetTransactionAdmin)
admin.site.register(StripeFee, StripeFeeAdmin)

