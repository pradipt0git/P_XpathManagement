import os
import json
import subprocess
from flask import Flask, render_template_string, request, jsonify
import signal
from pathlib import Path
import psutil

from modules.validate_xpath import validate_json_file
from modules.reporting_v2 import RobustReporting

# Initialize reporting
rr = RobustReporting()

app = Flask(__name__)

CAPTURED_XPATHS_DIR = os.path.join(os.path.dirname(__file__), 'captured_xpaths')
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), 'config', 'xpath_ui_template.html')

def load_template():
    # Robustly load template; fallback to a minimal inline template if missing
    try:
        if not os.path.exists(TEMPLATE_PATH):
            rr.log_error(f"Template not found at {TEMPLATE_PATH}")
            return "<!doctype html><html><head><meta charset='utf-8'><title>XPath UI</title></head><body><h1>XPath UI</h1><div id='app'></div></body></html>"
        with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        rr.log_error(f"Failed to load template {TEMPLATE_PATH}: {e}")
        return "<!doctype html><html><head><meta charset='utf-8'><title>XPath UI</title></head><body><h1>XPath UI</h1><div id='app'></div></body></html>"

def get_all_json_data():
    data = {}
    for fname in os.listdir(CAPTURED_XPATHS_DIR):
        if fname.endswith('.json'):
            fpath = os.path.join(CAPTURED_XPATHS_DIR, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    arr = json.load(f)
                    data[fname] = arr
            except Exception as e:
                rr.log_error(f"Failed to load JSON {fpath}: {e}")
                continue
    return data

@app.route('/')
def index():
    template = load_template()
    return render_template_string(template)

@app.route('/api/data')
def api_data():
    return jsonify(get_all_json_data())

@app.route('/api/update_name', methods=['POST'])
def api_update_name():
    try:
        req = request.json
        page = req['page']
        idx = req['index']
        new_name = req['name']
        fpath = os.path.join(CAPTURED_XPATHS_DIR, page)
        
        with open(fpath, 'r', encoding='utf-8') as f:
            arr = json.load(f)
        if 0 <= idx < len(arr):
            arr[idx]['name'] = new_name
            with open(fpath, 'w', encoding='utf-8') as f:
                json.dump(arr, f, indent=2, ensure_ascii=False)
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Invalid index'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/reorder', methods=['POST'])
def api_reorder():
    try:
        req = request.json
        page = req['page']
        old_index = req['oldIndex']
        new_index = req['newIndex']
        fpath = os.path.join(CAPTURED_XPATHS_DIR, page)
        
        with open(fpath, 'r', encoding='utf-8') as f:
            arr = json.load(f)
        if 0 <= old_index < len(arr) and 0 <= new_index < len(arr):
            item = arr.pop(old_index)
            arr.insert(new_index, item)
            with open(fpath, 'w', encoding='utf-8') as f:
                json.dump(arr, f, indent=2, ensure_ascii=False)
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Invalid indices'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/reorder_files', methods=['POST'])
def api_reorder_files():
    try:
        req = request.json
        old_index = req['oldIndex']
        new_index = req['newIndex']
        
        # Get list of JSON files
        files = [f for f in os.listdir(CAPTURED_XPATHS_DIR) if f.endswith('.json')]
        files.sort()
        
        if 0 <= old_index < len(files) and 0 <= new_index < len(files):
            file_to_move = files[old_index]
            files.remove(file_to_move)
            files.insert(new_index, file_to_move)
            
            # Update the order by renaming files with temporary names first
            temp_names = []
            for i, fname in enumerate(files):
                old_path = os.path.join(CAPTURED_XPATHS_DIR, fname)
                temp_name = f"temp_{i}_{fname}"
                temp_path = os.path.join(CAPTURED_XPATHS_DIR, temp_name)
                os.rename(old_path, temp_path)
                temp_names.append(temp_name)
            
            # Rename back to original names in the new order
            for temp_name, final_name in zip(temp_names, files):
                temp_path = os.path.join(CAPTURED_XPATHS_DIR, temp_name)
                final_path = os.path.join(CAPTURED_XPATHS_DIR, final_name)
                os.rename(temp_path, final_path)
                
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Invalid indices'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    return jsonify({'success': False, 'error': 'Invalid index'})

# Update globals
capture_process = None
capture_active = False
selenium_start_time = None
selenium_browser_pids = set()
ui_browser_pid = None
ui_browser_start_time = None

def cleanup_selenium_processes():
    import psutil
    try:
        # Only kill processes we know are from Selenium
        for pid in selenium_browser_pids:
            try:
                proc = psutil.Process(pid)
                if proc.is_running() and pid != ui_browser_pid:  # Don't kill UI browser
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Kill selenium drivers
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                pname = proc.name().lower()
                # Only target msedgedriver.exe as primary driver; also keep fallback to known drivers for safety
                if any(driver in pname for driver in ['msedgedriver']):
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        rr.log_error(f"cleanup_selenium_processes error: {e}")

def signal_handler(signum, frame):
    print("\nCleaning up before exit...")
    try:
        cleanup_selenium_processes()
    except Exception as e:
        rr.log_error(f"Error during cleanup in signal_handler: {e}")
    if capture_process and capture_process.poll() is None:
        try:
            capture_process.terminate()
            try:
                capture_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                capture_process.kill()
        except Exception as e:
            rr.log_error(f"Error terminating capture_process in signal_handler: {e}")
    print("Cleanup complete. Exiting...")
    os._exit(0)

# Update capture_xpath endpoint to store driver
@app.route('/api/capture_xpath', methods=['POST'])
def api_capture_xpath():
    import subprocess
    import sys
    import time
    global capture_process, capture_active, selenium_start_time
    
    if capture_active:
        return jsonify({
            'success': False,
            'error': 'Capture already running'
        })
    
    try:
        # Resolve python executable: prefer current interpreter (sys.executable), else project .venv, else PATH lookup
        import shutil
        project_venv = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.venv', 'Scripts', 'python.exe'))
        # Prefer the interpreter that runs this process
        python_exec = sys.executable if getattr(sys, 'executable', None) else None
        if not python_exec and os.path.exists(project_venv):
            python_exec = project_venv
        if not python_exec:
            # Try to resolve 'python' on PATH
            python_on_path = shutil.which('python') or shutil.which('python3')
            if python_on_path:
                python_exec = python_on_path
        if not python_exec:
            rr.log_error('No Python executable found to start capture subprocess')
            raise FileNotFoundError('No Python executable found to start capture subprocess')
        # If python_exec is not absolute, try to resolve via which
        if not os.path.isabs(python_exec):
            resolved = shutil.which(python_exec)
            if resolved:
                python_exec = resolved
        rr.log_info(f'Resolved python executable for capture: {python_exec}')
        # Capture script lives in modules/
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'modules', 'capture_xpath.py'))
        if not os.path.exists(script_path):
            rr.log_error(f"Capture script not found at {script_path}")
            raise FileNotFoundError(f"Capture script not found at {script_path}")
        # Driver should be in the project's drivers folder (same level as main.py)
        driver_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'drivers', 'msedgedriver.exe'))
        if not os.path.exists(driver_path):
            rr.log_error(f"Edge WebDriver not found at {driver_path}")
            raise FileNotFoundError(f"Edge WebDriver not found at {driver_path}")
 
        selenium_start_time = time.time()
 
        # Use project-local logs folder
        logs_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(logs_dir, exist_ok=True)
 
        stdout_log = open(os.path.join(logs_dir, 'capture_stdout.log'), 'w')
        stderr_log = open(os.path.join(logs_dir, 'capture_stderr.log'), 'w')
 
        # Pass driver path and browser type to the script
        # Run as a module so package imports (modules.*) work correctly in the subprocess.
        cmd = [python_exec, '-m', 'modules.capture_xpath', '--browser', 'edge', '--driver', driver_path]
        rr.log_info(f"Starting capture subprocess with command: {cmd}")
        if not os.path.exists(python_exec):
            rr.log_error(f"Resolved python executable does not exist: {python_exec}")
            raise FileNotFoundError(f"Python executable not found: {python_exec}")
        capture_process = subprocess.Popen(
            cmd,
            stdout=stdout_log,
            stderr=stderr_log,
            env=dict(os.environ,
                    PYTHONUNBUFFERED="1",
                    EDGE_LOG_FILE="NUL",
                    EDGE_SUPPRESS_WARNINGS="1"),
            text=True,
            cwd=os.path.dirname(__file__)
        )
        capture_active = True
        rr.log_info(f"Capture subprocess started with PID: {capture_process.pid}")
        return jsonify({
            'success': True,
            'message': 'Capture started',
            'status': 'running',
            'pid': capture_process.pid
        })
    except Exception as e:
        rr.log_error(f"Error starting capture subprocess: {e}")
        if capture_process:
            capture_process.terminate()
        capture_process = None
        capture_active = False
        selenium_start_time = None
        if 'stdout_log' in locals(): stdout_log.close()
        if 'stderr_log' in locals(): stderr_log.close()
        return jsonify({
            'success': False,
            'error': f'Failed to start capture: {str(e)}'
        })


@app.route('/api/stop_capture', methods=['POST'])
def api_stop_capture():
    import psutil
    import time
    global capture_process, capture_active, selenium_start_time
    
    if not capture_active:
        return jsonify({
            'success': False,
            'error': 'No capture process running'
        })
        
    try:
        # Only kill ChromeDriver/Selenium processes
        killed_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'create_time']):
            try:
                # Only kill processes created after we started Selenium
                if selenium_start_time and proc.create_time() > selenium_start_time:
                    pname = proc.name().lower()
                    if any(driver in pname for driver in ['chromedriver', 'msedgedriver', 'geckodriver']):
                        proc.kill()
                        killed_processes.append(pname)
                    elif any(browser in pname for browser in ['chrome', 'msedge', 'firefox']):
                        # For browsers, check if it's a Selenium instance
                        cmdline = ' '.join(proc.cmdline()).lower()
                        if 'selenium' in cmdline or '--remote-debugging-port' in cmdline:
                            proc.kill()
                            killed_processes.append(pname)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            
        # Terminate the capture process
        if capture_process and capture_process.poll() is None:
            capture_process.terminate()
            try:
                capture_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                capture_process.kill()
            
        capture_process = None
        capture_active = False
        selenium_start_time = None
        
        return jsonify({
            'success': True,
            'message': f'Capture stopped successfully. Killed processes: {", ".join(killed_processes)}',
            'status': 'stopped'
        })
        
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': f'Error stopping capture: {str(e)}\n{traceback.format_exc()}'
        })
    

@app.route('/api/rename_json', methods=['POST'])
def api_rename_json():
    req = request.json
    old = req.get('old')
    new = req.get('new')
    if not old or not new or old == new:
        return jsonify({'success': False, 'error': 'Invalid file names'})
    old_path = os.path.join(CAPTURED_XPATHS_DIR, old)
    new_path = os.path.join(CAPTURED_XPATHS_DIR, new)
    try:
        if not os.path.exists(old_path):
            return jsonify({'success': False, 'error': 'Old file does not exist'})
        if os.path.exists(new_path):
            return jsonify({'success': False, 'error': 'New file already exists'})
        os.rename(old_path, new_path)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    
@app.route('/api/update_xpath', methods=['POST'])
def api_update_xpath():
    req = request.json
    page = req['page']
    idx = req['index']
    new_xpath = req['xpath']
    fpath = os.path.join(CAPTURED_XPATHS_DIR, page)
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            arr = json.load(f)
        if 0 <= idx < len(arr):
            arr[idx].setdefault('selectors', {})['xpath'] = new_xpath
            with open(fpath, 'w', encoding='utf-8') as f:
                json.dump(arr, f, indent=2, ensure_ascii=False)
            return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    return jsonify({'success': False, 'error': 'Invalid index'})

def open_browser(url):
    import time
    global ui_browser_pid, ui_browser_start_time
    ui_browser_start_time = time.time()
    
    try:
        import webbrowser
        webbrowser.open_new_tab(url)
    except Exception as e:
        print(f"Error opening browser: {e}")


@app.route('/api/delete_json', methods=['POST'])
def api_delete_json():
    try:
        if not request.is_json:
            return jsonify({'success': False, 'error': 'Content-Type must be application/json'})
        
        data = request.get_json()
        if not data or 'file' not in data:
            return jsonify({'success': False, 'error': 'Missing file parameter'})
        
        fname = data['file']
        fpath = os.path.join(CAPTURED_XPATHS_DIR, fname)
        
        if not os.path.exists(fpath):
            return jsonify({'success': False, 'error': 'File not found'})
            
        os.remove(fpath)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    
@app.route('/api/delete_field', methods=['POST'])
def api_delete_field():
    try:
        if not request.is_json:
            return jsonify({'success': False, 'error': 'Content-Type must be application/json'})
            
        data = request.get_json()
        if not data or 'page' not in data or 'index' not in data:
            return jsonify({'success': False, 'error': 'Missing required parameters'})
            
        page = data['page']
        idx = int(data['index'])
        fpath = os.path.join(CAPTURED_XPATHS_DIR, page)
        
        if not os.path.exists(fpath):
            return jsonify({'success': False, 'error': 'File not found'})
            
        with open(fpath, 'r', encoding='utf-8') as f:
            arr = json.load(f)
            
        if not (0 <= idx < len(arr)):
            return jsonify({'success': False, 'error': 'Invalid index'})
            
        arr.pop(idx)
        
        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(arr, f, indent=2, ensure_ascii=False)
            
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    

@app.route('/api/current_url', methods=['GET'])
def get_current_url():
    if not capture_active or not capture_process:
        return jsonify({
            'success': False,
            'error': 'No active capture session'
        })
    
    try:
        # Get URL from capture process
        url = capture_process.stdout.readline().strip()
        return jsonify({
            'success': True,
            'url': url
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })
    
@app.route('/api/capture_status', methods=['GET'])
def api_capture_status():
    global capture_process, capture_active, capture_driver
    if not capture_active:
        return jsonify({
            'active': False
        })
    
    current_url = None
    if capture_driver:
        try:
            current_url = capture_driver.current_url
        except:
            pass
            
    return jsonify({
        'active': True,
        'currentUrl': current_url
    })

@app.route('/api/validate_xpaths', methods=['POST'])
def api_validate_xpaths():
    try:
        if not capture_active:
            return jsonify({
                'success': False,
                'error': 'Start capture process first to validate XPaths'
            })
            
        req = request.get_json()
        if not req or 'file' not in req:
            return jsonify({'success': False, 'error': 'Missing file parameter'})
            
        fname = req['file']
        fpath = os.path.join(CAPTURED_XPATHS_DIR, fname)
        
        if not os.path.exists(fpath):
            return jsonify({'success': False, 'error': 'File not found'})
            
        result = validate_json_file(fpath)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    

# Handle graceful exit on Ctrl+C
signal.signal(signal.SIGINT, signal_handler)

if __name__ == '__main__':
    port = 5005
    url = f'http://127.0.0.1:{port}/'
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Open browser in main process only
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        open_browser(url)
    
    app.run(port=port, debug=True)
    import webbrowser
    webbrowser.open(url)
