from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import HttpResponse
from rest_framework import status
import os 
import json
import large_image_source_tiff
import pyvips
from django.conf import settings

class Viewers(APIView):
    def getTile(self, wsi, z, x, y):
        imagePath = os.path.join(settings.GLOBAL_SETTINGS['DATASET'], wsi)
        source = large_image_source_tiff.open(imagePath, jpegQuality=100, edge=True)
        tileData = source.getTile(x, y, z)
        return HttpResponse(tileData, content_type='image/jpeg')

    def getInfo(self, wsi):
        imagePath = os.path.join(settings.GLOBAL_SETTINGS['DATASET'], wsi)
        source = large_image_source_tiff.open(imagePath)
        tileMetadata = source.getMetadata()
        return HttpResponse(json.dumps(tileMetadata))