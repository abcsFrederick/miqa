import os
from pathlib import Path
import csv
import glob

file_name = './rms.csv'
dataset_path = '/scratch/IVG_scratch/ziaeid2/sarcoma/Dataset'
accept_types = ('*.tif', 'P-*.svs')


with open(file_name, mode='w') as rms_file:
    writer = csv.writer(rms_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)

    writer.writerow(['project_name', 'experiment_name', 'scan_name', 'scan_type',
        'frame_number', 'file_location', 'experiment_notes', 'subject_id',
        'session_id', 'scan_link', 'last_decision', 'last_decision_creator',
        'last_decision_note', 'last_decision_created', 'identified_artifacts',
        'location_of_interest'])
    all_files = []
    for accept_type in accept_types:
        all_files.extend(Path(dataset_path).glob(accept_type))
    for index, file in enumerate(all_files):
        writer.writerow(['Sarcoma', 'sarcoma_' + str(index // 3), file.name, 'WSI',
        0, str(file), '', '',
        '', '', '', '',
        '', '', '',
        ''])
        if index >= 100:
            break
