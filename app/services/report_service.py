from bson import ObjectId
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agents.report_generator_agent import generate_report_content
from app.db.models import StudentModel

async def create_report_for_student(student_id: str, db: AsyncIOMotorDatabase) -> str:
    """
    Orchestrates the report generation for a specific student.

    Args:
        student_id: The ID of the student.
        db: The database instance.

    Returns:
        The generated report content as a string.
    """
    # Validate if the student_id is a valid MongoDB ObjectId
    if not ObjectId.is_valid(student_id):
        raise HTTPException(status_code=400, detail=f"Invalid student ID: {student_id}")

    # Fetch student data from the database
    student_data = await db["students"].find_one({"_id": ObjectId(student_id)})

    if not student_data:
        raise HTTPException(status_code=404, detail=f"Student with ID {student_id} not found")

    # Validate data with Pydantic model
    try:
        student = StudentModel(**student_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Data validation error for student {student_id}: {e}")

    # Generate the report content by calling the agent
    report_content = await generate_report_content(student.model_dump(by_alias=True))

    return report_content
