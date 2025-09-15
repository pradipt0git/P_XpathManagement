# selenium_actions.py
# This module contains the SeleniumActions class, which provides methods to interact with web elements using Selenium WebDriver.

# Import necessary modules and libraries
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import *
from modules.reporting_v2 import RobustReporting
import time
import os
import shutil

class SeleniumActions:
    
    def __init__(self, reporting: RobustReporting, driver: webdriver = None):
        """Initialize the SeleniumActions class."""
        self.reporting = reporting
        if(driver is not None):
            self.driver = driver
        else:
            self._init_driver()  # Initialize the WebDriver
        os.makedirs('Reports', exist_ok=True)  # Ensure the Reports directory exists

    def _init_driver(self):
        """Initialize WebDriver."""
        try:
            self.driver = webdriver.Chrome()  # Use Chrome WebDriver
            self.driver.maximize_window()  # Maximize the browser window
        except Exception as e:
            self.reporting.log_error(
                f"WebDriver initialization failed: {str(e)}")
            raise

    def open_url(self, url):
        """Open the specified URL in the browser."""
        try:
            self.driver.get(url)  # Navigate to the URL
            self.reporting.log_info(f"Opened URL: {url}")
            return True, None
        except Exception as e:
            full_error_message = f"Failed to open URL {url}: {str(e)}"
            brief_error_message = f"Failed to open URL {url}: {str(e).splitlines()[0]}"  # User-friendly error message
            self.reporting.log_error(full_error_message)
            return False, brief_error_message

    def set_value(self, xpath, value):
        """Set a value to an element identified by its XPath."""
        try:
            if not xpath:
                raise ValueError("XPath cannot be empty for set_value action")

            from selenium.webdriver.common.keys import Keys

            element = self._find_element(xpath)  # Locate the element
            element_type = element.get_attribute("type")
            element_type = element_type.lower() if element_type else None
            known_types = ["text", "email", "number", "password", "radio", "checkbox"]

            if element_type in ["text", "email", "number"]:
                element.clear()
                element.send_keys(value)
                element.send_keys("\t")  # Send TAB key after setting value
            elif element_type == "password":
                element.send_keys(value)
                element.send_keys("\t")  # Send TAB key after setting value
            elif element_type in ["radio", "checkbox"]:
                str_value = str(value).lower() if isinstance(value, bool) else str(value).lower()
                if str_value in ["true", "yes", "1"]:
                    if not element.is_selected():
                        element.click()
                else:
                    if element.is_selected():
                        element.click()
            elif element.tag_name.lower() == "select":
                from selenium.webdriver.support.ui import Select
                Select(element).select_by_visible_text(value)
            else:
                # For unknown or missing type, use select-all and delete before send_keys
                try:
                    element.send_keys(Keys.CONTROL, "a")
                    element.send_keys(Keys.DELETE)
                except Exception:
                    pass
                element.send_keys(value)

            self.reporting.log_info(f"Set value '{value}' to element: {xpath}")
            return True, None
        except Exception as e:
            error_message = f"Failed to set value: {str(e)}"
            self.reporting.log_error(error_message)
            return False, error_message

    def get_value(self, xpath):
        """Retrieve the value of an element identified by its XPath."""
        try:
            if not xpath:
                raise ValueError("XPath cannot be empty for get_value action")

            element = self._find_element(xpath)  # Locate the element

            # Handle different element types
            if element.tag_name.lower() in ["input", "textarea"]:
                value = element.get_attribute("value")
            elif element.tag_name.lower() == "select":
                from selenium.webdriver.support.ui import Select
                value = Select(element).first_selected_option.text
            else:
                value = element.text

            self.reporting.log_info(f"Got value '{value}' from element: {xpath}")
            return True, value
        except Exception as e:
            error_message = f"Failed to get value: {str(e)}"
            self.reporting.log_error(error_message)
            return False, error_message

    def assert_value(self, xpath, expected_value, field_code=None):
        """Assert that the value of an element matches the expected value."""
        try:
            if not xpath:
                raise ValueError("XPath cannot be empty for assert_value action")

            actual_value = self.get_value(xpath)[1]  # Extract value from tuple

            # Check if expected_value is a field code reference
            if field_code and expected_value in self.reporting.values_dict:
                expected_value = self.reporting.values_dict[expected_value]

            if str(actual_value) != str(expected_value):
                error_message = f"Assertion failed: Expected '{expected_value}', got '{actual_value}'"
                self.reporting.log_error(error_message)
                return False, error_message

            self.reporting.log_info(f"Assertion passed: {expected_value} == {actual_value}")
            return True, None
        except Exception as e:
            error_message = f"Assertion failed: {str(e)}"
            self.reporting.log_error(error_message)
            return False, error_message

    def _detect_selector_type(self, selector):
        """Detect if the selector is XPath or CSS selector."""
        # Heuristic: XPath usually starts with /, //, .//, ( or contains '@', '[', etc.
        selector = selector.strip()
        if selector.startswith('/') or selector.startswith('(') or selector.startswith('.//') or selector.startswith('//'):
            return 'xpath'
        # If it contains [@ or @, likely XPath
        if '[@' in selector or selector.startswith('..') or selector.startswith('('):
            return 'xpath'
        # Otherwise, treat as CSS
        return 'css'

    def _find_element(self, selector):
        """Find an element using XPath or CSS selector with robust error handling. Waits for presence and clickability."""
        by_type = self._detect_selector_type(selector)
        by = By.XPATH if by_type == 'xpath' else By.CSS_SELECTOR
        try:
            # Wait for the element to be present in the DOM
            element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((by, selector))
            )
            # Wait for the element to be clickable (if visible)
            try:
                element = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((by, selector))
                )
            except Exception:
                self.reporting.log_info(f"Element present but not clickable within 10s: {selector}")
            # Check if the element is visible
            if not element.is_displayed():
                self.reporting.log_info(f"Element found but not visible: {selector}")
                return element  # Return the element even if not visible
            # Scroll element into view if not visible
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", element)
            return element
        except TimeoutException:
            self.reporting.log_info(f"Element not found initially, attempting to scroll and locate: {selector}")

            # Detect the immediate scrollable parent container of the element (only for XPath)
            container = None
            if by == By.XPATH:
                detect_container_script = """
                    var element = document.evaluate(arguments[0], document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                    if (!element) return null;
                    var parent = element.parentElement;
                    while (parent) {
                        var overflowY = window.getComputedStyle(parent).overflowY;
                        if (overflowY === 'auto' || overflowY === 'scroll') {
                            return parent;
                        }
                        parent = parent.parentElement;
                    }
                    return null;
                """
                container = self.driver.execute_script(detect_container_script, selector)
                if not container:
                    self.reporting.log_info("No scrollable container found; defaulting to window scroll.")
                    container = None  # Default to window scroll
            scroll_script = """
                var container = arguments[0] || window;
                var scrollStep = arguments[1];
                var currentScroll = container.scrollTop || window.pageYOffset;
                var maxScroll = container.scrollHeight - container.clientHeight;
                if (currentScroll + scrollStep <= maxScroll) {
                    container.scrollBy(0, scrollStep);
                    return false; // Not at the end of scroll
                } else {
                    return true; // Reached the end of scroll
                }
            """
            scroll_step = 100  # Scroll by 100px at a time
            while True:
                at_end = self.driver.execute_script(scroll_script, container, scroll_step)
                try:
                    element = WebDriverWait(self.driver, 2).until(
                        EC.presence_of_element_located((by, selector))
                    )
                    self.reporting.log_info(f"Element found after scrolling: {selector}")
                    return element
                except TimeoutException:
                    pass  # Continue scrolling
                if at_end:
                    break  # Stop if reached the end of the scrollable area
            # if still not found then do not raise error, just return None
            return None
                   
            #raise Exception(f"Element not found after scrolling: {selector}")

    def quit(self):
        """Close the browser and clean up resources."""
        if self.driver:
            self.driver.quit()
        # Clean up backups after execution
        if os.path.exists('Backups'):
            shutil.rmtree('Backups')
        self.reporting.log_info("Browser closed and cleanup completed")

    def element_click(self, xpath):
        """Click on an element identified by its XPath."""
        try:
            element = self._find_element(xpath)  # Locate the element
            element.click()  # Perform the click action
            self.reporting.log_info(f"Clicked element: {xpath}")
            return True, None
        except Exception as e:
            full_error_message = f"Failed to click element {xpath}: {str(e)}"
            brief_error_message = f"Failed to click element {xpath}: {str(e).split(':')[0]}"  # User-friendly error message
            self.reporting.log_error(full_error_message)
            return False, brief_error_message

    def scroll_page(self, scroll_count=1, container_xpath=None):
        """Scroll the page or a specific container multiple times."""
        try:
            scroll_script = """
                var container = arguments[0] || window;
                var scrollCount = arguments[1];
                for (var i = 0; i < scrollCount; i++) {
                    container.scrollBy(0, container.scrollHeight/scrollCount);
                }
            """
            if container_xpath:
                container = self.driver.find_element(By.XPATH, container_xpath)
            else:
                container = None

            self.driver.execute_script(scroll_script, container, scroll_count)
            self.reporting.log_info(f"Scrolled {scroll_count} time(s) in {'container' if container_xpath else 'window'}")
            return True, None
        except Exception as e:
            error_message = f"Scroll failed: {str(e)}"
            self.reporting.log_error(error_message)
            return False, error_message

    def clear_text(self, xpath):
        """Clear the value of an element identified by its XPath."""
        try:
            if not xpath:
                raise ValueError("XPath cannot be empty for clear_text action")
            element = self._find_element(xpath)
            element.clear()
            self.reporting.log_info(f"Cleared text for element: {xpath}")
            return True, None
        except Exception as e:
            error_message = f"Failed to clear text: {str(e)}"
            self.reporting.log_error(error_message)
            return False, error_message

    def is_element_visible(self, xpath):
        """Check if an element identified by its XPath is visible on the page."""
        try:
            if not xpath:
                raise ValueError("XPath cannot be empty for is_element_visible action")
            element = self._find_element(xpath)
            visible = element.is_displayed()
            self.reporting.log_info(f"Element visibility for {xpath}: {visible}")
            return True, str(visible)
        except Exception as e:
            error_message = f"Failed to check element visibility: {str(e)}"
            self.reporting.log_error(error_message)
            return False, error_message
        
    def element_exists(self, xpath):
        """Check if an element exists for the given xpath. Returns (True, None) if found, (False, error_message) if not."""
        try:
            if not xpath:
                raise ValueError("XPath cannot be empty for element_exists action")
            by_type = self._detect_selector_type(xpath)
            by = By.XPATH if by_type == 'xpath' else By.CSS_SELECTOR
            elements = self.driver.find_elements(by, xpath)
            if elements and len(elements) > 0:
                self.reporting.log_info(f"Element exists: {xpath}")
                return True, None
            else:
                msg = f"Element does not exist: {xpath}"
                self.reporting.log_info(msg)
                return False, msg
        except Exception as e:
            error_message = f"Error in element_exists: {str(e)}"
            self.reporting.log_error(error_message)
            return False, error_message