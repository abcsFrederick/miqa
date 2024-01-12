from uuid import uuid4

from django.db import models
from django_extensions.db.models import TimeStampedModel

ANALYSIS_TYPES = [
    ('SEGMENTATION', 'SEGMENTATION'),
    ('MYOD1', 'MYOD1'),
    ('SURVIVABILITY', 'SURVIVABILITY'),
    ('TP53', 'TP53'),
    ('SUBTYPE', 'SUBTYPE'),
]

# status:
# 0 Stop
# 1 Fetching
# 2 Running
# 3 Success
# 4 Error


class Analysis(TimeStampedModel, models.Model):
    class Meta:
        ordering = ['status']

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    input = models.CharField(max_length=256, blank='Input WSI UUID')
    output = models.CharField(max_length=256, blank='Output file UUID')
    slurm_id = models.CharField(max_length=256, blank='Slurm ID')
    scan = models.ForeignKey('Scan', related_name='analysis', on_delete=models.CASCADE)
    status = models.IntegerField(default=0)
    analysis_type = models.CharField(max_length=25, choices=ANALYSIS_TYPES, default='SEGMENT')
    analysis_result = models.TextField(max_length=3000, null=True)
