from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("members", "0055_member_uniq_member_email_ci_nonblank"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                # Username must be unique regardless of letter case.
                """
                CREATE UNIQUE INDEX uniq_auth_user_username_ci
                ON auth_user (LOWER(username));
                """,

                # Nonblank email must be unique regardless of letter case.
                """
                CREATE UNIQUE INDEX uniq_auth_user_email_ci_nonblank
                ON auth_user (LOWER(email))
                WHERE email IS NOT NULL AND email <> '';
                """,
            ],
            reverse_sql=[
                "DROP INDEX uniq_auth_user_email_ci_nonblank;",
                "DROP INDEX uniq_auth_user_username_ci;",
            ],
        ),
    ]