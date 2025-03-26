from .models import Result
import re
import unidecode


class GetResult:
    """ Class for writing results to result table in database"""

    def __init__(self, date, race_id, name, ranking_code, uci_id, place, category, first_name, last_name, club, organizer, event_type):
        self.date = date
        self.race_id = race_id
        self.organizer = organizer
        self.name = name
        self.ranking_code = ranking_code
        self.uci_id = uci_id
        self.first_name = first_name
        self.last_name = last_name
        self.club = club
        self.place = place
        self.category = category
        self.point = 0
        self.is_20 = 1
        self.is_beginner = 0
        self.type = event_type

    def get_ranking_points(self):
        """ Function for give points depend by event place and ranking code """

        if ("beginners" in self.category) or ("Beginners" in self.category):
            return 0

        # RANKING CODE 1 - Mistrovství ČR jednotlivců
        if self.ranking_code == 1:
            if self.place == "1":
                return 350
            elif self.place == "2":
                return 300
            elif self.place == "3":
                return 250
            elif self.place == "4":
                return 200
            elif self.place == "5":
                return 190
            elif self.place == "6":
                return 180
            elif self.place == "7":
                return 170
            elif self.place == "8":
                return 160
            elif self.place == "9" or self.place == "10":
                return 125
            elif self.place == "11" or self.place == "12":
                return 120
            elif self.place == "13" or self.place == "14":
                return 115
            elif self.place == "15" or self.place == "16":
                return 110
            elif self.place == "17" or self.place == "18" or self.place == "19" or self.place == "20":
                return 90
            elif self.place == "21" or self.place == "22" or self.place == "23" or self.place == "24":
                return 80
            elif self.place == "25" or self.place == "26" or self.place == "27" or self.place == "28":
                return 70
            elif self.place == "29" or self.place == "30" or self.place == "31" or self.place == "32":
                return 60
            else:
                return 0

        # RANKING CODE 2 - Český pohár
        elif self.ranking_code == 2:
            if self.place == "1":
                return 150
            elif self.place == "2":
                return 130
            elif self.place == "3":
                return 115
            elif self.place == "4":
                return 100
            elif self.place == "5":
                return 90
            elif self.place == "6":
                return 80
            elif self.place == "7":
                return 75
            elif self.place == "8":
                return 70
            elif self.place == "9" or self.place == "10":
                return 65
            elif self.place == "11" or self.place == "12":
                return 60
            elif self.place == "13" or self.place == "14":
                return 55
            elif self.place == "15" or self.place == "16":
                return 50
            elif self.place == "17" or self.place == "18" or self.place == "19" or self.place == "20":
                return 40
            elif self.place == "21" or self.place == "22" or self.place == "23" or self.place == "24":
                return 35
            elif self.place == "25" or self.place == "26" or self.place == "27" or self.place == "28":
                return 30
            elif self.place == "29" or self.place == "30" or self.place == "31" or self.place == "32":
                return 25
            else:
                return 0

        # RANKING CODE 3 - Česká liga, Moravská liga, Volný závod
        elif self.ranking_code == 3:
            if self.place == "1":
                return 90
            elif self.place == "2":
                return 70
            elif self.place == "3":
                return 60
            elif self.place == "4":
                return 50
            elif self.place == "5":
                return 40
            elif self.place == "6":
                return 30
            elif self.place == "7":
                return 25
            elif self.place == "8":
                return 20
            elif self.place == "9" or self.place == "10":
                return 15
            elif self.place == "11" or self.place == "12":
                return 10
            elif self.place == "13" or self.place == "14":
                return 8
            elif self.place == "15" or self.place == "16":
                return 6
            else:
                return 0

        # RANKING CODE 4 - Volný závod - nyní nepoužívat
        elif self.ranking_code == 4:
            if self.place == "1":
                return 60
            elif self.place == "2":
                return 45
            elif self.place == "3":
                return 40
            elif self.place == "4":
                return 35
            elif self.place == "5":
                return 30
            elif self.place == "6":
                return 25
            elif self.place == "7":
                return 20
            elif self.place == "8":
                return 15
            elif self.place == "9" or self.place == "10":
                return 8
            elif self.place == "11" or self.place == "12":
                return 6
            elif self.place == "13" or self.place == "14":
                return 4
            elif self.place == "15" or self.place == "16":
                return 2
            else:
                return 0
        # Race without ranking points
        else:
            return 0

    def cruiser_resolve(self):
        """Určí, zda je kategorie Cruiser (tedy 24") nebo ne (tedy 20")"""
        if not self.category:
            return 1  # výchozí – považuj za 20"

        category = unidecode.unidecode(self.category).lower()

        if re.search(r'\b(cruiser|cruisers|24)\b', category):
            return 0
        return 1  # 20"

    def is_beginner_category(self):
        """
        Zjistí, jestli kategorie je 'Příchozí' nebo 'Beginners' – různé varianty, nezávisle na velikosti písmen a diakritice.
        """
        if not self.category:
            return 0

        category = unidecode.unidecode(self.category).lower()

        if re.search(r'\b(prichozi|prichozí|beginners?|beginner)\b', category):
            return 1
        return 0

    def write_result(self):

        self.point = self.get_ranking_points()
        self.is_20 = self.cruiser_resolve()
        self.is_beginner  = self.is_beginner_category()

        if self.is_beginner:
            self.is_20=False

        result = Result.objects.create()
        try:
            result.rider = int(self.uci_id)
        except:
            result.rider = 0

        result.first_name = self.first_name
        result.last_name = self.last_name
        result.club = self.club
        result.category = self.category

        result.event_id = self.race_id
        result.date = self.date
        result.name = self.name
        result.organizer = self.organizer
        result.event_type = self.type

        result.place = self.place
        if self.is_beginner:
            result.points = 0
        else:
            result.points = self.point

        result.is_20 = self.is_20
        result.is_beginner = self.is_beginner

        result.save()

    @staticmethod
    def ranking_code_resolve(type):
        if type == "Mistrovství ČR jednotlivců":
            return 1
        elif type == "Český pohár":
            return 2
        elif type == "Česká liga" or type == "Moravská liga":
            return 3
        elif type == "Volný závod":
            return 3 # Pokud bude Česká liga, změnit na 4
        else:
            return 0
