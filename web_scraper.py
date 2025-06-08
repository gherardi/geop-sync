import logging
from datetime import datetime, date
from typing import List, Optional
from contextlib import contextmanager

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

from config import ConfigurationManager
from models import LectureData, LectureScrapingError
from constants import DEFAULT_TIMEOUT, LECTURE_TAGS_TO_REMOVE

logger = logging.getLogger(__name__)

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