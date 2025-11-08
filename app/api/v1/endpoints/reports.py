import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.db.session import get_database
from app.services.report_service import create_report_for_student

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/generate/{student_id}", response_class=HTMLResponse)
async def generate_report(
    student_id: str, 
    db: AsyncIOMotorDatabase = Depends(get_database)
) -> str:
    """
    Generates a fitness report for a given student ID.
    """
    logger.info(f"Report generation requested for student_id: {student_id}")
    try:
        html_content = await create_report_for_student(student_id=student_id, db=db)
        logger.info(f"Successfully generated report for student_id: {student_id}")
        return html_content
    except HTTPException as e:
        logger.error(f"HTTPException for student_id {student_id}: {e.status_code} - {e.detail}")
        raise
    except Exception as e:
        logger.critical(f"An unexpected error occurred for student_id {student_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal server error occurred.")
