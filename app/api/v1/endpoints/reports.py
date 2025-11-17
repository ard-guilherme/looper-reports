import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.db.session import get_database
from app.services import report_service

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/generate-bulk", status_code=202)
async def generate_bulk_reports_endpoint(
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Triggers the asynchronous bulk generation of reports for all active students.
    """
    logger.info("Bulk report generation endpoint triggered.")
    background_tasks.add_task(report_service.generate_bulk_reports, db)
    return {"message": "Bulk report generation has been started in the background."}

@router.post("/generate/{student_id}", response_class=HTMLResponse)
async def generate_report(
    student_id: str, 
    db: AsyncIOMotorDatabase = Depends(get_database)
) -> HTMLResponse:
    """
    Generates a fitness report for a given student ID.
    """
    logger.info(f"Report generation requested for student_id: {student_id}")
    try:
        html_content = await report_service.create_report_for_student(student_id=student_id, db=db)
        logger.info(f"Successfully generated report for student_id: {student_id}")
        return HTMLResponse(content=html_content)
    except HTTPException as e:
        logger.error(f"HTTPException for student_id {student_id}: {e.status_code} - {e.detail}")
        raise
    except Exception as e:
        logger.critical(f"An unexpected error occurred for student_id {student_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal server error occurred.")
