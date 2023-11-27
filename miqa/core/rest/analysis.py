from pathlib import Path
import re
import subprocess

from django.conf import settings
from drf_yasg.utils import no_body, swagger_auto_schema
from guardian.shortcuts import get_objects_for_user
import pandas as pd
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from miqa.core.models import Analysis, Experiment, Frame, Project, Scan
from miqa.core.rest.frame import FrameSerializer
from miqa.core.rest.permissions import project_permission_required

from ..tasks import myod1, segment_wsi, survivability, tp53, subtype


class AnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = Analysis
        fields = [
            'id',
            'slurm_id',
            'input',
            'output',
            'status',
            'scan',
            'analysis_type',
            'analysis_result'
        ]
        ref_name = 'scan_analysis'

    scan = serializers.SerializerMethodField('convert_scan')
    status = serializers.SerializerMethodField('get_update')

    def convert_scan(self, obj):
        return obj.scan.id

    def get_update(self, obj):
        if obj.status == 3:
            return obj.status
        if obj.status == 4:
            # Remove error analysis or keep it somewhere?
            return obj.status
        # if status is not error
        if obj.slurm_id:
            args = 'squeue -j {}'.format(obj.slurm_id)
            output = subprocess.Popen(args,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            out_put = output.communicate()[0]
            found = re.findall(obj.slurm_id, out_put.decode())
            if len(found) == 0:
                obj.status = 3
                if Path(obj.analysis_result).is_file():
                    f = open(obj.analysis_result, 'r')
                    content = f.read()
                    obj.analysis_result = content
                else:
                    obj.status = 4
                    pass
                obj.save()
                return obj.status
            return obj.status
        return obj.status


class ScanAnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = Scan
        fields = [
            'id',
            'frames',
            'analysis'
        ]
    analysis = AnalysisSerializer(many=True, read_only=True)
    frames = FrameSerializer(many=True, read_only=True)


def is_valid_scan(scan_id):
    try:
        Scan.objects.get(id=scan_id)
    except Scan.DoesNotExist:
        raise serializers.ValidationError(f'Scan {scan_id} does not exist.')


def is_analysis_exist(scan_obj, analysis_type):
    for exist_analysis in ScanAnalysisSerializer(scan_obj).data['analysis']:
        if exist_analysis['analysis_type'] == analysis_type and exist_analysis['status'] == 3:
            return True
        if exist_analysis['status'] == 4:
            Analysis.objects.get(id=exist_analysis['id']).delete()
            # Only delete segmentation frame if failed analysis is segment
            if exist_analysis['analysis_type'] == 'SEGMENT':
                for frame in Frame.objects.filter(scan=exist_analysis['scan']):
                    if frame.frame_number == 1:
                        frame.delete()
    return False


class AnalysisCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Analysis
        fields = ['id', 'input', 'output', 'analysis_type', 'scan']
        extra_kwargs = {'content': {'required': True}}

    scan = serializers.CharField(required=False, validators=[is_valid_scan])


class AnalysisViewSet(ReadOnlyModelViewSet, mixins.CreateModelMixin, mixins.DestroyModelMixin):
    serializer_class = AnalysisSerializer

    def get_queryset(self):
        projects = get_objects_for_user(
            self.request.user,
            [f'core.{perm}' for perm in Project().get_read_permission_groups()],
            any_perm=True,
        )
        return Analysis.objects.filter(scan__experiment__project__in=projects)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        frame_id = AnalysisSerializer(instance).data['output']
        if frame_id:
            Frame.objects.get(id=frame_id).delete()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    # To do experiment based delete all
    @action(detail=False, methods=['DELETE'])
    def delete_all(self, request):
        for analysis in Analysis.objects.all():
            if analysis.output != '':
                Frame.objects.get(id=analysis.output).delete()
        Analysis.objects.all().delete()
        return Response('Analysis all deleted')

    @swagger_auto_schema(
        request_body=AnalysisCreateSerializer(),
        responses={201: AnalysisSerializer},
    )
    @action(detail=False, methods=['POST'], permission_classes=[IsAuthenticated])
    def segment_all(self, request, *args, **kwargs):
        # preparing data
        frame_ids = []
        for exp in request.data['params']['experiments']:
            experiment = Experiment.objects.get(id=exp)
            # frames = Frame.objects.filter(scan__experiment=experiment)
            scans = Scan.objects.filter(experiment=experiment)
            for scan_obj in scans:
                frames = ScanAnalysisSerializer(scan_obj).data['frames']
                analysis_exist = is_analysis_exist(scan_obj, 'SEGMENT')
                for frame in frames:
                    if frame['extension'] in ['.svs', '.tif'] and not analysis_exist:
                        frame_ids.append(frame['id'])
        # create slurm task
        if len(frame_ids):
            segment_wsi.delay(frame_ids)
            return Response(
                data='Successfully submit analysis.',
                status=status.HTTP_201_CREATED,
            )
        else:
            return Response(
                data='Already has segmentation results or still running.',
                status=status.HTTP_204_NO_CONTENT,
            )

    @swagger_auto_schema(
        request_body=no_body
    )
    @project_permission_required(review_access=True, experiments__pk='pk')
    @action(detail=True, methods=['POST'], permission_classes=[IsAuthenticated])
    def segment(self, request, pk=None):
        print(pk)
        print('segment')

    @swagger_auto_schema(
        request_body=AnalysisCreateSerializer(),
        responses={201: AnalysisSerializer},
    )
    @action(detail=False, methods=['POST'], permission_classes=[IsAuthenticated])
    def myod1_all(self, request, *args, **kwargs):
        # preparing data
        org_seg_ids = []
        for exp in request.data['params']['experiments']:
            experiment = Experiment.objects.get(id=exp)
            scans = Scan.objects.filter(experiment=experiment)
            for scan_obj in scans:
                scan_analysis_serializer = ScanAnalysisSerializer(scan_obj).data
                analyses = scan_analysis_serializer['analysis']
                # segment_exit = any(analysis['analysis_type'] == 'SEGMENT'
                # for analysis in analyses)
                analysis_exist = is_analysis_exist(scan_obj, 'MYOD1')
                for analysis in analyses:
                    if analysis['analysis_type'] == 'SEGMENT' and not analysis_exist:
                        org_id = analysis['input']
                        seg_id = analysis['output']
                        org_seg_ids.append((org_id, seg_id))
        # create slurm task
        if len(org_seg_ids):
            myod1.delay(org_seg_ids)
            return Response(
                data='Successfully submit MyoD1 analysis.',
                status=status.HTTP_201_CREATED,
            )
        else:
            return Response(
                data='Already has MyoD1 results or no SEGMENT exist.',
                status=status.HTTP_201_CREATED,
            )

    @swagger_auto_schema(
        request_body=no_body
    )
    @project_permission_required(review_access=True, experiments__pk='pk')
    @action(detail=True, methods=['POST'], permission_classes=[IsAuthenticated])
    def myod1(self, request, pk=None):
        print(pk)
        print('myod1')

    @swagger_auto_schema(
        request_body=AnalysisCreateSerializer(),
        responses={201: AnalysisSerializer},
    )
    @action(detail=False, methods=['POST'], permission_classes=[IsAuthenticated])
    def survivability_all(self, request, *args, **kwargs):
        # preparing data
        org_seg_ids = []
        for exp in request.data['params']['experiments']:
            experiment = Experiment.objects.get(id=exp)
            scans = Scan.objects.filter(experiment=experiment)
            for scan_obj in scans:
                scan_analysis_serializer = ScanAnalysisSerializer(scan_obj).data
                analyses = scan_analysis_serializer['analysis']
                # segment_exit = any(analysis['analysis_type'] == 'SEGMENT'
                # for analysis in analyses)
                analysis_exist = is_analysis_exist(scan_obj, 'SURVIVABILITY')
                for analysis in analyses:
                    if analysis['analysis_type'] == 'SEGMENT' and not analysis_exist:
                        org_id = analysis['input']
                        seg_id = analysis['output']
                        org_seg_ids.append((org_id, seg_id))
        fastmode = False
        if 'fastmode' in request.data['params']:
            fastmode = request.data['params']['fastmode']
        # create slurm task
        if len(org_seg_ids):
            survivability.delay(org_seg_ids, fastmode=fastmode)
            return Response(
                data='Successfully submit Survivability analysis.',
                status=status.HTTP_201_CREATED,
            )
        else:
            return Response(
                data='Already has Survivability results or no SEGMENT exist.',
                status=status.HTTP_201_CREATED,
            )

    @swagger_auto_schema(
        request_body=no_body
    )
    @project_permission_required(review_access=True, experiments__pk='pk')
    @action(detail=True, methods=['POST'], permission_classes=[IsAuthenticated])
    def survivability(self, request, pk=None):
        print(pk)
        print('survivability')


    @swagger_auto_schema(
        request_body=AnalysisCreateSerializer(),
        responses={201: AnalysisSerializer},
    )
    @action(detail=False, methods=['POST'], permission_classes=[IsAuthenticated])
    def subtype_all(self, request, *args, **kwargs):
        # preparing data
        org_seg_ids = []
        for exp in request.data['params']['experiments']:
            experiment = Experiment.objects.get(id=exp)
            scans = Scan.objects.filter(experiment=experiment)
            for scan_obj in scans:
                scan_analysis_serializer = ScanAnalysisSerializer(scan_obj).data
                analyses = scan_analysis_serializer['analysis']
                # segment_exit = any(analysis['analysis_type'] == 'SEGMENT'
                # for analysis in analyses)
                analysis_exist = is_analysis_exist(scan_obj, 'SUBTYPE')
                for analysis in analyses:
                    if analysis['analysis_type'] == 'SEGMENT' and not analysis_exist:
                        org_id = analysis['input']
                        seg_id = analysis['output']
                        org_seg_ids.append((org_id, seg_id))
        # create slurm task
        if len(org_seg_ids):
            subtype.delay(org_seg_ids)
            return Response(
                data='Successfully submit SUBTYPE classification analysis.',
                status=status.HTTP_201_CREATED,
            )
        else:
            return Response(
                data='Already has SUBTYPE classification results or no SEGMENT exist.',
                status=status.HTTP_201_CREATED,
            )

    @swagger_auto_schema(
        request_body=no_body
    )
    @project_permission_required(review_access=True, experiments__pk='pk')
    @action(detail=True, methods=['POST'], permission_classes=[IsAuthenticated])
    def subtype(self, request, pk=None):
        print(pk)
        print('subtype')


    @swagger_auto_schema(
        request_body=AnalysisCreateSerializer(),
        responses={201: AnalysisSerializer},
    )
    @action(detail=False, methods=['POST'], permission_classes=[IsAuthenticated])
    def tp53_all(self, request, *args, **kwargs):
        # preparing data
        org_seg_ids = []
        for exp in request.data['params']['experiments']:
            experiment = Experiment.objects.get(id=exp)
            scans = Scan.objects.filter(experiment=experiment)
            for scan_obj in scans:
                scan_analysis_serializer = ScanAnalysisSerializer(scan_obj).data
                analyses = scan_analysis_serializer['analysis']
                # segment_exit = any(analysis['analysis_type'] == 'SEGMENT'
                # for analysis in analyses)
                analysis_exist = is_analysis_exist(scan_obj, 'TP53')
                for analysis in analyses:
                    if analysis['analysis_type'] == 'SEGMENT' and not analysis_exist:
                        org_id = analysis['input']
                        seg_id = analysis['output']
                        org_seg_ids.append((org_id, seg_id))
        # create slurm task
        if len(org_seg_ids):
            tp53.delay(org_seg_ids)
            return Response(
                data='Successfully submit TP53 analysis.',
                status=status.HTTP_201_CREATED,
            )
        else:
            return Response(
                data='Already has TP53 results or no SEGMENT exist.',
                status=status.HTTP_201_CREATED,
            )

    @swagger_auto_schema(
        request_body=no_body
    )
    @project_permission_required(review_access=True, experiments__pk='pk')
    @action(detail=True, methods=['POST'], permission_classes=[IsAuthenticated])
    def tp53(self, request, pk=None):
        print(pk)
        print('tp53')


    @swagger_auto_schema(
    )
    @action(detail=False, methods=['GET'], permission_classes=[IsAuthenticated])
    def cohort(self, request, *args, **kwargs):
        cohort_name = 'COHORT_' + request.query_params.get('cohortName')
        if cohort_name in settings.GLOBAL_SETTINGS:
            cohort_df = pd.read_csv(settings.GLOBAL_SETTINGS[cohort_name])
            return Response(
                cohort_df.to_dict('records'),
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                'No analysis found',
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
