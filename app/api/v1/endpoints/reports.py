from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.db.session import get_database

router = APIRouter()

@router.post("/generate/{student_id}")
async def generate_report(student_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    # Exemplo de como acessaríamos a coleção de alunos
    # student = await db["students"].find_one({"_id": student_id})
    return {"message": f"Report generation requested for student ID: {student_id} using DB: {db.name}"}
