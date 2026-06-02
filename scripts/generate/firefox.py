
import os
import hashlib
import getpass
import requests
import re
import random
import signal
import string
import subprocess
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from pymailtm import Account
from username_generator import generate_username

VIDEO_PATH = "9089uilbo0890"
LOOPBACK_DEV = "pio;jk;jk;;2"
_ffmpeg_proc = None
ARTIFACT_DIR = Path(os.getenv("GENERATOR_ARTIFACT_DIR", "artifacts/generator"))
CURRENT_STEP = "startup"

def utc_timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def safe_field(value):
    text = str(value)
    return text.replace("\n", "\\n").replace("\r", "\\r")

def log(message, **fields):
    suffix = ""
    if fields:
        suffix = " " + " ".join(f"{key}={safe_field(value)}" for key, value in fields.items())
    print(f"[{utc_timestamp()}] {message}{suffix}", flush=True)

def set_step(name):
    global CURRENT_STEP
    CURRENT_STEP = name
    log("STEP", name=name)

def github_escape(value):
    text = str(value)
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")

def github_error(message):
    if os.getenv("GITHUB_ACTIONS"):
        print(f"::error::{github_escape(message)}", flush=True)

def secret_summary(value):
    if not value:
        return "<missing>"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    return f"<set len={len(value)} sha256={digest}>"

def redacted_url(url):
    if not url:
        return "<unknown>"
    try:
        parsed = urlparse(url)
        query = "<redacted>" if parsed.query else ""
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, ""))
    except Exception:
        return "<unparseable-url>"

def env_float(name, default):
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero")
    return value

def artifact_path(label, suffix):
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("_") or "artifact"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return ARTIFACT_DIR / f"{stamp}-{safe_label}.{suffix}"

def write_artifact(label, suffix, content):
    path = artifact_path(label, suffix)
    path.write_text(content, encoding="utf-8", errors="replace")
    log("Saved artifact", path=path)
    return path

def save_browser_artifacts(driver, label):
    if driver is None:
        return
    try:
        log("Browser state", url=redacted_url(driver.current_url), title=getattr(driver, "title", "<unknown>"))
    except Exception as exc:
        log("Could not read browser state", error=exc)
    try:
        screenshot = artifact_path(label, "png")
        driver.save_screenshot(str(screenshot))
        log("Saved browser screenshot", path=screenshot)
    except Exception as exc:
        log("Could not save browser screenshot", error=exc)
    try:
        write_artifact(f"{label}-page", "html", driver.page_source or "")
    except Exception as exc:
        log("Could not save page source", error=exc)

def report_exception(context, exc, driver=None):
    message = f"{context} failed during step '{CURRENT_STEP}': {type(exc).__name__}: {exc}"
    log("ERROR", context=context, step=CURRENT_STEP, error=f"{type(exc).__name__}: {exc}")
    github_error(message)
    trace = traceback.format_exc()
    print(trace, flush=True)
    try:
        write_artifact(f"{context}-traceback", "txt", trace)
    except Exception:
        pass
    save_browser_artifacts(driver, f"{context}-{CURRENT_STEP}")

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
        try:
            _ffmpeg_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            _ffmpeg_proc.kill()

def generateUsername():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))

def generateEmail(password):
    maxRetries = 3
    for attempt in range(maxRetries):
        try:
            log("Fetching mail.tm domains", attempt=f"{attempt + 1}/{maxRetries}")
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
                log("Created mail.tm account", address=address, account_id=account_data.get("id"))
                
                token_response = requests.post(
                    "https://api.mail.tm/token",
                    json={"address": address, "password": password},
                    timeout=10
                )
                
                if token_response.status_code == 200:
                    token = token_response.json().get("token")
                    if token:
                        return address, password, token, account_data['id']
                log(
                    "mail.tm token request failed",
                    status=token_response.status_code,
                    body=token_response.text[:500],
                )
            else:
                log(
                    "mail.tm account create failed",
                    status=account_response.status_code,
                    body=account_response.text[:500],
                )
            
            if attempt < maxRetries - 1:
                time.sleep(2)
                
        except Exception as e:
            log("Error creating email", error=e, attempt=f"{attempt + 1}/{maxRetries}")
            if attempt < maxRetries - 1:
                time.sleep(2)

    raise RuntimeError(f"Failed to create email after {maxRetries} attempts")


USE_CHROME = False

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
upload_url = os.getenv("UPLOAD_URL", "https://command.botted.org/api/internal/roblox-sessions/import")
upload_division = os.getenv("ROBLOX_SESSION_INGEST_DIVISION", "default").strip() or "default"
upload_pool = os.getenv("ROBLOX_SESSION_INGEST_POOL", "global").strip().lower() or "global"
POOL_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
upload_enqueue_timeout_seconds = env_float("UPLOAD_ENQUEUE_TIMEOUT_SECONDS", 15)

def validate_environment():
    missing = []
    if not PASSWORD:
        missing.append("PASSWORD")
    if not upload_key:
        missing.append("UPLOAD_KEY")
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
    if len(upload_division) > 64:
        raise RuntimeError("ROBLOX_SESSION_INGEST_DIVISION must be 64 characters or fewer")
    if upload_pool == "project" or not POOL_NAME_PATTERN.match(upload_pool):
        raise RuntimeError("ROBLOX_SESSION_INGEST_POOL must use lowercase letters, numbers, underscores, or hyphens")
    log(
        "Configuration loaded",
        display=os.getenv("DISPLAY", "<missing>"),
        upload_url=upload_url,
        ingest_division=upload_division,
        ingest_pool=upload_pool,
        upload_enqueue_timeout_seconds=upload_enqueue_timeout_seconds,
        upload_key=secret_summary(upload_key),
        password=secret_summary(PASSWORD),
        artifacts=ARTIFACT_DIR,
    )

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
        random_sleep()
        
        try:
            success_div = driver.find_element(By.XPATH, "//div[contains(@class, 'has-success') and input[@id='signup-username']]")
            if success_div:
                print(f"Username {username} accepted.")
                break
        except Exception:
            pass
        
        try:
            error_div = driver.find_element(By.XPATH, "//div[contains(@class, 'has-error') and input[@id='signup-username']]")
            if error_div:
                print(f"Username {username} rejected, trying again.")
                username_input.send_keys(Keys.CONTROL + "a")
                username_input.send_keys(Keys.DELETE)
        except Exception:
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
    except Exception:
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
        time.sleep(5)

        drv.switch_to.frame("challenge-frame")

        password_input_box = wait.until(EC.presence_of_element_located((By.ID, "two-step-verification-code-input")))
        password_input_box.send_keys(PASSWORD)
        random_sleep(.5, 1.2)

        verify_button = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'button.btn-cta-md.modal-modern-footer-button[aria-label="Verify"]')))
        verify_button.click()
  
        drv.switch_to.default_content()

        time.sleep(3)


    except Exception as e:
        report_exception("account-protection", e, drv)
        return False

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
                log("Verification link found", url=redacted_url(link))
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


def poll_for_captcha(driver, timeout_seconds=120):
    started = time.time()
    while True: 
        if "https://www.roblox.com/home" in driver.current_url: 
            break
        if time.time() - started > timeout_seconds:
            raise TimeoutError(f"Timed out waiting for signup completion after {timeout_seconds}s")

        try:
            driver.find_element(By.CSS_SELECTOR, 'iframe[title="Verification challenge"], iframe[src*="arkoselabs"]')
            raise RuntimeError("Detected Roblox captcha during signup")
        except Exception as exc:
            if isinstance(exc, RuntimeError):
                raise

        try:
            driver.find_element(By.CSS_SELECTOR, 'div#GeneralErrorText[role="button"][aria-label="dismiss general error"]')
            raise RuntimeError("Detected Roblox general signup error")
        except Exception as exc:
            if isinstance(exc, RuntimeError):
                raise

        time.sleep(0.5)

def response_body_preview(response, max_chars=2000):
    text = response.text or ""
    text = text.replace("\r", "\\r").replace("\n", "\\n")
    if len(text) > max_chars:
        return text[:max_chars] + "...<truncated>"
    return text

def parse_upload_payload(response):
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Upload returned non-JSON response: status={response.status_code} "
            f"content_type={response.headers.get('content-type')} "
            f"body={response_body_preview(response)}"
        ) from exc

def upload_session_cookie(cookie):
    headers = {"x-session-ingest-key": upload_key}
    response = requests.post(
        upload_url,
        json={
            "cookie": cookie,
            "division": upload_division,
            "pool": upload_pool,
        },
        headers=headers,
        timeout=upload_enqueue_timeout_seconds,
    )

    log(
        "Upload response received",
        status=response.status_code,
        content_type=response.headers.get("content-type"),
        body=response_body_preview(response),
    )

    payload = parse_upload_payload(response)
    if response.status_code == 202:
        job = payload.get("job") or {}
        status_url = job.get("status_url") or response.headers.get("location")
        log(
            "Roblox session import queued",
            job_id=job.get("id") or "<unknown>",
            status=job.get("status") or "<unknown>",
            status_url=status_url or "<missing>",
        )
        return payload

    if 200 <= response.status_code < 300:
        return payload

    raise RuntimeError(
        f"Failed to upload cookie: status={response.status_code} "
        f"body={response_body_preview(response)}"
    )


def main():
    driver = None

    try:
        set_step("validate-environment")
        validate_environment()
        if USE_CHROME:
            set_step("browser-start-chrome")
            import undetected_chromedriver as uc
            opts = uc.ChromeOptions()
            opts.add_argument("--use-fake-ui-for-media-stream")
            driver = uc.Chrome(options=opts)
        else:
            set_step("browser-start-firefox")
            from undetected_geckodriver import Firefox
            from selenium.webdriver.firefox.options import Options as FxOptions
            opts = FxOptions()
            opts.set_preference("permissions.default.camera", 1)
            opts.set_preference("permissions.default.microphone", 1)
            opts.set_preference("media.navigator.permission.disabled", True)
            opts.set_preference("media.getusermedia.insecure.enabled", True)
            driver = Firefox(options=opts)

        log("Browser initialized")
        set_step("open-signup")
        driver.get("https://www.roblox.com/CreateAccount")
        log("Accessed Roblox account creation page", url=redacted_url(driver.current_url))

        set_step("fill-signup")
        fill_out_page(driver)

        set_step("wait-signup-result")
        poll_for_captcha(driver)

        set_step("account-protection")
        success = kill_account_protection(driver)

        set_step("email-verification")
        verified = verify_email_address(driver)

        if verified:
            print("Email verified.", flush=True)
        else:
            print("Email verification failed.", flush=True)

        age_verified = False # age_verify(driver)

        if success:
            set_step("session-upload")
            roblosecurity_cookie = driver.get_cookie('.ROBLOSECURITY')
            if not upload_key:
                raise RuntimeError("UPLOAD_KEY is required to upload Roblox sessions")
            if not roblosecurity_cookie or not roblosecurity_cookie.get("value"):
                raise RuntimeError(".ROBLOSECURITY cookie was not found in the browser session")

            log(
                "Uploading Roblox session",
                upload_url=upload_url,
                ingest_division=upload_division,
                ingest_pool=upload_pool,
                cookie=secret_summary(roblosecurity_cookie["value"]),
            )
            
            payload = upload_session_cookie(roblosecurity_cookie["value"])
            session = payload.get("session") or {}
            if session:
                print(
                    "Cookie uploaded successfully.",
                    f"session_id={session.get('session_id')}",
                    f"username={session.get('username')}",
                    f"status={session.get('status')}",
                    flush=True,
                )
            else:
                job = payload.get("job") or {}
                print(
                    "Cookie import queued.",
                    f"job_id={job.get('id')}",
                    f"status={job.get('status')}",
                    f"status_url={job.get('status_url')}",
                    flush=True,
                )
        else:
            log("Account protection failed; retrying with a fresh browser")
            driver.quit()
            main()
            return
    except Exception as exc:
        report_exception("generator", exc, driver)
        raise
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            print("program closed, but webdriver already shutdown", flush=True)

while True: 
    try: 
        main()
    except KeyboardInterrupt:
        exit()
