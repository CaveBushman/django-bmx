from rest_framework import serializers
from event.models import Event, Entry
from event.models_events import EventPhoto
from event.services.registration_status import can_register, can_unregister


class OrganizerCoordinatesMixin:
    organizer_lat = serializers.SerializerMethodField()
    organizer_lon = serializers.SerializerMethodField()

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
    organizer_name = serializers.CharField(source="organizer.team_name", read_only=True, default=None)
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
            "organizer", "organizer_name", "organizer_lat", "organizer_lon",
            "eshop_pickup_enabled", "photos",
        ]

    def get_registration_open(self, obj) -> bool:
        return can_register(obj)

    def get_unregistration_open(self, obj) -> bool:
        return can_unregister(obj)


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
