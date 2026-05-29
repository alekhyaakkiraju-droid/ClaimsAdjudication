# Generated manually for WO-026

from django.db import migrations, models
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("claim", "0036_alter_claim_admin_delete_claimadmin"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClaimJob",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.CharField(default=uuid.uuid4, max_length=36, unique=True)),
                ("job_type", models.CharField(max_length=64)),
                ("status", models.CharField(default="pending", max_length=16)),
                ("queue_name", models.CharField(default="default", max_length=64)),
                ("priority", models.IntegerField(default=0)),
                ("payload", models.JSONField(default=dict)),
                ("result", models.JSONField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True, null=True)),
                ("retry_count", models.IntegerField(default=0)),
                ("max_retries", models.IntegerField(default=3)),
                ("audit_user_id", models.IntegerField(blank=True, null=True)),
                ("client_mutation_id", models.CharField(blank=True, max_length=255, null=True)),
                ("created", models.DateTimeField(default=django.utils.timezone.now)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "claim_ClaimJob",
                "managed": True,
            },
        ),
        migrations.AddIndex(
            model_name="claimjob",
            index=models.Index(
                fields=["status", "queue_name", "priority", "created"],
                name="claim_claim_status_wo026_idx",
            ),
        ),
    ]
