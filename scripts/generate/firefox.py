
import os
import requests
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from pymailtm import Account

import random, time
import string
import subprocess, atexit, signal

VIDEO_PATH   =  "9089uilbo0890"
LOOPBACK_DEV = "pio;jk;jk;;2"
_ffmpeg_proc = None

def start_fake_webcam():
    global _ffmpeg_proc
    if _ffmpeg_proc and _ffmpeg_proc.poll() is None:
        return
    if not os.path.exists(LOOPBACK_DEV):
        raise RuntimeError(f"{LOOPBACK_DEV} missing — load v4l2loopback first")
    if not os.path.exists(VIDEO_PATH):
        raise RuntimeError(f"video {VIDEO_PATH} not found — set FAKE_CAM_VIDEO")
    _ffmpeg_proc = subprocess.Popen([
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-stream_loop", "-1", "-re", "-i", VIDEO_PATH,
        "-vf", "scale=1280:720,fps=30,format=yuv420p",
        "-f", "v4l2", LOOPBACK_DEV,
    ], stdin=subprocess.DEVNULL)
    time.sleep(1)

def stop_fake_webcam():
    global _ffmpeg_proc
    if _ffmpeg_proc and _ffmpeg_proc.poll() is None:
        _ffmpeg_proc.send_signal(signal.SIGINT)
        try: _ffmpeg_proc.wait(timeout=3)
        except subprocess.TimeoutExpired: _ffmpeg_proc.kill()

#atexit.register(stop_fake_webcam)

def generateUsername():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))

def generateEmail(password):
    maxRetries = 3
    for attempt in range(maxRetries):
        try:
            domain_response = requests.get("https://api.mail.tm/domains", timeout=10)
            domain_response.raise_for_status()
            domains = domain_response.json().get('hydra:member', [])
            
            if not domains:
                raise Exception("No domains available")

            domain = random.choice(domains)['domain']
            username = generateUsername()
            address = f"{username}@{domain}"

            account_response = requests.post(
                "https://api.mail.tm/accounts", 
                json={"address": address, "password": password}, 
                timeout=10
            )
            
            if account_response.status_code == 201:
                account_data = account_response.json()
                
                token_response = requests.post(
                    "https://api.mail.tm/token",
                    json={"address": address, "password": password},
                    timeout=10
                )
                
                if token_response.status_code == 200:
                    token = token_response.json().get("token")
                    if token:
                        return address, password, token, account_data['id']
            
            if attempt < maxRetries - 1:
                time.sleep(2)
                
        except Exception as e:
            print(f"Error creating email: {e}")
            if attempt < maxRetries - 1:
                time.sleep(2)

    raise Exception(f"Failed to create email after {maxRetries} attempts")


USE_CHROME = False


import getpass

try:
    os.getlogin()
except OSError:
    def getlogin_monkey_patch():
        return getpass.getuser()

    os.getlogin = getlogin_monkey_patch



def generate_random_birthdate():
    month = random.choice(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])
    day = random.choice(range(1, 27))
    year = str(random.randint(1995, 2002))
    return month, day, year

PASSWORD = os.getenv("PASSWORD")
upload_key = os.getenv("UPLOAD_KEY")
upload_url = os.getenv("UPLOAD_URL", "https://command.botted.org/api/roblox-sessions/import")
session_proxy = os.getenv("ROBLOX_SESSION_PROXY") or os.getenv("PROXY")

firstnames = [
    "john","Jane","scott","ian","jimmy","r2eq","mark","Just","rea3","Christos",
    "opan","scar","Gluerell","pixel","skib","george","ahmad","Unu","neo","luna",
    "Max","zero","nova","echo","kai","drip","ace","blitz","rex","niko","vex","lex",
    "rami","theo","dino","mira","nash","pyro","juno","aria","zane","finn","tara",
    "omar","riley","zyro","cyn","ash","chloe","brynn","milo","toby","ezra","axel",
    "vale","skye","ryn","dusk","jett","haze","emi","kora","lio","nira","kane",
    "drew","rook","blair","jax","novae","rune","faye","lars","tess","mika","rei",
    "zeph","cole","timo","grey","wren","arlo","lux","bree","seth","remi","vera",
    "zion","maddie","eli","rhea","nox","ivy","kace","lark","nemo","arden","ty","l0g","c4de","mist","oz"
]

middlenames = [
    "_3","the4","And5","men1","664","S1dney","sl33per","simpon","bee","DJd33",
    "wil12","Van","bayar","zz","404","xX","pro","Dev","dark","_the","v2","exe",
    "_bot","999","666","777","XL","jr","onfire","Ultra","beta","alpha","Core",
    "_real","dat","meta","neo","micro","Macro","prime","alt","0","01","02","x",
    "xx","XXX","low","High","deep","Fast","slow","Cold","hot","void","Doom",
    "space","Tech","iron","Ghost","night","Sun","moon","Cloud","air","Fire","ice",
    "earth","Stone","dust","Wave","warp","Hyper","cyber","Ninja","mage","Tank",
    "sn1p3","Aim","shot","blast","botz","Droid","Sys","port","Root"
]

lastnames = [
    "itius","inion","Ion","Ian","xd","xD","II","Th","v","Rum","cache","0251",
    "kai","Walls","14","00","AS","capybara","sammy","Lord","Master","Core","Byte",
    "sync","Zero","nix","Burn","dust","Nova","storm","Lite","Rise","loop","man",
    "x","99","Zone","code","Crash","void","Cube","Stack","Flow","drop","End","fox",
    "Owl","wolf","Hawk","bear","Bee","Fish","Whale","lion","Panther","Tiger",
    "crow","Ghost","shade","Spark","Flame","Ray","Drake","snake","Spider","cube",
    "Data","file","Gate","link","Net","Mode","prog","Clip","Cast","shot","Band",
    "Play","jam","Spin","wave","mix","Hack","crpt","corex","unit","Rider","sig",
    "Stormz","Sparkz","Darkz","Lightz","Plus","Prime","Seed","Dusty","Voidy","Mind"
]

#print("total combinations", len(firstnames) * len(middlenames) * len(lastnames) * 9 * 9 * 9)

def generate_username():
    firstname = random.randint(1,10000) == 1 and "shownape" or random.choice(firstnames)
    return firstname + random.choice(middlenames) + random.choice(lastnames) + str(random.randint(1, 999))
        

def random_sleep(min = 0.3, max = 0.8):
    time.sleep(random.uniform(min, max))

def fill_out_page(driver):
    month, day, year = generate_random_birthdate()
    print(f"Generated birthdate: {month} {day}, {year}") 

    month_select = Select(driver.find_element(By.ID, "MonthDropdown"))
    month_select.select_by_value(month)
    print(f"Selected month: {month}") 

    day_select = Select(driver.find_element(By.ID, "DayDropdown"))
    day_select.select_by_value(f"{day:02d}")
    print(f"Selected day: {day}") 

    year_select = Select(driver.find_element(By.ID, "YearDropdown"))
    year_select.select_by_value(year)
    print(f"Selected year: {year}") 

    username_input = driver.find_element(By.ID, "signup-username")
    
    while True:
        username = generate_username()
        username_input.send_keys(username)
        print(f"Attempting username: {username}") 
       # driver.execute_script("arguments[0].blur();", username_input)
        random_sleep()
        
        try:
            success_div = driver.find_element(By.XPATH, "//div[contains(@class, 'has-success') and input[@id='signup-username']]")
            if success_div:
                print(f"Username {username} accepted.") 
                break
        except:
            pass
        
        try:
            error_div = driver.find_element(By.XPATH, "//div[contains(@class, 'has-error') and input[@id='signup-username']]")
            if error_div:
                print(f"Username {username} rejected, trying again.") 
                username_input.send_keys(Keys.CONTROL + "a")
                username_input.send_keys(Keys.DELETE) # different way same result - miller
        except:
            pass
    random_sleep()

    password_input = driver.find_element(By.ID, "signup-password")
    password_input.send_keys(PASSWORD)
    print("Password entered.") 
    random_sleep()

    try:
        signup_checkbox = driver.find_element(By.ID, "signup-checkbox")
        if signup_checkbox:
            signup_checkbox.click()
            random_sleep()
    except Exception as e:
        print("Signup checkbox doesnt exist")

    signup_button = driver.find_element(By.ID, "signup-button")

    signup_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "signup-button")))
    signup_button.click()
    random_sleep()

    print("Signup button clicked.") 

def kill_account_protection(drv):
    try:
        drv.get("https://create.roblox.com/settings/advanced")
        print("Accessed account protection settings page.") 
        wait = WebDriverWait(drv, 30)

        unprotected_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-testid='unprotected-button']")))
        unprotected_btn.click()
        print("Clicked 'Unprotected' button.") 
        random_sleep(1.4, 2) 

        checkbox_label = wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/div[2]/div[3]/div/div[1]/span/div[2]/label")))
        checkbox_label.click() 
        print("Clicked checkbox.") 
        random_sleep()

        disable_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-testid='disable-button']")))
        disable_btn.click()
        print("Clicked 'Disable' button.") 
        time.sleep(5) # wait just in case if pop up

        drv.switch_to.frame("challenge-frame")

        password_input_box = wait.until(EC.presence_of_element_located((By.ID, "two-step-verification-code-input")))  
        password_input_box.send_keys(PASSWORD) 
        random_sleep(.5, 1.2)

        verify_button = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'button.btn-cta-md.modal-modern-footer-button[aria-label="Verify"]')))   
        verify_button.click()
  
        drv.switch_to.default_content()

        time.sleep(3)


    except Exception as e:
        print("settings step failed:", e)
        return False # solution: kill yourself - miller

    print("Account protection successfully killed.") 
    return True



def poll_email(email, emailPassword, emailID):
    print(f"Polling email for {email}...")
    emailCheckAttempts = 0
    maxEmailAttempts = 300
    account = Account(emailID, email, emailPassword)

    while emailCheckAttempts < maxEmailAttempts:
        print(f"Email poll attempt {emailCheckAttempts + 1}/{maxEmailAttempts}")
        try:
            messages = account.get_messages()
            if len(messages) > 0:
                print(f"Found {len(messages)} messages.")
                return messages
        except Exception as e:
            print(f"Error checking email: {e}")

        emailCheckAttempts += 1
        time.sleep(5)

    print("Email polling timed out.")
    return False

def link_email(driver, email):
    print("Linking email...")
    driver.get("https://www.roblox.com/my/account#!/info")
    wait = WebDriverWait(driver, 30)

    btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'settings-text-field-container')][.//span[text()='Email']]//button[contains(@class, 'foundation-web-button') and .//span[normalize-space()='Add']]")))
    btn.click()
    print("Clicked Add button.")
    email_input = wait.until(EC.presence_of_element_located((By.ID, "emailAddress")))
    email_input.send_keys(email)
    print(f"Entered email into modal: {email}")
    random_sleep()
    
    add_email_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@class='modal-full-width-button btn-primary-md btn-min-width' and text()='Add Email']")))
    add_email_btn.click()
    print("Clicked Add Email button")
    random_sleep()


def verify_email_address(driver):
    email, emailPassword, token, emailID = generateEmail(PASSWORD)
    print(f"Generated email: {email}")

    link_email(driver, email)
    

    messages = poll_email(email, emailPassword, emailID)
    if messages:
        msg = messages[0]
        body = getattr(msg, 'text', None)

        if not body and hasattr(msg, 'html') and msg.html and len(msg.html) > 0:
            body = msg.html[0]

        if body:
            print("Email body found.")
            match = re.search(r'https://www\.roblox\.com/account/settings/verify-email\?ticket=[^\s)"]+', body)
            if match:
                link = match.group(0)
                print(f"Verification link found: {link}")
                driver.get(link)
                return True
            else:
                print("No verification link found in email body.")
        else:
            print("No email body found.")

    return False


def age_verify(driver):
    print("Starting age verification...")
    driver.get("https://www.roblox.com/my/account#!/info")
    wait = WebDriverWait(driver, 30)

    cam_btn = wait.until(EC.element_to_be_clickable((
        By.XPATH,
        "//div[contains(@class,'age-verification-upsell-banner')]"
        "//button[.//span[normalize-space()='Continue with camera']]"
    )))
    cam_btn.click()
    print("Clicked 'Continue with camera'.")
    random_sleep(1, 2)

    persona_iframe = wait.until(EC.presence_of_element_located((
        By.CSS_SELECTOR, 'iframe.persona-widget__iframe'
    )))
    driver.switch_to.frame(persona_iframe)
    print("Switched into Persona iframe.")

    try:
        continue_btn = wait.until(EC.element_to_be_clickable((
            By.XPATH, "//button[.//span[normalize-space()='Continue'] or normalize-space()='Continue']"
        )))
        continue_btn.click()
        print("Clicked Continue inside Persona widget.")
        random_sleep(1, 2)
        return True
    finally:
        driver.switch_to.default_content()


def poll_for_captcha(driver):
    while True: 
        if "https://www.roblox.com/home" in driver.current_url: 
            break

        try:
            driver.find_element(By.CSS_SELECTOR, 'iframe[title="Verification challenge"], iframe[src*="arkoselabs"]')
            print("Detected captcha, done.")
            driver.quit()
            exit()
        except Exception:
            pass

        try:
            driver.find_element(By.CSS_SELECTOR, 'div#GeneralErrorText[role="button"][aria-label="dismiss general error"]')
            print("Detected general error, quitting.")
            driver.quit()
            exit()
        except Exception:
            pass


def main():
  #  start_fake_webcam()

    if USE_CHROME:
        import undetected_chromedriver as uc
        opts = uc.ChromeOptions()
        opts.add_argument("--use-fake-ui-for-media-stream")
        driver = uc.Chrome(options=opts)
    else:
        from undetected_geckodriver import Firefox
        from selenium.webdriver.firefox.options import Options as FxOptions
        opts = FxOptions()
        opts.set_preference("permissions.default.camera", 1)
        opts.set_preference("permissions.default.microphone", 1)
        opts.set_preference("media.navigator.permission.disabled", True)
        opts.set_preference("media.getusermedia.insecure.enabled", True)
        driver = Firefox(options=opts)
        
    try:
        print("Browser initialized.") 
        driver.get("https://www.roblox.com/CreateAccount")
        print("Accessed Roblox account creation page.") 

        fill_out_page(driver)

        poll_for_captcha(driver)

        success = kill_account_protection(driver)

        verified = verify_email_address(driver)

        if verified:
            print("Email verified.")
        else:
            print("Email verification failed.")

        age_verified = False # age_verify(driver)

        if success:
            roblosecurity_cookie = driver.get_cookie('.ROBLOSECURITY')
            if not upload_key:
                raise RuntimeError("UPLOAD_KEY is required to upload Roblox sessions")
            if not session_proxy:
                raise RuntimeError("ROBLOX_SESSION_PROXY or PROXY is required by /api/roblox-sessions/import")
            if not roblosecurity_cookie or not roblosecurity_cookie.get("value"):
                raise RuntimeError(".ROBLOSECURITY cookie was not found in the browser session")
            
            response = requests.post(
                upload_url,
                json={
                    "cookie": roblosecurity_cookie["value"],
                    "proxy": session_proxy,
                },
                headers={
                    "x-api-key": upload_key
                },
                timeout=30,
            )

            if 200 <= response.status_code < 300:
                payload = response.json()
                session = payload.get("session") or {}
                print(
                    "Cookie uploaded successfully.",
                    f"session_id={session.get('session_id')}",
                    f"username={session.get('username')}",
                    f"status={session.get('status')}",
                )
            else:
                print(f"Failed to upload cookie: {response.status_code} - {response.text}")
        else:
            driver.quit() 
            main()
            return
    finally:
        try:
            driver.quit()
        except:
            print("program closed, but webdriver already shutdown")

while True: 
    try: 
        main()
    except KeyboardInterrupt:
        exit()
