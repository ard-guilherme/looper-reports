from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.db.session import get_database
from app.services.report_service import create_report_for_student

router = APIRouter()

@router.post("/generate/{student_id}", response_class=HTMLResponse)
async def generate_report(
    student_id: str, 
    db: AsyncIOMotorDatabase = Depends(get_database)
) -> str:
    """
    Generates a fitness report for a given student ID.
    """
    html_content = await create_report_for_student(student_id=student_id, db=db)
    return html_content
