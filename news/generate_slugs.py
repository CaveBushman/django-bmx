from django.core.management.base import BaseCommand
from news.models import News

class Command(BaseCommand):
    help = 'Vygeneruje slugy pro články, které je zatím nemají (pro zpětnou kompatibilitu).'

    def handle(self, *args, **options):
        # Najdeme články, které nemají slug nebo ho mají prázdný
        news_list = News.objects.filter(slug__isnull=True) | News.objects.filter(slug='')
        count = news_list.count()
        
        self.stdout.write(f'Nalezeno {count} článků bez slugu. Začínám generování...')

        for article in news_list:
            # Metoda save() v modelu News má nyní logiku pro automatické generování slugu,
            # pokud chybí. Stačí tedy zavolat save().
            try:
                article.save()
                self.stdout.write(f'Slug pro "{article.title}" nastaven na: {article.slug}')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Chyba u článku ID {article.id}: {e}'))

        self.stdout.write(self.style.SUCCESS(f'Hotovo. Aktualizováno {count} článků.'))