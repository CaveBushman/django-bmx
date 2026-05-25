from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from django.contrib.auth import authenticate


class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '')
        if not username or not password:
            return Response(
                {'detail': 'Vyplňte uživatelské jméno a heslo.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response(
                {'detail': 'Neplatné přihlašovací údaje.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not user.is_active:
            return Response(
                {'detail': 'Účet není aktivní.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': _user_data(user),
        })


class LogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            token = RefreshToken(request.data.get('refresh', ''))
            token.blacklist()
        except Exception:
            pass
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(_user_data(request.user))

    def patch(self, request):
        user = request.user
        for field in ('first_name', 'last_name', 'phone_number'):
            if field in request.data:
                setattr(user, field, request.data[field])
        user.save(update_fields=['first_name', 'last_name', 'phone_number'])
        return Response(_user_data(user))


def _user_data(user) -> dict:
    return {
        'id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
        'is_admin': getattr(user, 'is_admin', False),
        'is_staff': user.is_staff,
        'is_rider': getattr(user, 'is_rider', False),
        'is_club_manager': getattr(user, 'is_club_manager', False),
        'is_commissar': getattr(user, 'is_commissar', False),
        'is_trainer': getattr(user, 'is_trainer', False),
        'credit': getattr(user, 'credit', 0),
    }
