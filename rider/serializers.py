from rest_framework import serializers
from .models import Rider, ForeignRider

class RiderSerializer(serializers.ModelSerializer):
    club_name = serializers.SerializerMethodField()

    def get_club_name(self, obj):
        return obj.club.team_name if obj.club_id and obj.club else None

    class Meta:
        model = Rider
        fields = [
            'id', 'uci_id', 'first_name', 'middle_name', 'last_name',
            'nationality', 'gender', 'photo', 'club', 'club_name',
            'is_20', 'is_24', 'is_elite', 'is_active', 'is_approved',
            'class_20', 'class_24', 'plate_text',
            'transponder_20', 'transponder_24',
            'points_20', 'points_24', 'ranking_20', 'ranking_24',
        ]
        read_only_fields = ['id']


class ForeignRiderSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = ForeignRider
        fields = '__all__'
        read_only_fields = ['id']
