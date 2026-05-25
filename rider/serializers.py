from rest_framework import serializers
from .models import Rider, ForeignRider

class RiderSerializer(serializers.ModelSerializer):
    club_name = serializers.SerializerMethodField()

    def get_club_name(self, obj):
        return obj.club.name if obj.club_id and obj.club else None

    class Meta:
        model = Rider
        exclude = ['email', 'emergency_contact', 'emergency_phone']
        read_only_fields = ['id']


class ForeignRiderSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = ForeignRider
        fields = '__all__'
        read_only_fields = ['id']
