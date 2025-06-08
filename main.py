import logging

from config import ConfigurationManager
from lecture_manager import LectureManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

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