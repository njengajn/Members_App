from rest_framework import serializers
from .models import Member, Dependant, Claim, PaymentRequest, Payment, ClaimRecord
from django.contrib.auth.models import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "surname"]

class MemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    class Meta:
        model = Member
        fields = "__all__"

class DependantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dependant
        fields = "__all__"

class ClaimSerializer(serializers.ModelSerializer):
    class Meta:
        model = Claim
        fields = "__all__"

class PaymentRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentRequest
        fields = "__all__"

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = "__all__"

class ClaimRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClaimRecord
        fields = "__all__"
