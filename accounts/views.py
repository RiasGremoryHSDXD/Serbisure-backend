from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import UserRegistrationSerializer

class UserRegistrationView(APIView):

    # This tell Django: "You do not need to logged in to access this windows."
    # (Because if you had to be logged in to register...nobody could ever register!)

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        # 1. Give the incoming JSON data to our bouncer (the Serializer)
        
        serializer = UserRegistrationSerializer(data=request.data)

        # 2. The bouncer checks if the data matches the blueprint perfeclty

        if serializer.is_valid():

            # 3. If valid, encrpyt the password and save to the database

            serializer.save()

            return Response(
                {
                    "message": "Account created successfully!"
                },
                status=status.HTTP_201_CREATED
            )
        
        # 5. If invalid (e.g., missing an email), send the exact error back

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        ) 