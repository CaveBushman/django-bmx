from rest_framework import serializers
from .models import Rider, ForeignRider

class RiderSerializer(serializers.ModelSerializer):

    class Meta:
        model = Rider
        exclude = ['email', 'emergency_contact', 'emergency_phone']
        read_only_fields = ['id']


class ForeignRiderSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = ForeignRider
        fields = '__all__'
        read_only_fields = ['id']
