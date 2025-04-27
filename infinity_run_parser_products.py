import subprocess
import time
import sys
import psutil

script_to_run = "main_parser.py"

def kill_chrome_processes():
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'] in ('chromedriver', 'chrome', 'google-chrome', 'chrome.exe'):
            try:
                proc.kill()
            except psutil.NoSuchProcess:
                pass

def monitor_script():
    while True:
        try:
            print(f"Запуск скрипта: {script_to_run}")
            kill_chrome_processes()
            process = subprocess.Popen([sys.executable, script_to_run])
            process.wait()
            print(f"Скрипт завершился с кодом {process.returncode}")
        except Exception as e:
            print(f"Ошибка: {e}")
        print("Перезапуск через 10 секунд...")
        time.sleep(10)

if __name__ == "__main__":
    monitor_script()