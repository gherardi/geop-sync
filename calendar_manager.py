import logging
from typing import List, Optional
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from config import ConfigurationManager
from models import LectureData, LectureScrapingError
from constants import GOOGLE_SCOPES, TIMEZONE

logger = logging.getLogger(__name__)

class CalendarManager:
    """Manages Google Calendar operations"""
    
    def __init__(self, config: ConfigurationManager):
        self.config = config
        self._service = None
    
    @property
    def service(self):
        """Lazy initialization of Google Calendar service"""
        if self._service is None:
            try:
                credentials = Credentials.from_service_account_file(
                    self.config.google_service_account_file,
                    scopes=GOOGLE_SCOPES
                )
                self._service = build("calendar", "v3", credentials=credentials)
                logger.info("Google Calendar service initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Google Calendar service: {str(e)}")
                raise LectureScrapingError(f"Calendar initialization failed: {str(e)}")
        return self._service
    
    def delete_events_by_ids(self, event_ids: List[str]) -> None:
        """Delete calendar events by their IDs"""
        for event_id in event_ids:
            try:
                self.service.events().delete(
                    calendarId=self.config.google_calendar_id,
                    eventId=event_id
                ).execute()
                logger.debug(f"Deleted calendar event: {event_id}")
            except Exception as e:
                logger.warning(f"Failed to delete calendar event {event_id}: {str(e)}")
    
    def create_event(self, lecture: LectureData) -> Optional[str]:
        """Create a calendar event for a lecture and return the event ID"""
        try:
            start_datetime = f"{lecture.date}T{self._format_time(lecture.start_time)}+02:00"
            end_datetime = f"{lecture.date}T{self._format_time(lecture.end_time)}+02:00"
            
            event = {
                "summary": lecture.subject,
                "description": lecture.professor,
                "start": {
                    "dateTime": start_datetime,
                    "timeZone": TIMEZONE
                },
                "end": {
                    "dateTime": end_datetime,
                    "timeZone": TIMEZONE
                },
                "location": lecture.classroom
            }
            
            created_event = self.service.events().insert(
                calendarId=self.config.google_calendar_id,
                body=event
            ).execute()
            
            event_id = created_event.get('id')
            logger.debug(f"Created calendar event: {event_id} for {lecture.subject}")
            return event_id
        except Exception as e:
            logger.error(f"Failed to create calendar event for {lecture.subject}: {str(e)}")
            return None
    
    def _format_time(self, time_str: str) -> str:
        """Ensure time string is in HH:MM:SS format"""
        if len(time_str.split(':')) == 2:
            return f"{time_str}:00"
        return time_str