import markdown
from bson import ObjectId
from fastapi import HTTPException
from jinja2 import Environment, FileSystemLoader
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agents.report_generator_agent import generate_report_content

# Configure Jinja2
env = Environment(loader=FileSystemLoader("app/templates"))

async def create_report_for_student(student_id: str, db: AsyncIOMotorDatabase) -> str:
    """
    Orchestrates the report generation for a specific student and returns HTML.

    Args:
        student_id: The ID of the student.
        db: The database instance.

    Returns:
        The generated report as an HTML string.
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
    }

    # Generate the report content in Markdown
    markdown_content = await generate_report_content(full_student_data)

    # Convert Markdown to HTML
    html_body = markdown.markdown(markdown_content)

    # Render the final HTML with the template
    template = env.get_template("report_template.html")
    html_output = template.render(
        student_name=student_data.get("name", "Aluno"), 
        report_body=html_body
    )

    return html_output

