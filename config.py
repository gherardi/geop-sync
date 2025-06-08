import os
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

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