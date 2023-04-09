import os
import time
import json
import random
import logging
import requests
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait as Wait
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from configparser import ConfigParser

from notification import send_notification

logging.basicConfig(
    filename="scheduler.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Get the absolute path to the config.ini file
current_dir = os.path.dirname(os.path.abspath(__file__))
config_file = os.path.join(current_dir, '..', 'config', 'config.ini')

config = ConfigParser()
config.read(config_file)

USERNAME = config.get('USVISA', 'USERNAME')
PASSWORD = config.get('USVISA', 'PASSWORD')
SCHEDULE_ID = config.get('USVISA', 'SCHEDULE_ID')
MY_SCHEDULE_DATE = config.get('USVISA', 'MY_SCHEDULE_DATE')
COUNTRY_CODE = config.get('USVISA', 'COUNTRY_CODE')
FACILITY_ID = config.get('USVISA', 'FACILITY_ID')

LOCAL_USE = config.getboolean('CHROMEDRIVER', 'LOCAL_USE')
HUB_ADDRESS = config.get('CHROMEDRIVER', 'HUB_ADDRESS')

REGEX_CONTINUE = "//a[contains(text(),'Continue')]"

STEP_TIME = 1 # time between steps (interactions with forms): 0.5 seconds
RETRY_TIME = 60 * 5 # wait time between retries/checks for available dates: 10 minutes
EXCEPTION_TIME = 60 * 37 # wait time when an exception occurs: 30 minutes
COOLDOWN_TIME = 60 * 57 * 3  # wait time when temporary banned (empty list): 60 minutes

DATE_URL = f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment/days/{FACILITY_ID}.json?appointments[expedite]=false"
TIME_URL = f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment/times/{FACILITY_ID}.json?date=%s&appointments[expedite]=false"
APPOINTMENT_URL = f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment"

EXIT = False

def get_driver():
    if LOCAL_USE:
        dr = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
    else:
        dr = webdriver.Remote(command_executor=HUB_ADDRESS, options=webdriver.ChromeOptions())
    return dr


driver = get_driver()

def login():
    # Bypass reCAPTCHA
    driver.get(f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv")
    time.sleep(STEP_TIME)
    a = driver.find_element(By.XPATH, '//a[@class="down-arrow bounce"]')
    a.click()
    time.sleep(STEP_TIME)

    logging.info("Login start...")
    href = driver.find_element(By.XPATH, '//*[@id="header"]/nav/div/div/div[2]/div[1]/ul/li[3]/a')
    href.click()
    time.sleep(STEP_TIME)
    Wait(driver, 60).until(EC.presence_of_element_located((By.NAME, "commit")))

    print("\tclick bounce")
    a = driver.find_element(By.XPATH, '//a[@class="down-arrow bounce"]')
    a.click()
    time.sleep(STEP_TIME)
    do_login_action()

def do_login_action():
    print("\tinput email")
    user = driver.find_element(By.ID, 'user_email')
    user.send_keys(USERNAME)
    time.sleep(random.uniform(0.5, 1))

    print("\tinput pwd")
    pw = driver.find_element(By.ID, 'user_password')
    pw.send_keys(PASSWORD)
    time.sleep(random.uniform(0.5, 1))

    print("\tclick privacy")
    box = driver.find_element(By.CLASS_NAME, 'icheckbox')
    box.click()
    time.sleep(random.uniform(0.5, 1))

    print("\tcommit")
    btn = driver.find_element(By.NAME, 'commit')
    btn.click()
    time.sleep(random.uniform(0.5, 1))
    
    print("\tcontinue")
    Wait(driver, 60).until(EC.presence_of_element_located((By.XPATH, REGEX_CONTINUE)))
    continue_btn = driver.find_element(By.XPATH, REGEX_CONTINUE)
    continue_btn.click()

    print("\treschedule")
    driver.get(APPOINTMENT_URL)

    print("\tlogin successful!")

def is_logged_in():
    content = driver.page_source
    if(content.find("error") != -1):
        return False
    return True

def get_date():
    # driver.get(DATE_URL)
    driver.get(APPOINTMENT_URL)
    session = driver.get_cookie("_yatri_session")["value"]
    NEW_GET = driver.execute_script(
        "var req = new XMLHttpRequest();req.open('GET', '"
        + str(DATE_URL)
        + "', false);req.setRequestHeader('Accept', 'application/json, text/javascript, */*; q=0.01');req.setRequestHeader('X-Requested-With', 'XMLHttpRequest'); req.setRequestHeader('Cookie', '_yatri_session="
        + session
        + "'); req.send(null);return req.responseText;"
    )
    return json.loads(NEW_GET)

def get_time(date):
    time_url = TIME_URL % date
    session = driver.get_cookie("_yatri_session")["value"]
    content = driver.execute_script(
        "var req = new XMLHttpRequest();req.open('GET', '"
        + str(time_url)
        + "', false);req.setRequestHeader('Accept', 'application/json, text/javascript, */*; q=0.01');req.setRequestHeader('X-Requested-With', 'XMLHttpRequest'); req.setRequestHeader('Cookie', '_yatri_session="
        + session
        + "'); req.send(null);return req.responseText;"
    )
    data = json.loads(content)
    time = data.get("available_times")[-1]
    print(f"Got time successfully! {date} {time}")
    return time

def print_dates(dates):
    print("Available dates:")
    for d in dates:
        print("%s \t business_day: %s" % (d.get("date"), d.get("business_day")))
    print()


last_seen = None

def get_available_date(dates):
    global last_seen

    def is_earlier(date):
        my_date = datetime.strptime(MY_SCHEDULE_DATE, "%Y-%m-%d")
        new_date = datetime.strptime(date, "%Y-%m-%d")
        result = my_date > new_date
        print(f"Is {my_date} > {new_date}:\t{result}")
        return result

    print("Checking for an earlier date:")
    for d in dates:
        date = d.get("date")
        if is_earlier(date) and date != last_seen:
            _, month, day = date.split("-")
            last_seen = date
            return date

def reschedule(date):
    global EXIT
    print(f"Starting Reschedule ({date})")

    time = get_time(date)
    if (driver.current_url != APPOINTMENT_URL): 
        driver.get(APPOINTMENT_URL)

    print("Reschedule start...")
    continue_button = driver.find_element(By.XPATH, '//*[@id="main"]/div[3]/form/div[2]/div/input')
    continue_button.click()
    referer = driver.current_url

    data = {
        "utf8": driver.find_element(by=By.NAME, value="utf8").get_attribute("value"),
        "authenticity_token": driver.find_element(
            by=By.NAME, value="authenticity_token"
        ).get_attribute("value"),
        "confirmed_limit_message": driver.find_element(
            by=By.NAME, value="confirmed_limit_message"
        ).get_attribute("value"),
        "use_consulate_appointment_capacity": driver.find_element(
            by=By.NAME, value="use_consulate_appointment_capacity"
        ).get_attribute("value"),
        "appointments[consulate_appointment][facility_id]": FACILITY_ID,
        "appointments[consulate_appointment][date]": date,
        "appointments[consulate_appointment][time]": time,
    }

    headers = {
        "User-Agent": driver.execute_script("return navigator.userAgent;"),
        "Referer": referer,
        "Cookie": "_ga=GA1.2.354589003.1677105816; " + "_yatri_session=" + driver.get_cookie("_yatri_session")["value"],
    }

    # print(f'APPOINTMENT_URL: {APPOINTMENT_URL}\nheaders: {headers}\ndata: {data}')
    r = requests.post(APPOINTMENT_URL, headers=headers, data=data)
    if r.text.find("You have successfully scheduled your visa appointment") != -1:
        msg = f"Rescheduled Successfully! {date} {time}"
        send_notification(msg)
        EXIT = True
    else:
        logging.error(f"Reschedule Failed. {date} {time}: {r.text} \n\n{r.status_code}")
        msg = f"Reschedule Failed. {date} {time}: {r.text} \n\n{r.status_code}"
        send_notification(msg)

def push_notification(dates):
    msg = "date: "
    for d in dates:
        msg = msg + d.get("date") + "; "
    send_notification(msg)

if __name__ == "__main__":
    login()
    print(driver.execute_script("return navigator.userAgent;"))
    retry_count = 0
    while 1:
        if retry_count > 6:
            break
        try:
            print("------------------")
            print(datetime.today())
            print(f"Retry count: {retry_count}")
            print()

            dates = get_date()[:5]
            if not dates:
                msg = "List is empty"
                send_notification(msg)
                # EXIT = True
            print_dates(dates)
            date = get_available_date(dates)
            print()
            print(f"New date: {date}")
            if date:
                reschedule(date)
                push_notification(dates)

            if EXIT:
                print("------------------exit")
                break

            if not dates:
                msg = "List is empty"
                send_notification(msg)
                # EXIT = True
                time.sleep(COOLDOWN_TIME)
            else:
                time.sleep(RETRY_TIME)

        except Exception as e:
            retry_count += 1
            time.sleep(EXCEPTION_TIME)
            from traceback import format_exc

            logging.exception("Program crashed!")
            send_notification("Program crashed!" + str(format_exc()))

    if not EXIT:
        send_notification("HELP! Crashed.")