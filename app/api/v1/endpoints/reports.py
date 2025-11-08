from fastapi import APIRouter

router = APIRouter()

@router.post("/generate/{student_id}")
async def generate_report(student_id: str):
    return {"message": f"Report generation requested for student ID: {student_id}"}
