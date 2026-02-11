from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    def get(self, request):
        return Response({'status': 'ok'})


class MetaView(APIView):
    def get(self, request):
        return Response({'app': 'JSLL Decision Intelligence', 'version': '0.1.0'})