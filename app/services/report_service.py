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

    # Fetch check-ins data
    checkins_data = await db["checkins"].find({"student_id": ObjectId(student_id)}).to_list(length=None)

    # Fetch macro goals data
    macro_goals_data = await db["macro_goals"].find({"student_id": ObjectId(student_id)}).to_list(length=None)

    # Combine all data into a single dictionary for the agent
    full_student_data = {
        "student_profile": student_data,
        "checkins": checkins_data,
        "macro_goals": macro_goals_data,
        # Add other data sources here as they become available
    }

    # Validate data with Pydantic model (optional, depending on how strict we want to be with combined data)
    # For now, we'll pass the raw combined data to the agent, assuming it can handle the structure.
    # If we want to validate, we'd need a more complex Pydantic model for the full_student_data.

    # Generate the report content by calling the agent
    report_content = await generate_report_content(full_student_data)

    return report_content
