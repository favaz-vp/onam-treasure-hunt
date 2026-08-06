from rest_framework import serializers
from .models import Node


class NodeSerializer(serializers.ModelSerializer):
    clue = serializers.SerializerMethodField()
    
    class Meta:
        model = Node
        fields = ['id', 'data', 'clue', 'effects', 'score', 'bonus', 'created_at']

    def get_clue(self, obj):
        return ("_ " * len(obj.answer))[:-1]
