import logging
from datetime import datetime
import os
from selenium import webdriver
from tempfile import NamedTemporaryFile
from string import Template

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))

class RobustReporting:
    def __init__(self):
        self.values_dict = {}
        self._init_logging()
        os.makedirs(os.path.join(PROJECT_ROOT, 'Reports'), exist_ok=True)        

    def _init_logging(self):
        """Initialize enhanced logging system"""
        log_dir = os.path.join(PROJECT_ROOT, 'Logs')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(
            log_dir, f"execution_{datetime.now().strftime('%Y%m%d')}.log")

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger('robust_reporting')


    def log_info(self, message):
        """Log informational message"""
        self.logger.info(message)

    def log_error(self, message):
        """Log error message"""
        self.logger.error(message)

