from rest_framework import serializers
from .models import Club


class ClubSerializer(serializers.ModelSerializer):
    class Meta:
        model = Club
        fields = '__all__'


class ClubPublicSerializer(serializers.ModelSerializer):
    lat = serializers.SerializerMethodField()
    lon = serializers.SerializerMethodField()

    class Meta:
        model = Club
        fields = [
            'id', 'team_name', 'club_name', 'city', 'region',
            'web', 'facebook', 'instagram',
            'contact_person', 'contact_phone', 'contact_email',
            'have_track', 'lat', 'lon', 'opening_hours',
        ]

    def get_lat(self, obj):
        v = obj.lon  # DB field 'lon' stores latitude
        return v if v not in (None, 0, 0.0) else None

    def get_lon(self, obj):
        v = obj.lng  # DB field 'lng' stores longitude
        return v if v not in (None, 0, 0.0) else None
