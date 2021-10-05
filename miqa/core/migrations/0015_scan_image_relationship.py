# Generated by Django 3.2.7 on 2021-10-05 00:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_rename_session_to_project'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='image',
            options={'ordering': ['frame_number']},
        ),
        migrations.AlterModelOptions(
            name='scan',
            options={'ordering': ['name', 'scan_type']},
        ),
        migrations.RemoveConstraint(
            model_name='scan',
            name='scan_unique_constraint',
        ),
        migrations.RemoveIndex(
            model_name='image',
            name='core_image_scan_id_4369e2_idx',
        ),
        migrations.RenameField(
            model_name='scan',
            old_name='scan_id',
            new_name='name',
        ),
        migrations.RemoveField(
            model_name='image',
            name='name',
        ),
        migrations.RemoveField(
            model_name='scan',
            name='site',
        ),
        migrations.AddField(
            model_name='image',
            name='frame_number',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='scan',
            name='scan_type',
            field=models.CharField(choices=[('T1', 'T1'), ('T2', 'T2'), ('FMRI', 'FMRI'), ('MRA', 'MRA'), ('PD', 'PD'), ('DTI', 'DTI'), ('DWI', 'DWI')], default='T1', max_length=10),
        ),
        migrations.AddIndex(
            model_name='image',
            index=models.Index(fields=['scan', 'frame_number'], name='core_image_scan_id_26e3ff_idx'),
        ),
    ]
