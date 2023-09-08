#!/bin/bash
source /var/opt/MIQA/env/bin/activate
source /var/opt/MIQA/miqa/dev/export-env.sh
/var/opt/MIQA/env/bin/gunicorn -k gthread --threads 8 --bind localhost:8000 miqa.wsgi --pid /var/opt/MIQA/rms2.pid --log-file /var/opt/MIQA/rms2.log
