import datetime
from rider.models import Rider
from event.models import Result, Entry, Event
from django.db.models import Q
import threading

def sort_20(self, classes):
    CLASS_ORDER20 = {
    'Boys 6', 'Boys 7', 'Boys 8', 'Boys 9', 'Boys 10', 'Boys 11', 'Boys 12', 'Boys 13', 'Boys 14', 'Boys 15', 'Boys 16', 'Men 17-24', 'Men 25-29', 'Men 30-34', 'Men 35 and over', 'Girls 7', 'Girls 8', 'Girls 9', 'Girls 10', 'Girls 11', 'Girls 12',
    'Girls 12', 'Girls 13', 'Girls 14', 'Girls 15', 'Girls 16', 'Women 17-24', 'Women 25 and over', 'Men Junior', 'Men Under 23', 'Men Elite', 'Women Junior'
    'Women Under 23', 'Women Elite'}
    pass


def sort_24(self, classes):
    CLASS_ORDER_24 = {'Boys 12 and under', 'Boys 13 and 14', 'Boys 15 and 16', 'Men 17-24', 'Men 25-39', 'Men 30-34', 'Men 35-39', 'Men 40-44', 'Men 45-49', 'Men 50 and over', 'Girls 12 and under', 'Girls 13-16', 'Women 17-29', 'Women 30-99', 'Women 40 and over'}
    pass


class SetRanking (threading.Thread):
    """ Class for setting ranking """

    def __init__(self):
        threading.Thread.__init__(self)
    
    def run(self):
        RankingCount.set_ranking_points()
        RankPositionCount().count_ranking_position()
        print("Ranking přepočítán")

class RankingCount:
    """ Class for rankings count"""
    CZECH_CUP = 10
    LIGA = 6

    def __init__(self, uci_id):
        self.uci_id = uci_id
        self.points_20 = 0
        self.points_24 = 0
        self.rider = None

    def resolve_category(self):
        self.rider = Rider.objects.select_related().get(uci_id=self.uci_id)

    def set_points(self, event_types, max_races, is_20):
        """ General method for setting points based on event type """
        results = (
            Result.objects.filter(event_type__in=event_types, is_20=is_20,
                                  date__gte=datetime.now() - timedelta(days=365),
                                  rider=self.uci_id)
            .order_by('-points', '-date')
        )

        # Reset previous markings
        results.update(marked_20=False) if is_20 else results.update(marked_24=False)

        # Get top races
        num_race = min(results.count(), max_races)
        selected_results = results[:num_race]

        # Update selected results
        if is_20:
            self.points_20 += sum(result.points for result in selected_results)
            results.filter(id__in=[r.id for r in selected_results]).update(marked_20=True)
        else:
            self.points_24 += sum(result.points for result in selected_results)
            results.filter(id__in=[r.id for r in selected_results]).update(marked_24=True)

    def count_points(self):
        self.resolve_category()
        if self.rider.is_20:
            self.set_points(["Mistrovství ČR jednotlivců"], 1, is_20=1)
            self.set_points(["Český pohár"], self.CZECH_CUP, is_20=1)
            self.set_points(["Česká liga", "Moravská liga", "Volný závod"], self.LIGA, is_20=1)

        if self.rider.is_24:
            self.set_points(["Mistrovství ČR jednotlivců"], 1, is_20=0)
            self.set_points(["Český pohár"], self.CZECH_CUP, is_20=0)
            self.set_points(["Česká liga", "Moravská liga", "Volný závod"], self.LIGA, is_20=0)

    @staticmethod
    def set_ranking_points():
        """ Methods for setting ranking points for all riders """
        for rider in Rider.objects.filter(is_active=True, is_approwe=True).iterator():
            ranking = RankingCount(rider.uci_id)
            ranking.count_points()
            Rider.objects.filter(uci_id=rider.uci_id).update(
                points_20=ranking.points_20,
                points_24=ranking.points_24
            )

class RankPositionCount:
    """ Class for counting ranking positions of riders"""

    def get_categories(self, is_20):
        """ Method for getting all real classes returned as list
        Arguments: is_20 = True - the 20" challenge, junior and elite classes
                   is_20 = False - the Cruiser classes
        """
        categories = []

        if is_20:
            riders = Rider.objects.filter(is_active=True, is_approwe=True, is_20=True).exclude(points_20=0)
            for rider in riders:
                if rider.class_20 not in categories:
                    categories.append(rider.class_20)
            del riders
        else:
            riders = Rider.objects.filter(is_active=True, is_approwe=True, is_24=True).exclude(points_24=0)
            for rider in riders:
                if rider.class_24 not in categories:
                    categories.append(rider.class_24)
            del riders

        categories.sort()
        clean_categories = []
        for category in categories:
            if category not in clean_categories:
                clean_categories.append(category)

        return clean_categories

    def get_riders_by_class(self, category: str, is_20: bool):

        """ Method for getting riders by class returned as queryset sorted by points
        Arguments:  category, is_20 = True - the 20" bike, is_20 = False - the Cruiser classes
        """
        if is_20:
            riders = Rider.objects.filter(is_active=True, is_approwe=True, is_20=True, class_20=category).order_by(
                '-points_20').exclude(points_20=0)
        else:
            riders = Rider.objects.filter(is_active=True, is_approwe=True, is_24=True, class_24=category).order_by(
                '-points_24').exclude(points_24=0)
        return riders

    def write_ranking(self, rider, is_20, ranking):

        if is_20:
            rider = Rider.objects.get(id=rider)
            rider.ranking_20 = ranking
            rider.save()
            del rider
        else:
            rider = Rider.objects.get(id=rider)
            rider.ranking_24 = ranking
            rider.save()
            del rider

    def mark_same_position(self):
        categories_20 = self.get_categories(is_20=True)
        categories_24 = self.get_categories(is_20=False)

        all_positions = []
        duplicates = []
        for category_20 in categories_20:
            riders = Rider.objects.filter(class_20=category_20, is_active=True, is_approwe=True, is_20=True).exclude(
                points_20=0)
            for rider in riders:
                if rider.ranking_20 not in all_positions:
                    all_positions.append(rider.ranking_20)
                else:
                    duplicates.append(rider.ranking_20)
            del riders

            if duplicates:
                for position in duplicates:
                    riders = Rider.objects.filter(ranking_20=position, is_20=True, is_active=True,
                                                  class_20=category_20, is_approwe=True)
                    new_end_position = int(position) + riders.count() - 1
                    text_ranking = f"{str(position)}. - {str(new_end_position)}"
                    for rider in riders:
                        rider.ranking_20 = text_ranking
                        rider.save()
                del riders
            duplicates = []
            all_positions = []

        for category_24 in categories_24:
            riders = Rider.objects.filter(class_24=category_24, is_active=True, is_approwe=True, is_24=True).exclude(
                points_24=0)
            for rider in riders:
                if rider.ranking_24 not in all_positions:
                    all_positions.append(rider.ranking_24)
                else:
                    duplicates.append(rider.ranking_24)
            del riders

            if duplicates:
                for position in duplicates:
                    riders = Rider.objects.filter(ranking_24=position, is_24=True, is_active=True,
                                                  class_24=category_24, is_approwe=True)
                    new_end_position = int(position) + riders.count() - 1
                    text_ranking = f"{str(position)} - {str(new_end_position)}"
                    for rider in riders:
                        rider.ranking_24 = text_ranking
                        rider.save()
                del riders
            duplicates = []
            all_positions = []

    def count_ranking_position(self):
        """ Method for counting ranking position for all riders. Without arguments """
        # RANKING POSITION FOR 20"
        categories_20 = self.get_categories(is_20=True)
        for category_20 in categories_20:
            riders_20 = self.get_riders_by_class(category=category_20, is_20=True)

            for i in range(0, riders_20.count()):
                #
                if i > 0:
                    if riders_20[i - 1].points_20 == riders_20[i].points_20:
                        same_point_rider = Rider.objects.filter(id=riders_20[i - 1].id)
                        ranking = same_point_rider[0].ranking_20
                        del same_point_rider
                    else:
                        ranking = i + 1
                else:
                    ranking = 1
                target = self.write_ranking(rider=riders_20[i].id, is_20=True, ranking=ranking)

        # RANKING POSITION FOR 24" (CRUISER)
        categories_24 = self.get_categories(is_20=False)
        for category_24 in categories_24:
            riders_24 = self.get_riders_by_class(category=category_24, is_20=False)

            for i in range(0, riders_24.count()):

                if i > 0:
                    if riders_24[i - 1].points_24 == riders_24[i].points_24:
                        same_point_rider = Rider.objects.filter(id=riders_24[i - 1].id)
                        ranking = same_point_rider[0].ranking_24
                        del same_point_rider
                    else:
                        ranking = i + 1
                else:
                    ranking = 1
                target = self.write_ranking(rider=riders_24[i].id, is_20=False, ranking=ranking)

        self.mark_same_position()
        print("Ranking všech jezdců přepočítán")


class Categories:
    """ Return set of classes """

    @staticmethod
    def get_categories(event=0):
        # events 0 is categories for ranking view
        if event == 0:

            riders = Rider.objects.filter(is_active=True, is_approwe=True)

            # PREPARE CLASSES FROM REAL RIDER CLASSES
            categories20 = []
            categories24 = []
            for rider in riders:
                try:
                    if rider.is_20:
                        categories20.append(rider.class_20)
                    if rider.is_24:
                        categories24.append(f"Cruiser {rider.class_24}")
                except:
                    pass
        # categories for entries
        else:
            current_event = Event.objects.get(pk=event)
            entries = Entry.objects.filter(event=current_event, payment_complete=True)
            print(entries)

            # PREPARE CLASSES FROM REAL RIDER CLASSES
            categories20 = []
            categories24 = []
            for entry in entries:
                try:
                    if entry.is_20:
                        categories20.append(entry.class_20)
                    if entry.is_24:
                        categories24.append(entry.class_24)
                except:
                    pass

        # REMOVE DUPLICATES
        clean_categories20 = []
        for category in categories20:
            if category not in clean_categories20:
                clean_categories20.append(category)
        # TODO: Předělat řazení kategorií 20
        clean_categories20.sort()

        clean_categories24 = []
        for category in categories24:
            if category not in clean_categories24:
                clean_categories24.append(category)
        # TODO: Předělat řazení kategorií 24
        clean_categories24.sort()
        return clean_categories20 + clean_categories24
