import markdown
from bson import ObjectId
from datetime import datetime
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

    student_obj_id = ObjectId(student_id)

    # --- 1. Fetch all data sources ---
    student_data = await db["students"].find_one({"_id": student_obj_id})
    if not student_data:
        raise HTTPException(status_code=404, detail=f"Student with ID {student_id} not found")

    checkins_data = await db["checkins"].find({"student_id": student_obj_id}).to_list(length=None)
    macro_goals_data = await db["macro_goals"].find({"student_id": student_obj_id}).to_list(length=None)
    bioimpedance_data = await db["bioimpedancias"].find({"student_id": student_obj_id}).to_list(length=None)
    past_reports_data = await db["relatorios"].find({"student_id": student_obj_id}).sort("generated_at", -1).limit(2).to_list(length=2)

    # Combine all data for the agent
    full_student_data = {
        "student_profile": student_data,
        "checkins": checkins_data,
        "macro_goals": macro_goals_data,
        "bioimpedance_data": bioimpedance_data,
        "past_reports": past_reports_data,
    }

    # --- 2. Generate the new report content ---
    markdown_content = await generate_report_content(full_student_data)

    # Convert Markdown to HTML
    html_body = markdown.markdown(markdown_content)

    # Render the final HTML with the template
    template = env.get_template("report_template.html")
    final_html_output = template.render(
        student_name=student_data.get("name", "Aluno"), 
        report_body=html_body
    )

    # --- 3. Save the newly generated report to the database ---
    new_report = {
        "student_id": student_obj_id,
        "generated_at": datetime.utcnow(),
        "html_content": final_html_output
    }
    await db["relatorios"].insert_one(new_report)

    # --- 4. Return the final report ---
    return final_html_output

