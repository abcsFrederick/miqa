from datetime import datetime
from io import BytesIO, StringIO
import json
from pathlib import Path
import tempfile
from typing import Dict, List, Optional

import boto3
from botocore import UNSIGNED
from botocore.client import Config
from celery import shared_task
import dateparser
from django.conf import settings
from django.contrib.auth.models import User
import large_image
import pandas
from rest_framework.exceptions import APIException

from miqa.core.conversion.import_export_csvs import (  # IMPORT_CSV_COLUMNS,
    IMPORT_CSV_COLUMNS_RMS,
    import_dataframe_to_dict,
    validate_import_dict,
)
from miqa.core.conversion.nifti_to_zarr_ngff import nifti_to_zarr_ngff
from miqa.core.models import (
    Analysis,
    Evaluation,
    Experiment,
    Frame,
    GlobalSettings,
    Project,
    Scan,
    ScanDecision,
)
from miqa.core.models.frame import StorageMode
from miqa.core.models.scan_decision import DECISION_CHOICES, default_identified_artifacts

from . import utils


def _get_s3_client(public: bool):
    if public:
        return boto3.client('s3', config=Config(signature_version=UNSIGNED))
    else:
        return boto3.client('s3')


def _download_from_s3(path: str, public: bool) -> bytes:
    bucket, key = path.strip()[5:].split('/', maxsplit=1)
    client = _get_s3_client(public)
    buf = BytesIO()
    client.download_fileobj(bucket, key, buf)
    return buf.getvalue()


@shared_task
def evaluate_frame_content(frame_id):
    from miqa.learning.evaluation_models import available_evaluation_models
    from miqa.learning.nn_inference import evaluate1

    frame = Frame.objects.get(id=frame_id)
    eval_model_name = frame.scan.experiment.project.evaluation_models[[frame.scan.scan_type][0]]
    s3_public = frame.scan.experiment.project.s3_public
    eval_model = available_evaluation_models[eval_model_name].load()
    with tempfile.TemporaryDirectory() as tmpdirname:
        # need to send a local version to NN
        if frame.storage_mode == StorageMode.LOCAL_PATH:
            dest = Path(frame.raw_path)
        else:
            dest = Path(tmpdirname, frame.content.name.split('/')[-1])
            with open(dest, 'wb') as fd:
                if frame.storage_mode == StorageMode.S3_PATH:
                    fd.write(_download_from_s3(frame.content.url, s3_public))
                else:
                    fd.write(frame.content.open().read())
        result = evaluate1(eval_model, dest)

        Evaluation.objects.create(
            frame=frame,
            evaluation_model=eval_model_name,
            results=result,
        )


@shared_task
def evaluate_data(frames_by_project):
    from miqa.learning.evaluation_models import available_evaluation_models
    from miqa.learning.nn_inference import evaluate_many

    model_to_frames_map = {}
    for project_id, frame_ids in frames_by_project.items():
        project = Project.objects.get(id=project_id)
        for frame_id in frame_ids:
            frame = Frame.objects.get(id=frame_id)
            file_path = frame.raw_path
            if frame.storage_mode == StorageMode.S3_PATH or Path(file_path).exists():
                eval_model_name = project.evaluation_models[[frame.scan.scan_type][0]]
                if eval_model_name not in model_to_frames_map:
                    model_to_frames_map[eval_model_name] = []
                model_to_frames_map[eval_model_name].append(frame)

    with tempfile.TemporaryDirectory() as tmpdirname:
        tmpdir = Path(tmpdirname)
        for model_name, frame_set in model_to_frames_map.items():
            current_model = available_evaluation_models[model_name].load()
            file_paths = {frame: frame.raw_path for frame in frame_set}
            for frame, file_path in file_paths.items():
                if frame.storage_mode == StorageMode.S3_PATH:
                    s3_public = frame.scan.experiment.project.s3_public
                    dest = tmpdir / frame.path.name
                    with open(dest, 'wb') as fd:
                        fd.write(_download_from_s3(file_path, s3_public))
                    file_paths[frame] = dest
            results = evaluate_many(current_model, list(file_paths.values()))

            Evaluation.objects.bulk_create(
                [
                    Evaluation(
                        frame=frame,
                        evaluation_model=model_name,
                        results=results[file_paths[frame]],
                    )
                    for frame in frame_set
                ]
            )


def import_data(project_id: Optional[str]):
    if project_id is None:
        project = None
        import_path = GlobalSettings.load().import_path
        s3_public = False  # TODO we don't support this for global imports yet
    else:
        project = Project.objects.get(id=project_id)
        import_path = project.import_path
        s3_public = project.s3_public

    try:
        if import_path.endswith('.csv'):
            if import_path.startswith('s3://'):
                buf = _download_from_s3(import_path, s3_public).decode('utf-8')
            else:
                with open(import_path) as fd:
                    buf = fd.read()
            import_dict = import_dataframe_to_dict(
                pandas.read_csv(StringIO(buf), index_col=False, na_filter=False).astype(str),
                project,
            )
        elif import_path.endswith('.json'):
            if import_path.startswith('s3://'):
                import_dict = json.loads(_download_from_s3(import_path, s3_public))
            else:
                with open(import_path) as fd:
                    import_dict = json.load(fd)
        else:
            raise APIException(f'Invalid import file {import_path}. Must be CSV or JSON.')
    except (FileNotFoundError, boto3.exceptions.Boto3Error):
        raise APIException(f'Could not locate import file at {import_path}.')
    except PermissionError:
        raise APIException(f'MIQA lacks permission to read {import_path}.')

    import_dict, not_found_errors = validate_import_dict(import_dict, project)
    perform_import(import_dict)
    return not_found_errors


@shared_task
def perform_import(import_dict):
    new_projects: List[Project] = []
    new_experiments: List[Experiment] = []
    new_scans: List[Scan] = []
    new_frames: List[Frame] = []
    new_scan_decisions: List[ScanDecision] = []

    for project_name, project_data in import_dict['projects'].items():
        try:
            project_object = Project.objects.get(name=project_name)
        except Project.DoesNotExist:
            raise APIException(f'Project {project_name} does not exist.')

        # delete old imports of these projects
        Experiment.objects.filter(
            project=project_object
        ).delete()  # cascades to scans -> frames, scan_notes

        for experiment_name, experiment_data in project_data['experiments'].items():
            notes = experiment_data.get('notes', '')
            experiment_object = Experiment(
                name=experiment_name,
                project=project_object,
                note=notes,
            )
            new_experiments.append(experiment_object)

            for scan_name, scan_data in experiment_data['scans'].items():
                subject_id = scan_data.get('subject_id', None)
                session_id = scan_data.get('session_id', None)
                scan_link = scan_data.get('scan_link', None)
                scan_object = Scan(
                    name=scan_name,
                    scan_type=scan_data['type'],
                    experiment=experiment_object,
                    subject_id=subject_id,
                    session_id=session_id,
                    scan_link=scan_link,
                )

                if 'last_decision' in scan_data:
                    last_decision_dict = scan_data['last_decision']
                    if (
                        last_decision_dict
                        and 'decision' in last_decision_dict
                        and len(last_decision_dict['decision']) > 0
                    ):
                        try:
                            creator = User.objects.get(email=last_decision_dict['creator'])
                        except User.DoesNotExist:
                            creator = None
                        note = ''
                        created = (
                            datetime.now() if settings.REPLACE_NULL_CREATION_DATETIMES else None
                        )
                        location = {}
                        if last_decision_dict['note']:
                            note = last_decision_dict['note'].replace(';', ',')
                        if last_decision_dict['created']:
                            valid_dt = dateparser.parse(last_decision_dict['created'])
                            if valid_dt:
                                created = valid_dt.strftime('%Y-%m-%d %H:%M')
                        if last_decision_dict['location'] and last_decision_dict['location'] != '':
                            slices = [
                                axis.split('=')[1]
                                for axis in last_decision_dict['location'].split(';')
                            ]
                            location = {
                                'i': slices[0],
                                'j': slices[1],
                                'k': slices[2],
                            }
                        if last_decision_dict['decision'] in [dec[0] for dec in DECISION_CHOICES]:
                            last_decision = ScanDecision(
                                decision=last_decision_dict['decision'],
                                creator=creator,
                                created=created,
                                note=note,
                                user_identified_artifacts={
                                    artifact_name: (
                                        1
                                        if last_decision_dict['user_identified_artifacts']
                                        and artifact_name
                                        in last_decision_dict['user_identified_artifacts']
                                        else 0
                                    )
                                    for artifact_name in default_identified_artifacts().keys()
                                },
                                location=location,
                                scan=scan_object,
                            )
                            new_scan_decisions.append(last_decision)
                new_scans.append(scan_object)
                for frame_number, frame_data in scan_data['frames'].items():

                    if frame_data['file_location']:
                        frame_object = Frame(
                            frame_number=frame_number,
                            raw_path=frame_data['file_location'],
                            scan=scan_object,
                        )
                        new_frames.append(frame_object)
                        if settings.ZARR_SUPPORT and Path(frame_object.raw_path).exists():
                            nifti_to_zarr_ngff.delay(frame_data['file_location'])

    # if any scan has no frames, it should not be created
    new_scans = [
        new_scan
        for new_scan in new_scans
        if any(new_frame.scan == new_scan for new_frame in new_frames)
    ]
    # if any experiment has no scans, it should not be created
    new_experiments = [
        new_experiment
        for new_experiment in new_experiments
        if any(new_scan.experiment == new_experiment for new_scan in new_scans)
    ]

    Project.objects.bulk_create(new_projects)
    Experiment.objects.bulk_create(new_experiments)
    Scan.objects.bulk_create(new_scans)
    Frame.objects.bulk_create(new_frames)
    ScanDecision.objects.bulk_create(new_scan_decisions)

    # must use str, not UUID, to get sent to celery task properly
    frames_by_project: Dict[str, List[str]] = {}
    for frame in new_frames:
        project_id = str(frame.scan.experiment.project.id)
        if project_id not in frames_by_project:
            frames_by_project[project_id] = []
        if(''.join(Path(frame.raw_path).suffixes) in ['.nii.gz', '.nii', '.nrrd', '.mgz']):
            frames_by_project[project_id].append(str(frame.id))
        if(''.join(Path(frame.raw_path).suffixes) in ['.svs', '.tif']):
            wsi_thumbnail.delay(str(frame.id))

    evaluate_data.delay(frames_by_project)


def export_data(project_id: Optional[str]):
    if not project_id:
        export_path = GlobalSettings.load().export_path
    else:
        project = Project.objects.get(id=project_id)
        export_path = project.export_path
    parent_location = Path(export_path).parent
    if not parent_location.exists():
        raise APIException(f'No such location {parent_location} to create export file.')

    return perform_export(project_id)


@shared_task
def perform_export(project_id: Optional[str]):
    data: List[List[Optional[str]]] = []
    export_warnings = []

    if project_id is None:
        # A global export should export all projects
        project = None
        projects = list(Project.objects.all())
        export_path = GlobalSettings.load().export_path
    else:
        # A normal export should only export the current project
        project = Project.objects.get(id=project_id)
        projects = [project]
        export_path = project.export_path

    for project_object in projects:
        # project_frames = Frame.objects.filter(scan__experiment__project=project_object)
        # project_analysis = Analysis.objects.filter(scan__experiment__project=project_object)
        project_scans = Scan.objects.filter(experiment__project=project_object)
        for scan_object in project_scans:
            scans_analysis = Analysis.objects.filter(scan=scan_object)
            for analysis_object in scans_analysis:
                print('scan name is : ' + scan_object.name)
                print(analysis_object.analysis_type)
                row_data = [
                    project_object.name,
                    scan_object.experiment.name,
                    scan_object.name,
                    scan_object.scan_type,
                    analysis_object.analysis_type,
                    # frame_object.scan.subject_id,
                    # frame_object.scan.session_id,
                    # frame_object.scan.scan_link,
                    # analysis
                ]
                results = json.loads(analysis_object.analysis_result)
                if 'ARMS' in results:
                    row_data.append(round(results['ARMS'], 3))
                else:
                    row_data.append('')
                if 'ERMS' in results:
                    row_data.append(round(results['ERMS'], 3))
                else:
                    row_data.append('')
                if 'stroma' in results:
                    row_data.append(round(results['stroma'], 3))
                else:
                    row_data.append('')
                if 'necrosis' in results:
                    row_data.append(round(results['necrosis'], 3))
                else:
                    row_data.append('')
                if 'Positive Score' in results:
                    row_data.append(round(results['Positive Score'], 3))
                else:
                    row_data.append('')
                if 'secondBest' in results:
                    row_data.append(round(results['secondBest'], 3))
                else:
                    row_data.append('')
                if 'mean' in results:
                    row_data.append(round(results['mean'], 3))
                else:
                    row_data.append('')
                data.append(row_data)
        # print(data)

        # return
        # if project_frames.count() == 0:
        #     data.append([project_object.name])

        # for frame_object in project_frames:
        #     if frame_object.storage_mode == StorageMode.LOCAL_PATH:
        #         # get analysis by scan
        #         print(frame_object.scan)
        #         analysis = Analysis.objects.filter(scan=frame_object.scan)
        #         print(analysis.__dict__)
        #         return analysis
        #         row_data = [
        #             project_object.name,
        #             frame_object.scan.experiment.name,
        #             frame_object.scan.name,
        #             frame_object.scan.scan_type,
        #             str(frame_object.frame_number),
        #             frame_object.raw_path,
        #             frame_object.scan.experiment.note,
        #             # frame_object.scan.subject_id,
        #             # frame_object.scan.session_id,
        #             # frame_object.scan.scan_link,
        #             # analysis
        #         ]
        #         last_decision = frame_object.scan.decisions.order_by('created').last()
        #         if last_decision:
        #             location = ''
        #             if last_decision.location:
        #                 location = (
        #                     f'i={last_decision.location["i"]};'
        #                     f'j={last_decision.location["j"]};'
        #                     f'k={last_decision.location["k"]}'
        #                 )
        #             artifacts = [
        #                 artifact
        #                 for artifact, value in last_decision.user_identified_artifacts.items()
        #                 if value == 1
        #             ]
        #             creator = ''
        #             if last_decision.creator:
        #                 creator = last_decision.creator.email
        #             created = None
        #             if last_decision.created:
        #                 created = str(last_decision.created)
        #             row_data += [
        #                 last_decision.decision,
        #                 creator,
        #                 last_decision.note.replace(',', ';'),
        #                 created,
        #                 ';'.join(artifacts),
        #                 location,
        #             ]
        #         else:
        #             row_data += ['' for i in range(6)]
        #         data.append(row_data)
        #     else:
        #         export_warnings.append(
        #             f'{frame_object.scan.name} not exported;
        #             this scan was uploaded, not imported.'
        #         )
    # export_df = pandas.DataFrame(data, columns=IMPORT_CSV_COLUMNS)
    export_df = pandas.DataFrame(data, columns=IMPORT_CSV_COLUMNS_RMS)
    try:
        if export_path.endswith('csv'):
            export_df.to_csv(export_path, index=False)
        elif export_path.endswith('json'):
            json_contents = import_dataframe_to_dict(export_df, project)
            with open(export_path, 'w') as fd:
                json.dump(json_contents, fd)
        else:
            raise APIException(
                f'Unknown format for export path {export_path}. Expected csv or json.'
            )
    except PermissionError:
        raise APIException(f'MIQA lacks permission to write to {export_path}.')
    return export_warnings


seg_prefix = 'Seg_'
thumb_prefix = 'thumb_'
myod1_prefix = 'myod1_'
survivability_prefix = 'survivability_'


def get_path(frame, *args, **kwargs):
    root = kwargs['_tempdir']
    if 'sub' in kwargs:
        Path(kwargs['_tempdir'], kwargs['sub']).mkdir(exist_ok=True)
        root = str(Path(kwargs['_tempdir'], kwargs['sub']))
    if frame.storage_mode == StorageMode.LOCAL_PATH:
        # move to NFS if neccessary or symlink under same folder for processing
        symlink_path = Path(root, frame.raw_path.split('/')[-1])
        Path(symlink_path).symlink_to(frame.raw_path)
        path = symlink_path
    else:
        path = Path(root, frame.content.name.split('/')[-1])
        with open(path, 'wb') as fd:
            if frame.storage_mode == StorageMode.S3_PATH:
                s3_public = frame.scan.experiment.project.s3_public
                fd.write(_download_from_s3(frame.content.url, s3_public))
            else:
                fd.write(frame.content.open().read())
    return root, path


def import_frame(frame_number, raw_path, scan_object):
    frame_object = Frame(
        frame_number=frame_number,
        raw_path=raw_path,
        scan=scan_object,
    )
    frame_object.save()
    return frame_object


@shared_task
@utils.with_tmpdir
def wsi_thumbnail(frame_id, *args, **kwargs):
    # configure large_image to handle really pig PNGs since sometimes this is used
    large_image.config.setConfig('max_small_image_size', 100000)
    frame = Frame.objects.get(id=frame_id)
    basename = ''
    if frame.storage_mode == StorageMode.LOCAL_PATH:
        basename = Path(frame.raw_path).stem
    else:
        basename = Path(frame.content.name).stem
    _, path = get_path(frame, **kwargs)
    print('generate a thumbnail for a WSI')
    # open an access handler on the large image
    source = large_image.getTileSource(path)
    # generate unique names for multiple runs.  Add extension so it is easier to use
    thumb_path = Path(kwargs['_tmp'], basename + '.png')

    thumbnail, mimetype = source.getThumbnail(
        width=800, height=1024, encoding='PNG')
    print('Made a thumbnail of type %s taking %d bytes' % (
        mimetype, len(thumbnail)))

    file_obj = open(thumb_path, 'wb')
    file_obj.write(thumbnail)
    file_obj.flush()
    file_obj.close()
    # scan_object = Scan.objects.get(id=frame.scan_id)
    frame.thumbnail_path = thumb_path
    frame.save()
#     print('thumbnail generation complete')
#     # return the name of the output file
#     return outname


@shared_task
@utils.with_tmpdir
def segment_wsi(frames, *args, **kwargs):
    from miqa.learning.nn_inference import seg_evaluate

    # fetching or relocating input into a single NFS folder
    analyses = []
    for frame_obj in frames:
        frame = Frame.objects.get(id=frame_obj)
        scan_object = Scan.objects.get(id=frame.scan_id)
        analysis = Analysis(
            scan=scan_object,
            status=1,
            analysis_type='SEGMENTATION'
        )
        analysis.save()
        root, _ = get_path(frame, **kwargs)
        # dest = Path(loc_, prefix + Path(wsi).stem + '.png')

        analysis.input = frame_obj
        analysis.status = 2
        analysis.save()
        analyses.append(analysis)
    tmp_input_dir = root
    # settings.GLOBAL_SETTINGS['SEGMENTATION']
    job_name = 'SEGMENTATION'
    slurm_id = seg_evaluate(tmp_input_dir, seg_prefix, thumb_prefix,
                            job_name, modules=['torch/1.7.0'])
    # import dest to a scan under same experiment or frame under same scan?
    # Do we upload file to bucket or just save in NFS as is
    print('Batch segmentation submit, slurm id: ', str(slurm_id))
    for index, frame_obj in enumerate(frames):
        frame = Frame.objects.get(id=frame_obj)
        scan_object = Scan.objects.get(id=frame.scan_id)
        basename = ''
        if frame.storage_mode == StorageMode.LOCAL_PATH:
            basename = Path(frame.raw_path).stem
        else:
            basename = Path(frame.content.name).stem
        seg_name = seg_prefix + basename + '.png'
        thumb_name = thumb_prefix + basename + '.png'
        json_name = seg_prefix + basename + '.json'
        seg_path = Path(kwargs['_tmp'], 'slurm-{}.{}'.format(job_name, str(slurm_id)), seg_name)
        thumb_path = Path(kwargs['_tmp'], 'slurm-{}.{}'.format(job_name, str(slurm_id)), thumb_name)
        json_path = Path(kwargs['_tmp'], 'slurm-{}.{}'.format(job_name, str(slurm_id)), json_name)

        seg_frame_object = import_frame(1, seg_path, scan_object)
        seg_frame_object.thumbnail_path = thumb_path
        seg_frame_object.save()

        analyses[index].slurm_id = str(slurm_id)
        analyses[index].output = seg_frame_object.id
        print('json path: ', json_path)
        analyses[index].analysis_result = json_path
        analyses[index].save()


@shared_task
@utils.with_tmpdir
def myod1(wsi_seg_ids, *args, **kwargs):
    from miqa.learning.nn_inference import myod1_evaluate

    # fetching or relocating input into a single NFS folder
    analyses = []
    for wsi_seg in wsi_seg_ids:
        wsi_frame = Frame.objects.get(id=wsi_seg[0])
        seg_frame = Frame.objects.get(id=wsi_seg[1])
        scan_object = Scan.objects.get(id=wsi_frame.scan_id)

        analysis = Analysis(
            scan=scan_object,
            status=1,
            analysis_type='MYOD1'
        )
        analysis.save()
        wsi_root, _ = get_path(wsi_frame, **kwargs, sub='wsi')
        seg_root, _ = get_path(seg_frame, **kwargs, sub='seg')
        # dest = Path(loc_, prefix + Path(wsi).stem + '.png')

        analysis.input = wsi_seg[0]
        analysis.status = 2
        analysis.save()
        analyses.append(analysis)

    # tmp_input_dir = kwargs['_tempdir']
    # settings.GLOBAL_SETTINGS['INFER_WSI']
    job_name = 'MYOD1'
    slurm_id = myod1_evaluate(wsi_root, seg_root, myod1_prefix, seg_prefix,
                              job_name, modules=['torch/1.7.0'])
    # import dest to a scan under same experiment or frame under same scan?
    # Do we upload file to bucket or just save in NFS as is
    print('Batch myod1 analysis submit, slurm id: ', str(slurm_id))
    for index, wsi_seg_id in enumerate(wsi_seg_ids):
        wsi_frame = Frame.objects.get(id=wsi_seg_id[0])
        seg_frame = Frame.objects.get(id=wsi_seg_id[1])
        scan_object = Scan.objects.get(id=wsi_frame.scan_id)
        basename = ''
        if wsi_frame.storage_mode == StorageMode.LOCAL_PATH:
            basename = Path(wsi_frame.raw_path).stem
        else:
            basename = Path(wsi_frame.content.name).stem

        json_name = myod1_prefix + basename + '.json'

        json_path = Path(kwargs['_tmp'], 'slurm-{}.{}'.format(job_name, str(slurm_id)), json_name)

        analyses[index].slurm_id = str(slurm_id)
        print('myod1 json path: ', json_path)
        analyses[index].analysis_result = json_path
        analyses[index].save()


@shared_task
@utils.with_tmpdir
def survivability(wsi_seg_ids, *args, **kwargs):
    from miqa.learning.nn_inference import survivability_evaluate

    # fetching or relocating input into a single NFS folder
    analyses = []
    for wsi_seg in wsi_seg_ids:
        wsi_frame = Frame.objects.get(id=wsi_seg[0])
        seg_frame = Frame.objects.get(id=wsi_seg[1])
        scan_object = Scan.objects.get(id=wsi_frame.scan_id)

        analysis = Analysis(
            scan=scan_object,
            status=1,
            analysis_type='SURVIVABILITY'
        )
        analysis.save()
        wsi_root, _ = get_path(wsi_frame, **kwargs, sub='wsi')
        seg_root, _ = get_path(seg_frame, **kwargs, sub='seg')
        # dest = Path(loc_, prefix + Path(wsi).stem + '.png')

        analysis.input = wsi_seg[0]
        analysis.status = 2
        analysis.save()
        analyses.append(analysis)

    # tmp_input_dir = kwargs['_tempdir']
    # settings.GLOBAL_SETTINGS['INFER_WSI']
    job_name = 'SURVIVABILITY'
    fastmode = kwargs['fastmode']
    slurm_id = survivability_evaluate(wsi_root, seg_root, survivability_prefix, seg_prefix,
                                      fastmode, job_name, modules=['torch/1.7.0'])
    # import dest to a scan under same experiment or frame under same scan?
    # Do we upload file to bucket or just save in NFS as is
    print('Batch survivability_evaluate analysis submit, slurm id: ', str(slurm_id))
    for index, wsi_seg_id in enumerate(wsi_seg_ids):
        wsi_frame = Frame.objects.get(id=wsi_seg_id[0])
        seg_frame = Frame.objects.get(id=wsi_seg_id[1])
        scan_object = Scan.objects.get(id=wsi_frame.scan_id)
        basename = ''
        if wsi_frame.storage_mode == StorageMode.LOCAL_PATH:
            basename = Path(wsi_frame.raw_path).stem
        else:
            basename = Path(wsi_frame.content.name).stem

        json_name = survivability_prefix + basename + '.json'

        json_path = Path(kwargs['_tmp'], 'slurm-{}.{}'.format(job_name, str(slurm_id)), json_name)

        analyses[index].slurm_id = str(slurm_id)
        print('survivability_evaluate json path: ', json_path)
        analyses[index].analysis_result = json_path
        analyses[index].save()


tp53_prefix = 'tp53_'

@shared_task
@utils.with_tmpdir
def tp53(wsi_seg_ids, *args, **kwargs):
    from miqa.learning.nn_inference import tp53_evaluate

    # fetching or relocating input into a single NFS folder
    analyses = []
    for wsi_seg in wsi_seg_ids:
        wsi_frame = Frame.objects.get(id=wsi_seg[0])
        seg_frame = Frame.objects.get(id=wsi_seg[1])
        scan_object = Scan.objects.get(id=wsi_frame.scan_id)

        analysis = Analysis(
            scan=scan_object,
            status=1,
            analysis_type='TP53'
        )
        analysis.save()
        wsi_root, _ = get_path(wsi_frame, **kwargs, sub='wsi')
        seg_root, _ = get_path(seg_frame, **kwargs, sub='seg')
        # dest = Path(loc_, prefix + Path(wsi).stem + '.png')

        analysis.input = wsi_seg[0]
        analysis.status = 2
        analysis.save()
        analyses.append(analysis)

    # tmp_input_dir = kwargs['_tempdir']
    # settings.GLOBAL_SETTINGS['INFER_WSI']
    job_name = 'TP53'
    slurm_id = tp53_evaluate(wsi_root, seg_root, tp53_prefix, seg_prefix,
                             job_name, modules=['torch/1.7.0'])
    # import dest to a scan under same experiment or frame under same scan?
    # Do we upload file to bucket or just save in NFS as is
    print('Batch tp53_evaluate analysis submit, slurm id: ', str(slurm_id))
    for index, wsi_seg_id in enumerate(wsi_seg_ids):
        wsi_frame = Frame.objects.get(id=wsi_seg_id[0])
        seg_frame = Frame.objects.get(id=wsi_seg_id[1])
        scan_object = Scan.objects.get(id=wsi_frame.scan_id)
        basename = ''
        if wsi_frame.storage_mode == StorageMode.LOCAL_PATH:
            basename = Path(wsi_frame.raw_path).stem
        else:
            basename = Path(wsi_frame.content.name).stem

        json_name = tp53_prefix + basename + '.json'

        json_path = Path(kwargs['_tmp'], 'slurm-{}.{}'.format(job_name, str(slurm_id)), json_name)

        analyses[index].slurm_id = str(slurm_id)
        print('tp53_evaluate json path: ', json_path)
        analyses[index].analysis_result = json_path
        analyses[index].save()


subtype_prefix = 'subtype_'

@shared_task
@utils.with_tmpdir
def subtype(wsi_seg_ids, *args, **kwargs):
    from miqa.learning.nn_inference import subtype_evaluate

    # fetching or relocating input into a single NFS folder
    analyses = []
    for wsi_seg in wsi_seg_ids:
        wsi_frame = Frame.objects.get(id=wsi_seg[0])
        seg_frame = Frame.objects.get(id=wsi_seg[1])
        scan_object = Scan.objects.get(id=wsi_frame.scan_id)

        analysis = Analysis(
            scan=scan_object,
            status=1,
            analysis_type='SUBTYPE'
        )
        analysis.save()
        wsi_root, _ = get_path(wsi_frame, **kwargs, sub='wsi')
        # dest = Path(loc_, prefix + Path(wsi).stem + '.png')

        analysis.input = wsi_seg[0]
        analysis.status = 2
        analysis.save()
        analyses.append(analysis)

    # tmp_input_dir = kwargs['_tempdir']
    # settings.GLOBAL_SETTINGS['INFER_WSI']
    job_name = 'SUBTYPE'
    slurm_id = subtype_evaluate(wsi_root, subtype_prefix, seg_prefix,
                                job_name, modules=['torch/1.7.0'])
    # import dest to a scan under same experiment or frame under same scan?
    # Do we upload file to bucket or just save in NFS as is
    print('Batch subtype_evaluate analysis submit, slurm id: ', str(slurm_id))
    for index, wsi_seg_id in enumerate(wsi_seg_ids):
        wsi_frame = Frame.objects.get(id=wsi_seg_id[0])
        seg_frame = Frame.objects.get(id=wsi_seg_id[1])
        scan_object = Scan.objects.get(id=wsi_frame.scan_id)
        basename = ''
        if wsi_frame.storage_mode == StorageMode.LOCAL_PATH:
            basename = Path(wsi_frame.raw_path).stem
        else:
            basename = Path(wsi_frame.content.name).stem

        json_name = subtype_prefix + basename + '.json'

        json_path = Path(kwargs['_tmp'], 'slurm-{}.{}'.format(job_name, str(slurm_id)), json_name)

        analyses[index].slurm_id = str(slurm_id)
        print('subtype_evaluate json path: ', json_path)
        analyses[index].analysis_result = json_path
        analyses[index].save()

