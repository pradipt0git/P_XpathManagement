from selenium import webdriver
from selenium.webdriver.common.by import By
import json
import os
from modules.reporting_v2 import RobustReporting

rr = RobustReporting()

class XPathValidator:
    def __init__(self, json_file_path, existing_driver=None):
        self.json_file_path = json_file_path
        self.driver = existing_driver
        self.data = self._load_json()

    def _load_json(self):
        try:
            with open(self.json_file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            rr.log_error(f"Failed to load JSON for validation: {self.json_file_path} - {e}")
            raise

    def _setup_driver(self):
        # Use Edge driver from project 'drivers' folder to be consistent with capture
        from selenium.webdriver.edge.service import Service
        from selenium.webdriver.edge.options import Options
        PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
        DRIVER_FOLDER = os.path.join(PROJECT_ROOT, 'drivers')
        MS_EDGE_DRIVER = os.path.join(DRIVER_FOLDER, 'msedgedriver.exe')
        if not os.path.exists(MS_EDGE_DRIVER):
            rr.log_error(f"Edge WebDriver not found for validation at {MS_EDGE_DRIVER}")
            raise FileNotFoundError(f"Edge WebDriver not found at {MS_EDGE_DRIVER}")
        options = Options()
        options.add_argument('--disable-gpu')
        options.add_argument('--headless')  # Run in headless mode for validation
        service = Service(executable_path=MS_EDGE_DRIVER)
        try:
            return webdriver.Edge(service=service, options=options)
        except Exception as e:
            rr.log_error(f"Failed to create Edge WebDriver for validation: {e}")
            raise

    def validate_page_url(self, current_url):
        if not self.data:
            return False, "No data found in JSON file"
        
        expected_url = self.data[0].get('page_url', '')
        if not expected_url:
            return False, "No page URL found in JSON file"
            
        return expected_url == current_url, {
            'expected': expected_url,
            'current': current_url
        }

    def validate_all_xpaths(self):
        results = []
        need_driver = self.driver is None
        
        try:
            if need_driver:
                self.driver = self._setup_driver()
                # Navigate to page only if using new driver
                page_url = self.data[0].get('page_url', '')
                if not page_url:
                    rr.log_error('No page URL found in JSON when validating')
                    return False, "No page URL found"
                self.driver.get(page_url)
            
            # Get current URL for comparison
            current_url = self.driver.current_url
            expected_url = self.data[0].get('page_url', '')
            
            # URL validation
            if current_url != expected_url:
                rr.log_error(f"Page URL mismatch during validation: expected {expected_url}, got {current_url}")
                return False, {
                    'error': 'Page URL mismatch',
                    'current': current_url,
                    'expected': expected_url
                }
            
            # Rest of validation logic
            for item in self.data:
                xpath = item.get('selectors', {}).get('xpath', '')
                name = item.get('name', 'Unnamed Element')
                
                if not xpath:
                    results.append({
                        'name': name,
                        'valid': False,
                        'error': 'No XPath found'
                    })
                    continue
                
                try:
                    elements = self.driver.find_elements(By.XPATH, xpath)
                    results.append({
                        'name': name,
                        'xpath': xpath,
                        'valid': len(elements) == 1,
                        'count': len(elements)
                    })
                except Exception as e:
                    rr.log_error(f"Error validating xpath '{xpath}' for '{name}': {e}")
                    results.append({
                        'name': name,
                        'xpath': xpath,
                        'valid': False,
                        'error': str(e)
                    })
            
            return True, results
        except Exception as e:
            rr.log_error(f"Unexpected error during XPath validation: {e}")
            return False, str(e)
        finally:
            # Only quit driver if we created it
            if need_driver and self.driver:
                try:
                    self.driver.quit()
                except Exception as e:
                    rr.log_error(f"Error quitting validation driver: {e}")

def validate_json_file(json_path, existing_driver=None):
    """
    Validate XPaths in a JSON file using either existing or new driver
    Args:
        json_path: Path to JSON file
        existing_driver: Optional WebDriver instance from capture process
    """
    validator = XPathValidator(json_path, existing_driver)
    success, results = validator.validate_all_xpaths()
    return {
        'success': success,
        'results': results if success else {'error': results}
    }
