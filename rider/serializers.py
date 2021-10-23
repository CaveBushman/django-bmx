from rest_framework import serializers
from .models import Rider

class RiderSerializer(serializers.ModelSerializer):

    class Meta:
        model = Rider
        exclude = ['email', 'emergency_contact', 'emergency_phone']
        read_only_fields = ['id']
