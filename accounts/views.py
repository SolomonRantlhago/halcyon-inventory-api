from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.serializers import RegisterSerializer, UserSerializer


@extend_schema(tags=["auth"], auth=[])
class RegisterView(generics.CreateAPIView):
    """Create a standard-role account."""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["auth"], responses=UserSerializer)
class MeView(APIView):
    """Return the authenticated user's profile and role."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)
