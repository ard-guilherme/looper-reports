from pydantic import BaseModel, Field
from typing import Dict, Any
from datetime import datetime

class StudentModel(BaseModel):
    id: str = Field(..., alias="_id")
    name: str
    email: str
    fitness_data: Dict[str, Any] = {}

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "_id": "60d5ec49f7e4e2a4e8f3b8a2",
                "name": "John Doe",
                "email": "john.doe@example.com",
                "fitness_data": {
                    "weight": 80,
                    "height": 180,
                    "workouts_last_week": 3
                }
            }
        }

class BioimpedanceModel(BaseModel):
    id: str = Field(..., alias="_id")
    student_id: str
    date: datetime
    data: Dict[str, Any]

class ReportModel(BaseModel):
    id: str = Field(..., alias="_id")
    student_id: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    html_content: str
