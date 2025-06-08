import logging
from datetime import date
from typing import List
from supabase import create_client, Client

from config import ConfigurationManager
from models import LectureData, LectureScrapingError

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages database operations with Supabase"""
    
    def __init__(self, config: ConfigurationManager):
        self.config = config
        self._client = None
    
    @property
    def client(self) -> Client:
        """Lazy initialization of Supabase client"""
        if self._client is None:
            try:
                self._client = create_client(self.config.supabase_url, self.config.supabase_anon_key)
                logger.info("Supabase client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Supabase client: {str(e)}")
                raise LectureScrapingError(f"Database initialization failed: {str(e)}")
        return self._client
    
    def delete_future_lectures(self) -> bool:
        """Delete all lectures with dates greater than or equal to today"""
        try:
            today = date.today().isoformat()
            response = self.client.table("lectures").delete().gte("date", today).execute()
            logger.info(f"Deleted future lectures from database")
            return True
        except Exception as e:
            logger.error(f"Failed to delete future lectures: {str(e)}")
            return False
    
    def get_future_lectures(self) -> List[LectureData]:
        """Retrieve all future lectures from database"""
        try:
            today = date.today().isoformat()
            response = self.client.table("lectures").select("*").gte("date", today).execute()
            
            lectures = []
            for row in response.data:
                lecture = LectureData(
                    id=row.get('id'),
                    start_time=row['start_time'],
                    end_time=row['end_time'],
                    subject=row['subject'],
                    classroom=row['classroom'],
                    professor=row['professor'],
                    date=row['date'],
                    calendar_event_id=row.get('calendar_event_id')
                )
                lectures.append(lecture)
            
            logger.info(f"Retrieved {len(lectures)} future lectures from database")
            return lectures
        except Exception as e:
            logger.error(f"Failed to retrieve future lectures: {str(e)}")
            return []
    
    def save_lectures(self, lectures: List[LectureData]) -> bool:
        """Save lectures to database"""
        if not lectures:
            logger.warning("No lectures to save to database")
            return True
        
        try:
            # Convert lectures to dictionary format for database insertion
            lecture_dicts = []
            for lecture in lectures:
                lecture_dict = {
                    'start_time': lecture.start_time,
                    'end_time': lecture.end_time,
                    'subject': lecture.subject,
                    'classroom': lecture.classroom,
                    'professor': lecture.professor,
                    'date': lecture.date
                }
                lecture_dicts.append(lecture_dict)
            
            response = self.client.table("lectures").insert(lecture_dicts).execute()
            logger.info(f"Successfully saved {len(lectures)} lectures to database")
            return True
        except Exception as e:
            logger.error(f"Failed to save lectures to database: {str(e)}")
            return False
    
    def update_lecture_calendar_id(self, lecture_id: int, calendar_event_id: str) -> bool:
        """Update lecture with calendar event ID"""
        try:
            response = self.client.table("lectures").update({
                "calendar_event_id": calendar_event_id
            }).eq("id", lecture_id).execute()

            return True
        except Exception as e:
            logger.error(f"Failed to update lecture {lecture_id} with calendar ID: {str(e)}")
            return False