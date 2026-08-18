import asyncio
import sys
from pathlib import Path

backend_dir = Path(r"d:\Axiora-pulse\backend")
sys.path.insert(0, str(backend_dir))

from app.db.database import AsyncSessionLocal
from app.db.models import Survey, User
from app.services.survey_service import survey_service
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as db:
        # Fetch survey 14 or any survey
        res = await db.execute(select(Survey).where(Survey.id == 14))
        survey = res.scalar_one_or_none()
        print("Survey 14 in DB:", survey)
        if not survey:
            all_s = await db.execute(select(Survey))
            surveys = all_s.scalars().all()
            print("Existing survey IDs in DB:", [s.id for s in surveys])
            if surveys:
                survey = surveys[0]
                print(f"Using survey ID {survey.id} instead")
            else:
                print("No surveys exist in DB!")
                return

        # Fetch user
        u_res = await db.execute(select(User).where(User.id == survey.user_id))
        user = u_res.scalar_one_or_none()
        print("Survey owner user:", user)

        print(f"Running post-link analysis for survey {survey.id}...")
        try:
            result = await survey_service.run_post_link_analysis(survey.id, user, db)
            print("SUCCESS! Analysis result keys:", list(result.keys()) if isinstance(result, dict) else result)
        except Exception as e:
            print("ERROR CAUGHT:")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
