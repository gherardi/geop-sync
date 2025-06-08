import logging

from config import ConfigurationManager
from database_manager import DatabaseManager
from calendar_manager import CalendarManager
from web_scraper import WebScraper
from models import LectureScrapingError

logger = logging.getLogger(__name__)

class LectureManager:
    """Main orchestrator class that manages the entire lecture synchronization process"""
    
    def __init__(self):
        self.config = ConfigurationManager()
        self.db_manager = DatabaseManager(self.config)
        self.calendar_manager = CalendarManager(self.config)
        self.web_scraper = WebScraper(self.config)
    
    def sync_lectures(self) -> bool:
        """Execute the complete lecture synchronization process"""
        try:
            logger.info("Starting lecture synchronization process")
            
            # Step 1: Delete existing calendar events for future lectures
            self._cleanup_existing_data()
            
            # Step 2: Scrape new lectures from portal
            scraped_lectures = self.web_scraper.scrape_lectures()
            if not scraped_lectures:
                logger.warning("No future lectures found during scraping")
                return True
            
            # Step 3: Save scraped lectures to database
            if not self.db_manager.save_lectures(scraped_lectures):
                raise LectureScrapingError("Failed to save lectures to database")
            
            # Step 4: Create calendar events and update database with event IDs
            self._create_calendar_events()
            
            logger.info("Lecture synchronization completed successfully")
            return True
        except Exception as e:
            logger.error(f"Lecture synchronization failed: {str(e)}")
            return False
    
    def _cleanup_existing_data(self) -> None:
        """Clean up existing future lectures and calendar events"""
        logger.info("Cleaning up existing data")
        
        # Get future lectures to extract calendar event IDs
        future_lectures = self.db_manager.get_future_lectures()
        calendar_event_ids = [
            lecture.calendar_event_id 
            for lecture in future_lectures 
            if lecture.calendar_event_id
        ]
        
        # Delete calendar events
        if calendar_event_ids:
            self.calendar_manager.delete_events_by_ids(calendar_event_ids)
            logger.info(f"Deleted {len(calendar_event_ids)} calendar events")
        
        # Delete database records
        self.db_manager.delete_future_lectures()
    
    def _create_calendar_events(self) -> None:
        """Create calendar events for all future lectures"""
        logger.info("Creating calendar events")
        
        future_lectures = self.db_manager.get_future_lectures()
        successful_events = 0
        
        for lecture in future_lectures:
            event_id = self.calendar_manager.create_event(lecture)
            if event_id:
                if self.db_manager.update_lecture_calendar_id(lecture.id, event_id):
                    successful_events += 1
                else:
                    logger.warning(f"Failed to update lecture {lecture.id} with calendar event ID")
            else:
                logger.warning(f"Failed to create calendar event for lecture: {lecture.subject}")
        
        logger.info(f"Successfully created {successful_events}/{len(future_lectures)} calendar events")