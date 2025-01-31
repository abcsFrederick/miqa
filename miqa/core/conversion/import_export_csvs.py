from datetime import datetime
from pathlib import Path
from typing import List, Optional as TypingOptional

import pandas
from rest_framework.exceptions import APIException
from schema import Optional, Or, Schema, SchemaError, Use

from miqa.core.models import GlobalSettings, Project

# subjectid and sessionid are for compatibility with PREDICT and other BidS datasets

IMPORT_CSV_COLUMNS = [
    'project_name',
    'experiment_name',
    'scan_name',
    'scan_type',
    'frame_number',
    'file_location',
    'experiment_notes',
    'subject_id',
    'session_id',
    'scan_link',
    'last_decision',
    'last_decision_creator',
    'last_decision_note',
    'last_decision_created',
    'identified_artifacts',
    'location_of_interest',
]


def validate_file_locations(input_dict, project, not_found_errors):
    if not isinstance(input_dict, dict):
        return input_dict, not_found_errors
    import_path = GlobalSettings.load().import_path if project is None else project.import_path
    for key, value in input_dict.items():
        if key == 'file_location':
            raw_path = Path(value.strip())
            if not value.startswith('s3://'):
                if not raw_path.is_absolute():
                    # not an absolute file path; refer to project import csv location
                    raw_path = Path(import_path).parent.parent / raw_path
                if not raw_path.exists():
                    not_found_errors.append(f'File not found: {raw_path}')
            input_dict[key] = str(raw_path) if value and 's3://' not in value else value
        else:
            new_value, not_found_errors = validate_file_locations(value, project, not_found_errors)
            input_dict[key] = new_value
    return input_dict, not_found_errors


def validate_import_dict(import_dict, project: TypingOptional[Project]):
    import_schema = Schema(
        {
            'projects': {
                Optional(Use(str)): {
                    'experiments': {
                        Optional(Use(str)): {
                            Optional('notes'): Optional(str, None),
                            'scans': {
                                Optional(Use(str)): {
                                    'type': Use(str),
                                    Optional('subject_id'): Or(str, None),
                                    Optional('session_id'): Or(str, None),
                                    Optional('scan_link'): Or(str, None),
                                    'frames': {Use(int): {'file_location': Use(str)}},
                                    Optional('decisions'): [
                                        {
                                            'decision': Use(str),
                                            'creator': Or(str, None),
                                            'note': Or(str, None),
                                            'created': Or(str, None),
                                            'user_identified_artifacts': Or(str, None),
                                            'location': Or(str, None),
                                        },
                                    ],
                                    Optional('last_decision'): Or(
                                        {
                                            'decision': Use(str),
                                            'creator': Or(str, None),
                                            'note': Or(str, None),
                                            'created': Or(str, None),
                                            'user_identified_artifacts': Or(str, None),
                                            'location': Or(str, None),
                                        },
                                        None,
                                    ),
                                }
                            },
                        }
                    }
                }
            }
        }
    )
    not_found_errors: List[str] = []
    try:
        import_schema.validate(import_dict)
        import_dict, not_found_errors = validate_file_locations(
            import_dict, project, not_found_errors
        )
    except SchemaError as e:
        import_path = GlobalSettings.load().import_path if project is None else project.import_path
        raise APIException(f'Invalid format of import file {import_path}. {e.autos[-1]}.')
    if not project:
        for project_name in import_dict['projects']:
            if not Project.objects.filter(name=project_name).exists():
                raise APIException(f'Project {project_name} does not exist')
    return import_dict, not_found_errors


def import_dataframe_to_dict(df, project):
    df_columns = list(df.columns)
    # The columns after the first 6 are optional
    if df_columns != IMPORT_CSV_COLUMNS and (
        len(df_columns) < 6 or df_columns != IMPORT_CSV_COLUMNS[: len(df_columns)]
    ):
        raise APIException(
            'Import file has invalid columns. '
            f'Expected {IMPORT_CSV_COLUMNS}, received {df_columns}.'
        )
    ingest_dict = {'projects': {}}
    for project_name, project_df in df.groupby('project_name'):
        if project and project_name != project.name:
            raise APIException(
                f'Import file contains rows for project "{project_name}, " \
                which does not match "{project.name}." Import failed.'
            )
        project_dict = {'experiments': {}}
        if list(project_df['experiment_name'].unique()) != ['']:
            for experiment_name, experiment_df in project_df.groupby('experiment_name'):
                experiment_dict = {'scans': {}}
                if 'experiment_notes' in experiment_df.columns:
                    experiment_dict['notes'] = experiment_df['experiment_notes'].iloc[0]
                for scan_name, scan_df in experiment_df.groupby('scan_name'):
                    scan_dict = {}
                    if list(scan_df['file_location'].unique()) != ['']:
                        try:
                            scan_dict = {
                                'type': scan_df['scan_type'].iloc[0],
                                'frames': {
                                    int(row[1]['frame_number']): {
                                        'file_location': row[1]['file_location']
                                    }
                                    for row in scan_df.iterrows()
                                },
                                'decisions': [],
                            }
                        except ValueError as e:
                            raise APIException(
                                f'Invalid frame number {str(e).split(":")[-1]}.'
                                f' Must be an integer value.'
                            )
                        if 'subject_id' in scan_df.columns:
                            scan_dict['subject_id'] = scan_df['subject_id'].iloc[0]
                        if 'session_id' in scan_df.columns:
                            scan_dict['session_id'] = scan_df['session_id'].iloc[0]
                        if 'scan_link' in scan_df.columns:
                            scan_dict['scan_link'] = scan_df['scan_link'].iloc[0]
                        if 'last_decision' in scan_df.columns and scan_df['last_decision'].iloc[0]:
                            decision_dict = {
                                'decision': scan_df['last_decision'].iloc[0],
                                'creator': scan_df['last_decision_creator'].iloc[0],
                                'note': scan_df['last_decision_note'].iloc[0],
                                'created': str(scan_df['last_decision_created'].iloc[0])
                                if scan_df['last_decision_created'].iloc[0]
                                else None,
                                'user_identified_artifacts': scan_df['identified_artifacts'].iloc[0]
                                or None,
                                'location': scan_df['location_of_interest'].iloc[0] or None,
                            }
                            decision_dict = {k: (v or None) for k, v in decision_dict.items()}
                            scan_dict['decisions'].append(decision_dict)

                        # added for BIDS import
                        if 'subject_ID' in scan_df.columns:
                            scan_dict['subject_ID'] = scan_df['subject_ID'].iloc[0]
                        if 'session_ID' in scan_df.columns:
                            scan_dict['session_ID'] = scan_df['session_ID'].iloc[0]
                        # ---- end of BIDS support addition

                        experiment_dict['scans'][scan_name] = scan_dict
                project_dict['experiments'][experiment_name] = experiment_dict
        ingest_dict['projects'][project_name] = project_dict
    return ingest_dict


def import_dict_to_dataframe(data):
    row_data = []
    for project_name, project_data in data.get('projects', {}).items():
        for experiment_name, experiment_data in project_data.get('experiments', {}).items():
            for scan_name, scan_data in experiment_data.get('scans', {}).items():
                for frame_number, frame_data in scan_data.get('frames', {}).items():
                    row = [
                        project_name,
                        experiment_name,
                        scan_name,
                        scan_data.get('type', ''),
                        frame_number,
                        frame_data.get('file_location', ''),
                        experiment_data.get('notes', ''),
                        scan_data.get('subject_id', ''),
                        scan_data.get('session_id', ''),
                        scan_data.get('scan_link', ''),
                    ]
                    sorted_decisions = sorted(
                        scan_data.get('decisions', []),
                        key=lambda d: datetime.strptime(
                            d['created'].split('+')[0], '%Y-%m-%d %H:%M:%S'
                        ),
                        reverse=True,
                    )
                    if len(sorted_decisions) > 0:
                        last_decision_data = sorted_decisions[0]
                        if last_decision_data:
                            row += [
                                last_decision_data.get('decision', ''),
                                last_decision_data.get('creator', ''),
                                last_decision_data.get('note', ''),
                                last_decision_data.get('created', ''),
                                last_decision_data.get('user_identified_artifacts', ''),
                                last_decision_data.get('location', ''),
                            ]
                        else:
                            row += ['' for i in range(6)]
                    else:
                        row += ['' for i in range(6)]
                    row_data.append(row)
    return pandas.DataFrame(row_data, columns=IMPORT_CSV_COLUMNS)
