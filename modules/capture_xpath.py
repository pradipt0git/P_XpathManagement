import os
import json
import time
import keyboard
from selenium import webdriver
from selenium.webdriver.common.by import By

from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.common.exceptions import WebDriverException

from modules.reporting_v2 import RobustReporting

# Initialize reporter
rr = RobustReporting()

# Path to EdgeDriver (Edge only) - driver located in project 'driver' folder
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DRIVER_FOLDER = os.path.join(PROJECT_ROOT, 'drivers')
MS_EDGE_DRIVER = os.path.join(DRIVER_FOLDER, 'msedgedriver.exe')  # adjust if needed

# Predefined URL
default_url = 'https://www.google.com'  # fallback

# JSON and CSV output files (inside captured_xpaths folder)
captured_folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'captured_xpaths')
os.makedirs(captured_folder, exist_ok=True)
selectors_csv = os.path.join(captured_folder, 'element_selectors.csv')
selectors_json = os.path.join(captured_folder, 'element_selectors.json')

def close_all_browsers():
    # Only close msedgedriver-controlled browsers
    driver_name = 'msedgedriver.exe'
    try:
        os.system(f'taskkill /F /IM {driver_name} >nul 2>&1')
        time.sleep(1)
    except Exception as e:
        rr.log_error(f"close_all_browsers error: {e}")

def open_browser(url):
    # Always use Microsoft Edge from project driver folder; do not fallback to other browsers or system PATH
    try:
        options = Options()
        # Useful options to reduce interference
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        # Require explicit driver path in project driver folder
        if not os.path.exists(MS_EDGE_DRIVER):
            raise FileNotFoundError(f"Edge WebDriver not found at {MS_EDGE_DRIVER}. Please place msedgedriver.exe in the project's driver folder.")
        service = Service(executable_path=MS_EDGE_DRIVER)
        driver = webdriver.Edge(service=service, options=options)
        driver.get(url)
        return driver
    except WebDriverException as e:
        rr.log_error(f"Failed to start Edge browser: {e.msg if hasattr(e, 'msg') else str(e)}")
        raise
    except Exception as e:
        rr.log_error(f"open_browser unexpected error: {e}")
        raise

def get_element_details(driver, element):
    # Determine the 'name' field for the JSON object
    name_val = element.get_attribute('name')
    if name_val:
        details = {'name': name_val}
    else:
        text_val = element.text
        if text_val:
            details = {'name': text_val}
        else:
            title_val = element.get_attribute('title')
            if title_val:
                details = {'name': title_val}
            else:
                placeholder_val = element.get_attribute('placeholder')
                if placeholder_val:
                    details = {'name': placeholder_val}
                else:
                    details = {'name': ''}
    try:
        # Properties
        props = {}
        props['ariaLabel'] = element.get_attribute('aria-label')
        props['className'] = element.get_attribute('class')
        props['href'] = element.get_attribute('href')
        props['id'] = element.get_attribute('id')
        props['name'] = element.get_attribute('name')
        props['role'] = element.get_attribute('role')
        props['tag'] = element.tag_name.upper()
        props['text'] = element.text
        props['title'] = element.get_attribute('title')
        props['type'] = element.get_attribute('type')
        props['value'] = element.get_attribute('value')
        # Get bounding rect
        rect = driver.execute_script('var r=arguments[0].getBoundingClientRect(); return {x:r.x, y:r.y, top:r.top, left:r.left, bottom:r.bottom, right:r.right, width:r.width, height:r.height};', element)
        props['rect'] = rect
        # Center point
        props['x'] = rect['x'] + rect['width']/2 if rect else None
        props['y'] = rect['y'] + rect['height']/2 if rect else None
        details['properties'] = props

        # Selectors
        selectors = {}
        class_name = props['className']
        tag = element.tag_name
        selectors['Class Name'] = class_name
        if class_name:
            first_class = class_name.split()[0]
            selectors['CSS Selector (Class)'] = f'.{first_class}'
            selectors['XPath (Class)'] = f"//*[contains(@class, '{first_class}')]"
            selectors['CSS Selector (Combined)'] = f"{tag}.{'.'.join(class_name.split())}"
            selectors['XPath (Combined)'] = f"//{tag}[contains(@class, '{first_class}')]"
        else:
            selectors['CSS Selector (Class)'] = None
            selectors['XPath (Class)'] = None
            selectors['CSS Selector (Combined)'] = None
            selectors['XPath (Combined)'] = None
        # Add id, name, etc. selectors if present
        if props['id']:
            selectors['CSS Selector (ID)'] = f"#{props['id']}"
            selectors['XPath (ID)'] = f"//*[@id='{props['id']}']"
        if props['name']:
            selectors['CSS Selector (Name)'] = f"{tag}[name='{props['name']}']"
            selectors['XPath (Name)'] = f"//{tag}[@name='{props['name']}']"
        # Add generic
        selectors['Tag'] = tag

        # --- CSS Selector Validation ---
        css_keys = [
            'CSS Selector (Class)',
            'CSS Selector (Combined)',
            'CSS Selector (ID)',
            'CSS Selector (Name)'
        ]
        found_element_counts = {}
        for css_key in css_keys:
            css_val = selectors.get(css_key, None)
            if css_val:
                try:
                    found = driver.find_elements(By.CSS_SELECTOR, css_val)
                    count = len(found)
                    if count > 0:
                        selectors[css_key] = css_val
                        found_element_counts[css_key] = count
                    else:
                        selectors.pop(css_key, None)
                except Exception:
                    selectors.pop(css_key, None)
            else:
                selectors.pop(css_key, None)

        # Add full XPath and most relative XPath using browser's developer tools logic
        # Full XPath (absolute):
        full_xpath = driver.execute_script('''
            function getElementXPath(elt) {
                var path = '';
                for (; elt && elt.nodeType == 1; elt = elt.parentNode) {
                    idx = 1;
                    for (var sib = elt.previousSibling; sib; sib = sib.previousSibling) {
                        if (sib.nodeType == 1 && sib.nodeName == elt.nodeName) idx++;
                    }
                    var xname = elt.nodeName.toLowerCase();
                    path = '/' + xname + '[' + idx + ']' + path;
                }
                return path;
            }
            return getElementXPath(arguments[0]);
        ''', element)
        if full_xpath and '"' in full_xpath:
            full_xpath = full_xpath.replace('"', "'")
        # Only add if it actually detects exactly one element
        try:
            found = driver.find_elements(By.XPATH, full_xpath)
            count = len(found)
            if count > 0:
                selectors['Full XPath'] = full_xpath
                found_element_counts['Full XPath'] = count
            else:
                selectors.pop('Full XPath', None)
        except Exception:
            selectors.pop('Full XPath', None)

        # Most relative XPath (copy as relative from devtools):
        # This is usually the shortest unique XPath from the element to the root with id if available
        relative_xpath = driver.execute_script('''
            function getRelativeXPath(elt) {
                if (elt.id !== '') {
                    return "//*[@id='" + elt.id + "']";
                }
                var path = '';
                for (; elt && elt.nodeType == 1; elt = elt.parentNode) {
                    var sibCount = 0;
                    var sibIndex = 0;
                    for (var sib = elt.parentNode ? elt.parentNode.firstChild : null; sib; sib = sib.nextSibling) {
                        if (sib.nodeType == 1 && sib.nodeName == elt.nodeName) {
                            sibCount++;
                            if (sib === elt) sibIndex = sibCount;
                        }
                    }
                    var xname = elt.nodeName.toLowerCase();
                    var segment = xname + (sibCount > 1 ? '[' + sibIndex + ']' : '');
                    path = '/' + segment + path;
                    if (elt.parentNode && elt.parentNode.nodeType == 1 && elt.parentNode.id) {
                        path = "//*[@id='" + elt.parentNode.id + "']" + path;
                        break;
                    }
                }
                return path;
            }
            return getRelativeXPath(arguments[0]);
        ''', element)
        if relative_xpath and '"' in relative_xpath:
            relative_xpath = relative_xpath.replace('"', "'")
        # Only add if it actually detects exactly one element
        try:
            found = driver.find_elements(By.XPATH, relative_xpath)
            count = len(found)
            if count > 0:
                selectors['Relative XPath'] = relative_xpath
                found_element_counts['Relative XPath'] = count
            else:
                selectors.pop('Relative XPath', None)
        except Exception:
            selectors.pop('Relative XPath', None)

        # Add smart/shortest unique XPath (like DevTools) as accu_xpath
        accu_xpath = None
        try:
            accu_xpath = driver.execute_script(r'''
                function getSmartXPath(element) {
                    if (!element) return '';
                    // Prefer id if unique
                    if (element.id && document.querySelectorAll('#' + CSS.escape(element.id)).length === 1) {
                        return '//*[@id="' + element.id + '"]';
                    }
                    // Prefer name if unique
                    if (element.name && document.querySelectorAll('[name="' + CSS.escape(element.name) + '"]').length === 1) {
                        return '//' + element.tagName.toLowerCase() + '[@name="' + element.name + '"]';
                    }
                    // Prefer class if unique
                    if (element.className && typeof element.className === 'string') {
                        var classes = element.className.trim().split(/\s+/);
                        for (var i = 0; i < classes.length; i++) {
                            var cls = classes[i];
                            if (cls && document.querySelectorAll('.' + CSS.escape(cls)).length === 1) {
                                return '//' + element.tagName.toLowerCase() + '[contains(@class, "' + cls + '")]';
                            }
                        }
                    }
                    // Otherwise, build a unique path up the tree
                    var path = [];
                    while (element && element.nodeType === 1 && element !== document.body) {
                        var tag = element.tagName.toLowerCase();
                        var siblings = element.parentNode ? Array.from(element.parentNode.children).filter(function(e) { return e.tagName === element.tagName; }) : [];
                        if (siblings.length > 1) {
                            var idx = siblings.indexOf(element) + 1;
                            path.unshift(tag + '[' + idx + ']');
                        } else {
                            path.unshift(tag);
                        }
                        element = element.parentNode;
                    }
                    return '//' + path.join('/');
                }
                return getSmartXPath(window.clickedElement);
            ''')
        except Exception:
            accu_xpath = None
        # Only add if it actually detects an element
        if accu_xpath:
            # Always use single quotes in accu_xpath
            if '"' in accu_xpath:
                accu_xpath = accu_xpath.replace('"', "'")
            try:
                found = driver.find_elements(By.XPATH, accu_xpath)
                count = len(found)
                if count > 0:
                    selectors['accu_xpath'] = accu_xpath
                    found_element_counts['accu_xpath'] = count
                else:
                    selectors.pop('accu_xpath', None)
            except Exception:
                selectors.pop('accu_xpath', None)
        else:
            selectors.pop('accu_xpath', None)

        # Add visible_property_xpath: prefer text, then aria-label, then value
        visible_property_xpath = None
        text_val = props.get('text', '')
        aria_label_val = props.get('ariaLabel', '')
        value_val = props.get('value', '')
        tag = element.tag_name
        if text_val:
            tag_lc = tag.lower() if tag else ''
            text_val_lc = text_val.strip().lower() if text_val else ''
            candidate = f"//{tag_lc}[translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='{text_val_lc}']"
            try:
                found = driver.find_elements(By.XPATH, candidate)
                count = len(found)
                if count > 0:
                    selectors['visible_property_xpath'] = candidate
                    selectors['xpath'] = candidate  # Add 'xpath' property after 'visible_property_xpath'
                    found_element_counts['visible_property_xpath'] = count
                else:
                    selectors.pop('visible_property_xpath', None)
                    selectors.pop('xpath', None)
            except Exception:
                selectors.pop('visible_property_xpath', None)
                selectors.pop('xpath', None)
        elif aria_label_val:
            tag_lc = tag.lower() if tag else ''
            aria_label_lc = aria_label_val.strip().lower() if aria_label_val else ''
            candidate = (
                f"//{tag_lc}[translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')="
                f"'{aria_label_lc}']"
            )
            try:
                found = driver.find_elements(By.XPATH, candidate)
                count = len(found)
                if count > 0:
                    selectors['visible_property_xpath'] = candidate
                    selectors['xpath'] = candidate  # Add 'xpath' property after 'visible_property_xpath'
                    found_element_counts['visible_property_xpath'] = count
                else:
                    selectors.pop('visible_property_xpath', None)
                    selectors.pop('xpath', None)
            except Exception:
                selectors.pop('visible_property_xpath', None)
                selectors.pop('xpath', None)
        elif element.get_attribute('placeholder'):
            tag_lc = tag.lower() if tag else ''
            placeholder_val = element.get_attribute('placeholder')
            placeholder_lc = placeholder_val.strip().lower() if placeholder_val else ''
            candidate = (
                f"//{tag_lc}[translate(@placeholder, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')="
                f"'{placeholder_lc}']"
            )
            try:
                found = driver.find_elements(By.XPATH, candidate)
                count = len(found)
                if count > 0:
                    selectors['visible_property_xpath'] = candidate
                    selectors['xpath'] = candidate  # Add 'xpath' property after 'visible_property_xpath'
                    found_element_counts['visible_property_xpath'] = count
                else:
                    selectors.pop('visible_property_xpath', None)
                    selectors.pop('xpath', None)
            except Exception:
                selectors.pop('visible_property_xpath', None)
                selectors.pop('xpath', None)
        elif value_val:
            tag_lc = tag.lower() if tag else ''
            value_lc = value_val.strip().lower() if value_val else ''
            candidate = (
                f"//{tag_lc}[translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')="
                f"'{value_lc}']"
            )
            try:
                found = driver.find_elements(By.XPATH, candidate)
                count = len(found)
                if count > 0:
                    selectors['visible_property_xpath'] = candidate
                    selectors['xpath'] = candidate  # Add 'xpath' property after 'visible_property_xpath'
                    found_element_counts['visible_property_xpath'] = count
                else:
                    selectors.pop('visible_property_xpath', None)
                    selectors.pop('xpath', None)
            except Exception:
                selectors.pop('visible_property_xpath', None)
                selectors.pop('xpath', None)
        else:
            selectors.pop('visible_property_xpath', None)
            selectors.pop('xpath', None)
        details['selectors'] = selectors
        details['found_element_counts'] = found_element_counts
    except Exception as e:
        details['error'] = str(e)
        rr.log_error(f"get_element_details error: {e}")
    return details

def get_xpath(element):
    # Selenium 4+ has get_dom_attribute, but for compatibility, build xpath manually
    path = ''
    while element is not None:
        parent = element.find_element(By.XPATH, '..') if element.tag_name != 'html' else None
        siblings = []
        if parent:
            siblings = parent.find_elements(By.XPATH, f'./{element.tag_name}')
        idx = siblings.index(element) + 1 if siblings else 1
        path = f'/{element.tag_name}[{idx}]' + path
        element = parent
    return path

def get_css_selector(element):
    selector = element.tag_name
    if element.get_attribute('id'):
        selector += f"#{element.get_attribute('id')}"
    elif element.get_attribute('class'):
        selector += '.' + '.'.join(element.get_attribute('class').split())
    return selector

def enable_capture_js(driver):
    js = '''
    if (!window._captureHandler) {
        window._captureModeActive = true;
        window._f9Pressed = false;
        window.addEventListener('keydown', function(e) {
            if (e.key === 'F9') window._f9Pressed = true;
        }, true);
        window.addEventListener('keyup', function(e) {
            if (e.key === 'F9') window._f9Pressed = false;
        }, true);
        window._captureHandler = function(e) {
            if (window._captureModeActive && window._f9Pressed) {
                e.preventDefault();
                e.stopPropagation();
                window.clickedElement = e.target;
            }
        };
        document.body.addEventListener('click', window._captureHandler, true);
        // Prevent all key and mouse events from propagating and triggering default actions only if capture mode is active and F9 is pressed
        window._captureKeyHandler = function(e) {
            if (window._captureModeActive && window._f9Pressed) {
                e.preventDefault();
                e.stopPropagation();
            }
        };
        var events = ['keydown','keyup','keypress','mousedown','mouseup','dblclick','contextmenu'];
        for (var i = 0; i < events.length; i++) {
            document.body.addEventListener(events[i], window._captureKeyHandler, true);
        }
    } else {
        window._captureModeActive = true;
    }
    '''
    driver.execute_script(js)

def disable_capture_js(driver):
    js = '''
    if (window._captureHandler) {
        window._captureModeActive = false;
    }
    '''
    driver.execute_script(js)

def capture_elements(driver, selectors_list):
    # Check for clicked element and append selectors
    import csv
    clicked = driver.execute_script('return window.clickedElement || null;')
    if not clicked:
        print('No element clicked. Nothing to capture.')
        return
    elem = driver.execute_script('return window.clickedElement;')
    # Use the actual clicked element for get_element_details
    details = get_element_details(driver, elem)
    # Add current page URL and title to details
    page_url = driver.current_url
    page_title = driver.title if hasattr(driver, 'title') else ''
    details['page_url'] = page_url
    details['page_title'] = page_title
    details['page_name'] = page_title or page_url
    print('Element details:', details)

    # --- CSV: Only append selectors with exactly one match ---
    name = details['properties'].get('name', '')
    value = details['properties'].get('value', '')
    typ = details['properties'].get('type', '')
    text = details['properties'].get('text', '')
    if text and len(text) > 40:
        text = text[:40]
    selectors = details['selectors']
    found_element_counts = details.get('found_element_counts', {})
    # XPaths
    full_xpath = selectors.get('Full XPath', '') if found_element_counts.get('Full XPath', 0) == 1 else ''
    relative_xpath = selectors.get('Relative XPath', '') if found_element_counts.get('Relative XPath', 0) == 1 else ''
    # Extra xpaths
    extra_xpaths = {}
    for key in ['accu_xpath', 'visible_property_xpath']:
        xpath_val = selectors.get(key, None)
        found_count = found_element_counts.get(key, 0)
        if xpath_val and found_count == 1:
            extra_xpaths[key] = xpath_val
    # CSS selectors with exactly one match
    css_keys = [
        'CSS Selector (Class)',
        'CSS Selector (Combined)',
        'CSS Selector (ID)',
        'CSS Selector (Name)'
    ]
    css_selectors = {}
    for css_key in css_keys:
        css_val = selectors.get(css_key, None)
        found_count = found_element_counts.get(css_key, 0)
        if css_val and found_count == 1:
            css_selectors[css_key] = css_val

    # Prepare CSV columns
    base_columns = ['page_url', 'name', 'value', 'type', 'text', 'full_xpath', 'relative_xpath']
    extra_columns = list(extra_xpaths.keys())
    css_columns = list(css_selectors.keys())
    row = [page_url, name, value, typ, text, full_xpath, relative_xpath]
    for col in extra_columns:
        row.append(extra_xpaths[col])
    for col in css_columns:
        row.append(css_selectors[col])
    write_header = not os.path.exists(selectors_csv)
    with open(selectors_csv, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(base_columns + extra_columns + css_columns)
        writer.writerow(row)
    print(f'Details appended to {selectors_csv}')
    # Add found element count flag to selectors_list
    # Only keep found_element_counts for selectors with count > 0
    details['found_element_counts'] = {k: v for k, v in found_element_counts.items() if v > 0}

    # --- PAGE-WISE JSON: Save per page, append only if not duplicate ---
    import re
    def sanitize_filename(name):
        # Replace non-alphanum with _
        fname = re.sub(r'[^a-zA-Z0-9]+', '_', name)
        return fname[:80]  # Limit length

    page_name = details.get('page_name', '')
    safe_page_name = sanitize_filename(page_name) if page_name else sanitize_filename(page_url)
    page_json = os.path.join(captured_folder, f"obj_{safe_page_name}.json")
    # Load existing data for this page
    existing_data = []
    if os.path.exists(page_json):
        try:
            with open(page_json, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
        except Exception as e:
            rr.log_error(f"Failed to read existing page json {page_json}: {e}")
            existing_data = []
    # Check for duplicate: use full_xpath as unique key
    
    # Ensure new_full_xpath is defined
    new_full_xpath = details.get('selectors', {}).get('Full XPath', '')

    is_duplicate = False
    for d in existing_data:
        existing_xpath = d.get('selectors', {}).get('Full XPath', '')
        if (existing_xpath or '').lower() == (new_full_xpath or '').lower():
            is_duplicate = True
            break
    if not is_duplicate:
        try:
            existing_data.append(details)
            with open(page_json, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, indent=2, ensure_ascii=False)
            rr.log_info(f'Details appended to {page_json}')
            print(f'Details appended to {page_json}')
        except Exception as e:
            rr.log_error(f"Failed to append details to {page_json}: {e}")
    else:
        rr.log_info(f"Element already present in {page_json}, not appending.")
        print(f"Element already present in {page_json}, not appending.")
    # Reset clickedElement so user can click again
    try:
        driver.execute_script('window.clickedElement = null;')
    except Exception as e:
        rr.log_error(f"Error resetting clickedElement: {e}")

# Read URL from config file
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'capture_xpath_config.json')
def get_config_url():
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config.get('url', default_url)
    except Exception:
        return default_url

def main():
    close_all_browsers()
    url = get_config_url()
    driver = open_browser(url)
    print('Press F9 to toggle capture mode (on/off). Click elements to capture selectors. Press F9 again to stop. Repeat as needed. Press Ctrl+C in terminal to exit.')
    selectors_list = []
    capture_mode_enabled = False
    from selenium.common.exceptions import NoSuchWindowException
    try:
        print('Hold Windows + F9 to enable capture mode. Release to disable. Press Ctrl+C in terminal to exit.')
        while True:
            try:
                fn_pressed = keyboard.is_pressed('F9')
                if fn_pressed:
                    if not capture_mode_enabled:
                        capture_mode_enabled = True
                        print('Capture mode enabled.')
                        enable_capture_js(driver)
                else:
                    if capture_mode_enabled:
                        capture_mode_enabled = False
                        print('Capture mode disabled.')
                        disable_capture_js(driver)
                if capture_mode_enabled:
                    capture_elements(driver, selectors_list)
                time.sleep(0.1)
            except NoSuchWindowException:
                rr.log_error('Browser window was closed. Exiting loop.')
                print('Browser window was closed. Exiting loop.')
                break
    except KeyboardInterrupt:
        print('Exiting...')
    finally:
        try:
            disable_capture_js(driver)
        except Exception as e:
            rr.log_error(f"Error disabling capture JS in finally: {e}")
        try:
            driver.quit()
        except Exception as e:
            rr.log_error(f"Error quitting driver in finally: {e}")

if __name__ == '__main__':
    main()
