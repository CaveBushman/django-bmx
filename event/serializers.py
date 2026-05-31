from rest_framework import serializers
from event.models import Event, Entry, Result
from event.models_events import EventPhoto
from event.services.registration_status import can_register, can_unregister


class OrganizerCoordinatesMixin(serializers.Serializer):
    organizer_lat = serializers.SerializerMethodField()
    organizer_lon = serializers.SerializerMethodField()
    organizer_name = serializers.SerializerMethodField()
    organizer_city = serializers.SerializerMethodField()

    def get_organizer_lat(self, obj):
        if not obj.organizer_id or not obj.organizer:
            return None
        value = obj.organizer.lon
        return value if value not in (None, 0) else None

    def get_organizer_lon(self, obj):
        if not obj.organizer_id or not obj.organizer:
            return None
        value = obj.organizer.lng
        return value if value not in (None, 0) else None

    def get_organizer_name(self, obj):
        if not obj.organizer_id or not obj.organizer:
            return None
        return obj.organizer.team_name or None

    def get_organizer_city(self, obj):
        if not obj.organizer_id or not obj.organizer:
            return None
        return obj.organizer.city or None


class EventPhotoSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = EventPhoto
        fields = ["id", "photo_url", "caption", "order"]

    def get_photo_url(self, obj) -> str:
        request = self.context.get("request")
        try:
            url = obj.photo.url
            return request.build_absolute_uri(url) if request else url
        except (ValueError, OSError):
            return ""


class EventSerializer(OrganizerCoordinatesMixin, serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = '__all__'


class EventPublicSerializer(OrganizerCoordinatesMixin, serializers.ModelSerializer):
    registration_open = serializers.SerializerMethodField()
    unregistration_open = serializers.SerializerMethodField()
    photos = EventPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = Event
        fields = [
            "id", "name", "date", "double_race", "type_for_ranking", "is_uci_race",
            "system", "director", "youtube_link", "canceled",
            "reg_open", "reg_open_from", "reg_open_to", "reg_cancel_to",
            "registration_open", "unregistration_open",
            "organizer", "organizer_name", "organizer_city", "organizer_lat", "organizer_lon",
            "eshop_pickup_enabled", "eshop_pickup_location", "eshop_pickup_time", "eshop_pickup_note",
            "proposition", "series", "bem_riders_list", "full_results", "html_results",
            "fast_riders", "xls_results", "uec_link", "uci_event_code",
            "photos",
        ]

    def get_registration_open(self, obj) -> bool:
        return can_register(obj)

    def get_unregistration_open(self, obj) -> bool:
        return can_unregister(obj)


class ResultPublicSerializer(serializers.ModelSerializer):
    event_name = serializers.SerializerMethodField()
    event_date = serializers.SerializerMethodField()
    type_for_ranking = serializers.SerializerMethodField()
    organizer_id = serializers.SerializerMethodField()
    organizer_name = serializers.SerializerMethodField()
    rider_uci_id = serializers.IntegerField(source="rider_id", read_only=True)
    wheel = serializers.SerializerMethodField()
    is_24 = serializers.SerializerMethodField()

    class Meta:
        model = Result
        fields = [
            "id",
            "event",
            "event_name",
            "event_date",
            "event_type",
            "type_for_ranking",
            "organizer_id",
            "organizer_name",
            "rider_uci_id",
            "first_name",
            "last_name",
            "club",
            "country",
            "category",
            "place",
            "points",
            "wheel",
            "is_20",
            "is_24",
            "is_beginner",
            "marked_20",
            "marked_24",
        ]

    def get_event_name(self, obj):
        if obj.event_id and obj.event:
            return obj.event.name
        return obj.organizer or ""

    def get_event_date(self, obj):
        date_value = obj.event.date if obj.event_id and obj.event else obj.date
        return date_value.isoformat() if date_value else None

    def get_type_for_ranking(self, obj):
        if obj.event_id and obj.event:
            return obj.event.type_for_ranking or ""
        return obj.event_type or ""

    def get_organizer_id(self, obj):
        if obj.event_id and obj.event:
            return obj.event.organizer_id
        return None

    def get_organizer_name(self, obj):
        if obj.event_id and obj.event and obj.event.organizer_id and obj.event.organizer:
            return obj.event.organizer.team_name or ""
        return obj.organizer or ""

    def get_wheel(self, obj):
        if obj.is_beginner:
            return "beginner"
        return "20" if obj.is_20 else "24"

    def get_is_24(self, obj):
        return not bool(obj.is_20) and not bool(obj.is_beginner)


class EntrySerializer(serializers.ModelSerializer):

    class Meta:
        model = Entry
        fields = '__all__'


class EntryDetailSerializer(serializers.ModelSerializer):
    event_name = serializers.CharField(source="event.name", read_only=True)
    event_date = serializers.DateField(source="event.date", read_only=True)
    rider_first_name = serializers.CharField(source="rider.first_name", read_only=True)
    rider_last_name = serializers.CharField(source="rider.last_name", read_only=True)
    rider_uci_id = serializers.IntegerField(source="rider.uci_id", read_only=True)
    total_fee = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()

    class Meta:
        model = Entry
        fields = [
            "id", "event", "event_name", "event_date",
            "rider", "rider_uci_id", "rider_first_name", "rider_last_name",
            "is_beginner", "is_20", "is_24",
            "class_beginner", "class_20", "class_24",
            "fee_beginner", "fee_20", "fee_24", "total_fee",
            "payment_complete", "checkout",
            "transaction_date", "can_cancel",
        ]

    def get_total_fee(self, obj) -> int:
        return (obj.fee_beginner or 0) + (obj.fee_20 or 0) + (obj.fee_24 or 0)

    def get_can_cancel(self, obj) -> bool:
        if not obj.payment_complete or obj.checkout:
            return False
        if not obj.event:
            return False
        return can_unregister(obj.event)
