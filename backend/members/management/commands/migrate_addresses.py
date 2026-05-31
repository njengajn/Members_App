from django.core.management.base import BaseCommand
from backend.members.models import Member, Address


class Command(BaseCommand):
    help = "Migrate text addresses to Address model (SAFE VERSION)"

    def handle(self, *args, **kwargs):
        created_count = 0
        linked_count = 0
        skipped_count = 0

        for member in Member.objects.all():

            # -----------------------------------------
            # ✅ SKIP if already linked (NEW SYSTEM)
            # -----------------------------------------
            if isinstance(member.address, Address):
                skipped_count += 1
                continue

            # -----------------------------------------
            # HANDLE OLD TEXT DATA (ONLY IF EXISTS)
            # -----------------------------------------
            raw = str(member.address or "").strip()

            if not raw:
                skipped_count += 1
                continue

            # -----------------------------------------
            # SIMPLE PARSER
            # -----------------------------------------
            parts = [p.strip() for p in raw.split(",") if p.strip()]

            house_number = parts[0] if len(parts) > 0 else ""
            line_1 = parts[1] if len(parts) > 1 else ""
            town = parts[2] if len(parts) > 2 else ""

            if not line_1:
                line_1 = house_number
                house_number = ""

            # -----------------------------------------
            # CREATE / GET ADDRESS
            # -----------------------------------------
            address, created = Address.objects.get_or_create(
                house_number=house_number,
                line_1=line_1,
                town=town,
                defaults={
                    "line_2": "",
                    "county": "",
                    "postcode": "UNK",
                    "country": "UK",
                }
            )

            if created:
                created_count += 1

            # -----------------------------------------
            # LINK MEMBER
            # -----------------------------------------
            member.address = address
            member.save()

            linked_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"""
Migration complete:
- Linked: {linked_count}
- Created addresses: {created_count}
- Skipped: {skipped_count}
"""
            )
        )