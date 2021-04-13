from rest_framework import serializers
from rider.models import Rider

class RiderSerializer(serializers.ModelSerializer):

    class Meta:
        model = Rider
        fields = ('id', 'uci_id', 'first_name', 'last_name', )