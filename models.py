from dataclasses import dataclass
from typing import Optional

@dataclass
class LectureData:
    """Data class representing a lecture"""
    subject: str
    date: str
    end_time: str
    start_time: str
    classroom: str
    professor: str
    calendar_event_id: Optional[str] = None
    id: Optional[int] = None

class LectureScrapingError(Exception):
    """Custom exception for lecture scraping errors"""
    pass