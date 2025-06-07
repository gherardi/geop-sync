import os
import logging
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from contextlib import contextmanager

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from supabase import create_client, Client
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Constants
DEFAULT_TIMEOUT = 10
MAX_RETRIES = 3
LECTURE_TAGS_TO_REMOVE = ["<br>", "[PRIMA LEZIONE]", "[ESAME]"]
GOOGLE_SCOPES = ['https://www.googleapis.com/auth/calendar']
TIMEZONE = "Europe/Rome"

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

class ConfigurationManager:
    """Manages environment configuration and validation"""
    
    def __init__(self):
        self.portal_url = os.environ.get("PORTAL_URL")
        self.user_email = os.environ.get("USER_EMAIL")
        self.user_password = os.environ.get("USER_PASSWORD")
        self.supabase_url = os.environ.get("SUPABASE_URL")
        self.supabase_anon_key = os.environ.get("SUPABASE_ANON_KEY")
        self.google_calendar_id = os.environ.get("GOOGLE_CALENDAR_ID")
        self.google_service_account_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
    
    def validate(self) -> bool:
        """Validate that all required environment variables are set"""
        required_vars = {
            'PORTAL_URL': self.portal_url,
            'USER_EMAIL': self.user_email,
            'USER_PASSWORD': self.user_password,
            'SUPABASE_URL': self.supabase_url,
            'SUPABASE_ANON_KEY': self.supabase_anon_key,
            'GOOGLE_CALENDAR_ID': self.google_calendar_id,
            'GOOGLE_SERVICE_ACCOUNT_FILE': self.google_service_account_file
        }
        
        missing_vars = [var_name for var_name, var_value in required_vars.items() if not var_value]
        
        if missing_vars:
            logger.error(f"Missing environment variables: {', '.join(missing_vars)}")
            return False
        
        logger.info("Environment configuration validated successfully")
        return True

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

class WebScraper:
    """Handles web scraping operations"""
    
    def __init__(self, config: ConfigurationManager):
        self.config = config
        self._driver = None
    
    @contextmanager
    def webdriver_context(self):
        """Context manager for WebDriver lifecycle"""
        driver = None
        try:
            driver = self._initialize_webdriver()
            if not driver:
                raise LectureScrapingError("Failed to initialize WebDriver")
            yield driver
        finally:
            if driver:
                try:
                    driver.quit()
                    logger.info("WebDriver closed successfully")
                except Exception as e:
                    logger.error(f"Error closing WebDriver: {str(e)}")
    
    def _initialize_webdriver(self) -> Optional[webdriver.Chrome]:
        """Initialize Chrome WebDriver with appropriate options"""
        try:
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            chrome_service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=chrome_service, options=chrome_options)
            
            logger.info("Chrome WebDriver initialized successfully")
            return driver
        except Exception as e:
            logger.error(f"Failed to initialize Chrome WebDriver: {str(e)}")
            return None
    
    def _wait_for_element(self, driver: webdriver.Chrome, locator_type: By, 
                         locator_value: str, timeout: int = DEFAULT_TIMEOUT) -> Optional[WebElement]:
        """Wait for an element to be present and return it"""
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((locator_type, locator_value))
            )
            return element
        except TimeoutException:
            logger.warning(f"Element not found within {timeout} seconds: {locator_type}={locator_value}")
            return None
    
    def _wait_for_elements(self, driver: webdriver.Chrome, locator_type: By, 
                          locator_value: str, timeout: int = DEFAULT_TIMEOUT) -> List[WebElement]:
        """Wait for elements to be present and return them"""
        try:
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((locator_type, locator_value))
            )
            return driver.find_elements(locator_type, locator_value)
        except TimeoutException:
            logger.warning(f"Elements not found within {timeout} seconds: {locator_type}={locator_value}")
            return []
    
    def _perform_login(self, driver: webdriver.Chrome) -> bool:
        """Handle the login process for the portal"""
        try:
            logger.info("Starting login process")
            driver.get(self.config.portal_url)
            
            login_form = self._wait_for_element(driver, By.ID, "frm_login")
            if not login_form:
                logger.error("Login form not found")
                return False
            
            username_field = driver.find_element(By.NAME, "username")
            password_field = driver.find_element(By.NAME, "password")
            
            username_field.clear()
            username_field.send_keys(self.config.user_email)
            password_field.clear()
            password_field.send_keys(self.config.user_password)
            
            login_form.submit()
            logger.info("Login credentials submitted successfully")
            return True
        except (NoSuchElementException, WebDriverException) as e:
            logger.error(f"Login failed: {str(e)}")
            return False
    
    def _extract_week_dates(self, driver: webdriver.Chrome) -> List[datetime]:
        """Extract dates for the current week from the calendar view"""
        try:
            current_year = datetime.now().year
            
            calendar_view = self._wait_for_element(driver, By.CLASS_NAME, "fc-view")
            if not calendar_view:
                logger.error("Calendar view not found")
                return []

            date_header_elements = self._wait_for_elements(driver, By.CLASS_NAME, "fc-day-header")
            if not date_header_elements:
                logger.warning("No date headers found for current week")
                return []

            week_dates = []
            for date_header_element in date_header_elements:
                try:
                    date_text = date_header_element.text.split(" ")[-1]
                    day_str, month_str = date_text.split("/")
                    
                    parsed_date = datetime(current_year, int(month_str), int(day_str))
                    week_dates.append(parsed_date)
                except (ValueError, IndexError) as e:
                    logger.warning(f"Could not parse date from element text '{date_header_element.text}': {str(e)}")
                    continue

            return week_dates
        except Exception as e:
            logger.error(f"Error extracting week dates: {str(e)}")
            return []
    
    def _extract_week_lectures(self, driver: webdriver.Chrome, week_dates: List[datetime]) -> List[LectureData]:
        """Extract all lectures for the given week dates"""
        try:
            lecture_containers = self._wait_for_elements(driver, By.CLASS_NAME, "fc-event-container")
            if not lecture_containers:
                logger.warning("No lecture containers found for current week")
                return []

            weekly_lectures = []
            
            for day_index, daily_container in enumerate(lecture_containers):
                if day_index >= len(week_dates):
                    logger.warning(f"More containers ({len(lecture_containers)}) than dates ({len(week_dates)})")
                    break
                    
                daily_lecture_elements = daily_container.find_elements(By.CSS_SELECTOR, ".fc-content")
                
                for lecture_element in daily_lecture_elements:
                    try:
                        parsed_lecture = self._parse_lecture_data(lecture_element)
                        if parsed_lecture is None:
                            continue

                        parsed_lecture.date = week_dates[day_index].strftime("%Y-%m-%d")
                        weekly_lectures.append(parsed_lecture)
                    except Exception:
                        logger.warning(f"Skipping unparseable lecture on day {day_index}")
                        continue

            return weekly_lectures
        except Exception as e:
            logger.error(f"Error extracting week lectures: {str(e)}")
            return []
    
    def _parse_lecture_data(self, lecture_element: WebElement) -> Optional[LectureData]:
        """Parse lecture information from a web element"""
        try:
            raw_lecture_text = lecture_element.text.replace("\n", " - ")
            cleaned_lecture_text = self._clean_text_content(raw_lecture_text, ["<br>"])
            
            if len(cleaned_lecture_text) < 16:
                logger.warning(f"Lecture text too short to parse: '{cleaned_lecture_text}'")
                return None
            
            # Extract time information (first 13 characters)
            time_segment = cleaned_lecture_text[:13]
            try:
                start_time, end_time = time_segment.split(" - ")
            except ValueError:
                logger.warning(f"Could not parse time segment: '{time_segment}'")
                return None
            
            # Extract lecture information (from character 16 onwards)
            lecture_info_segment = cleaned_lecture_text[16:]
            
            if " - Aula: " not in lecture_info_segment:
                logger.warning(f"No classroom information found in: '{lecture_info_segment}'")
                return None
                
            subject_and_professor, classroom = lecture_info_segment.split(" - Aula: ", 1)
            
            # Extract professor (last part after splitting by ' - ')
            subject_parts = subject_and_professor.split(' - ')
            if len(subject_parts) < 2:
                logger.warning(f"Could not extract professor from: '{subject_and_professor}'")
                return None
                
            # raw_professor = subject_parts[-1]
            raw_subject = ' - '.join(subject_parts[:-1])
            raw_professor = subject_parts[-1]
            
            # Clean subject and professor names
            cleaned_subject = self._clean_text_content(raw_subject, LECTURE_TAGS_TO_REMOVE)
            cleaned_professor = self._clean_text_content(raw_professor, LECTURE_TAGS_TO_REMOVE)
            
            lecture_data = LectureData(
                start_time=start_time.strip(),
                end_time=end_time.strip(),
                subject=cleaned_subject,
                classroom=classroom.strip(),
                professor=cleaned_professor,
                date=""  # Will be set by caller
            )
            
            logger.debug(f"Successfully parsed lecture: {lecture_data.subject} at {lecture_data.start_time}")
            return lecture_data
        except Exception as e:
            logger.error(f"Error parsing lecture element: {str(e)}")
            return None
    
    def _clean_text_content(self, text: str, tags_to_remove: List[str]) -> str:
        """Remove specified tags from text and clean whitespace"""
        cleaned_text = text
        for tag in tags_to_remove:
            cleaned_text = cleaned_text.replace(tag, "")
        return cleaned_text.strip()
    
    def _navigate_to_next_week(self, driver: webdriver.Chrome) -> bool:
        """Navigate to the next week in the calendar"""
        try:
            next_week_button = self._wait_for_element(driver, By.CLASS_NAME, "fc-next-button")
            if not next_week_button:
                logger.error("Next week button not found")
                return False
                
            next_week_button.click()
            logger.debug("Successfully navigated to next week")
            return True
        except Exception as e:
            logger.error(f"Error navigating to next week: {str(e)}")
            return False
    
    def _check_if_past_current_month(self, driver: webdriver.Chrome) -> bool:
        """Check if we've navigated past the current month"""
        try:
            month_title_element = self._wait_for_element(driver, By.TAG_NAME, "h2")
            if not month_title_element:
                logger.warning("Could not find month title element")
                return False
                
            month_title = month_title_element.text
            is_past_month = "ago" in month_title.lower()
            
            if is_past_month:
                logger.info(f"Reached past month: {month_title}")
            
            return is_past_month
        except Exception as e:
            logger.error(f"Error checking month title: {str(e)}")
            return False
    
    def scrape_lectures(self) -> List[LectureData]:
        """Main scraping function that coordinates the entire process"""
        with self.webdriver_context() as driver:
            if not self._perform_login(driver):
                raise LectureScrapingError("Login failed")
            
            if not self._wait_for_element(driver, By.CLASS_NAME, "fc-next-button"):
                raise LectureScrapingError("Calendar navigation not available")
            
            all_lectures = []
            week_count = 0
            
            while True:
                week_count += 1
                
                current_week_dates = self._extract_week_dates(driver)
                if not current_week_dates:
                    logger.error(f"Could not extract dates for week {week_count}")
                    break
                
                current_week_lectures = self._extract_week_lectures(driver, current_week_dates)
                all_lectures.extend(current_week_lectures)
                
                if not self._navigate_to_next_week(driver):
                    logger.error("Could not navigate to next week")
                    break
                
                if self._check_if_past_current_month(driver):
                    logger.info("Reached past month, stopping scraping")
                    break
            
            # Filter lectures to only include future ones
            today = date.today().isoformat()
            future_lectures = [lecture for lecture in all_lectures if lecture.date >= today]
            
            logger.info(f"Scraping completed. Total lectures: {len(all_lectures)}, Future lectures: {len(future_lectures)}")
            return future_lectures

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

def main():
    """Main entry point of the script"""
    logger.info("Starting lecture management script")
    
    try:
        # Initialize and validate configuration
        config = ConfigurationManager()
        if not config.validate():
            logger.error("Configuration validation failed")
            exit(1)
        
        # Execute lecture synchronization
        lecture_manager = LectureManager()
        success = lecture_manager.sync_lectures()
        
        if success:
            logger.info("Script completed successfully")
            exit(0)
        else:
            logger.error("Script completed with errors")
            exit(1)
            
    except KeyboardInterrupt:
        logger.info("Script interrupted by user")
        exit(0)
    except Exception as e:
        logger.error(f"Unexpected error in main: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main()