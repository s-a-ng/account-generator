
import os
import hashlib
import getpass
import requests
import re
import random
import string
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlunparse

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from pymailtm import Account
from ageverify import AgeVerificationConfig, verify_age
from username_generator import generate_username
from session_context import (
    inspect_hba_keypair,
    install_hba_request_observer,
    seed_hba_keypair,
)

ARTIFACT_DIR = Path(os.getenv("GENERATOR_ARTIFACT_DIR", "artifacts/generator"))
CURRENT_STEP = "startup"
CREATE_ACCOUNT_URL = "https://www.roblox.com/CreateAccount"
ACCOUNT_SETTINGS_URL = "https://www.roblox.com/my/account#!/info"
MAX_SIGNUP_RELOADS = 5


class SignupRetry(RuntimeError):
    pass

class CaptchaDetected(RuntimeError):
    pass

class SessionImportFailed(RuntimeError):
    pass

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

def env_int(name, default):
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero")
    return value

def env_nonnegative_int(name, default):
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < 0:
        raise RuntimeError(f"{name} must be zero or greater")
    return value

def env_bool(name, default):
    raw = os.getenv(name, str(default)).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(
        f"{name} must be one of: 1, 0, true, false, yes, no, on, off"
    )

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
upload_import_timeout_seconds = env_float("UPLOAD_IMPORT_TIMEOUT_SECONDS", 90)
upload_import_poll_seconds = env_float("UPLOAD_IMPORT_POLL_SECONDS", 2)
roblox_page_retry_attempts = env_int("ROBLOX_PAGE_RETRY_ATTEMPTS", 5)
generator_retry_attempts = env_int("GENERATOR_RETRY_ATTEMPTS", 5)
generator_max_successes = env_nonnegative_int("GENERATOR_MAX_SUCCESSES", 0)
age_verification_enabled = env_bool("AGE_VERIFICATION_ENABLED", True)

hba_material = None

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
    age_verification_config = None
    if age_verification_enabled:
        age_verification_config = AgeVerificationConfig.from_environment()
        age_verification_config.validate_runtime()
    log(
        "Configuration loaded",
        display=os.getenv("DISPLAY", "<missing>"),
        upload_url=upload_url,
        ingest_division=upload_division,
        ingest_pool=upload_pool,
        upload_enqueue_timeout_seconds=upload_enqueue_timeout_seconds,
        upload_import_timeout_seconds=upload_import_timeout_seconds,
        upload_import_poll_seconds=upload_import_poll_seconds,
        roblox_page_retry_attempts=roblox_page_retry_attempts,
        generator_retry_attempts=generator_retry_attempts,
        generator_max_successes=generator_max_successes or "until-captcha",
        age_verification_enabled=age_verification_enabled,
        fake_cam_video=(
            age_verification_config.video_path
            if age_verification_config is not None
            else "<disabled>"
        ),
        fake_cam_device=(
            age_verification_config.loopback_device
            if age_verification_config is not None
            else "<disabled>"
        ),
        upload_key=secret_summary(upload_key),
        password=secret_summary(PASSWORD),
        artifacts=ARTIFACT_DIR,
    )

def random_sleep(min = 0.3, max = 0.8):
    time.sleep(random.uniform(min, max))

def is_roblox_request_error_page(driver):
    try:
        current_url = driver.current_url or ""
        page_source = (driver.page_source or "").lower()
    except Exception:
        return False
    return (
        "request-error" in current_url
        or ("something went wrong" in page_source and "unexpected error occurred" in page_source)
    )

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
    last_error = None
    for attempt in range(1, roblox_page_retry_attempts + 1):
        driver.get(ACCOUNT_SETTINGS_URL)
        log(
            "Opened account settings page",
            attempt=f"{attempt}/{roblox_page_retry_attempts}",
            url=redacted_url(driver.current_url),
        )
        wait = WebDriverWait(driver, 30)

        if is_roblox_request_error_page(driver):
            log("Roblox account settings returned request error; reloading", attempt=attempt)
            random_sleep(1.5, 3.0)
            continue

        try:
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
            return
        except TimeoutException as exc:
            last_error = exc
            if is_roblox_request_error_page(driver):
                log("Roblox account settings became request error; reloading", attempt=attempt)
                random_sleep(1.5, 3.0)
                continue
            raise

    raise RuntimeError(f"Failed to load Roblox account settings after {roblox_page_retry_attempts} attempts") from last_error


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


def poll_for_captcha(driver, timeout_seconds=120):
    started = time.time()
    while True: 
        if "https://www.roblox.com/home" in driver.current_url: 
            break
        if time.time() - started > timeout_seconds:
            raise SignupRetry(f"Timed out waiting for signup completion after {timeout_seconds}s")

        try:
            driver.find_element(By.CSS_SELECTOR, 'iframe[title="Verification challenge"], iframe[src*="arkoselabs"]')
            raise CaptchaDetected("Detected Roblox captcha during signup")
        except Exception as exc:
            if isinstance(exc, RuntimeError):
                raise

        try:
            driver.find_element(By.CSS_SELECTOR, 'div#GeneralErrorText[role="button"][aria-label="dismiss general error"]')
            raise SignupRetry("Detected Roblox general signup error")
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

def import_status_url(job):
    job_id = job.get("id")
    status_url = job.get("status_url")

    if status_url:
        parsed = urlparse(status_url)
        upload_parsed = urlparse(upload_url)
        if parsed.netloc and upload_parsed.netloc and parsed.netloc == upload_parsed.netloc:
            return urlunparse((
                upload_parsed.scheme or parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            ))
        return status_url

    if not job_id:
        return None

    upload_parsed = urlparse(upload_url)
    return urlunparse((
        upload_parsed.scheme,
        upload_parsed.netloc,
        "/api/internal/roblox-sessions/import-status",
        "",
        urlencode({"job_id": job_id}),
        "",
    ))

def poll_upload_import(job):
    status_url = import_status_url(job)
    job_id = job.get("id") or "<unknown>"
    if not status_url:
        raise RuntimeError("Upload queued but no import status URL or job id was returned")

    headers = {"x-session-ingest-key": upload_key}
    deadline = time.time() + upload_import_timeout_seconds
    last_status = None

    while True:
        response = requests.get(
            status_url,
            headers=headers,
            timeout=upload_enqueue_timeout_seconds,
        )
        payload = parse_upload_payload(response)

        if response.status_code != 200:
            raise RuntimeError(
                f"Import status request failed: status={response.status_code} "
                f"body={response_body_preview(response)}"
            )

        current_job = payload.get("job") or {}
        status = current_job.get("status") or "<unknown>"
        if status != last_status:
            error = payload.get("error") or current_job.get("error") or {}
            session = payload.get("session") or current_job.get("session") or {}
            log(
                "Roblox session import status",
                job_id=job_id,
                status=status,
                error_code=error.get("code") or None,
                error_message=error.get("message") or None,
                error_details=error.get("details") or None,
                session_id=session.get("session_id") or None,
                username=session.get("username") or None,
            )
            last_status = status

        if status == "succeeded":
            return payload

        if status == "failed":
            error = payload.get("error") or current_job.get("error") or {}
            raise RuntimeError(
                "Roblox session import failed: "
                f"code={error.get('code') or '<unknown>'} "
                f"message={error.get('message') or '<missing>'}"
            )

        if time.time() >= deadline:
            raise RuntimeError(
                f"Timed out waiting for Roblox session import job {job_id}; "
                f"last_status={status}"
            )

        time.sleep(upload_import_poll_seconds)

def upload_session_cookie(cookie):
    if not hba_material:
        raise RuntimeError("HBA material is required before uploading Roblox sessions")

    headers = {"x-session-ingest-key": upload_key}
    payload = {
        "cookie": cookie,
        "division": upload_division,
        "pool": upload_pool,
    }
    payload.update(hba_material.upload_payload())

    response = requests.post(
        upload_url,
        json=payload,
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
        job = dict(payload.get("job") or {})
        status_url = job.get("status_url") or response.headers.get("location")
        if status_url:
            job["status_url"] = status_url
        log(
            "Roblox session import queued",
            job_id=job.get("id") or "<unknown>",
            status=job.get("status") or "<unknown>",
            status_url=status_url or "<missing>",
        )
        return poll_upload_import(job)

    if 200 <= response.status_code < 300:
        return payload

    raise RuntimeError(
        f"Failed to upload cookie: status={response.status_code} "
        f"body={response_body_preview(response)}"
    )


def create_account(driver):
    global hba_material

    if not PASSWORD:
        raise RuntimeError("PASSWORD is required to create an account")

    for signup_reload in range(0, MAX_SIGNUP_RELOADS + 1):
        set_step("open-signup")
        driver.get(CREATE_ACCOUNT_URL)
        log(
            "Accessed Roblox account creation page",
            attempt=f"{signup_reload + 1}/{MAX_SIGNUP_RELOADS + 1}",
            url=redacted_url(driver.current_url),
        )

        if hba_material is None:
            set_step("seed-hba")
            hba_material = seed_hba_keypair(driver)
            log(
                "Seeded browser HBA key",
                public_key=secret_summary(hba_material.public_key_spki),
                indexed_db=hba_material.db_name,
                object_store=hba_material.object_store_name,
                key=hba_material.key_name,
            )

        install_hba_request_observer(driver)

        set_step("fill-signup")
        fill_out_page(driver)

        set_step("wait-signup-result")
        try:
            poll_for_captcha(driver)
            break
        except SignupRetry as exc:
            if signup_reload >= MAX_SIGNUP_RELOADS:
                raise RuntimeError(
                    f"Exceeded {MAX_SIGNUP_RELOADS} signup page reloads"
                ) from exc
            log(
                "Reloading signup page after retryable signup failure",
                reload=f"{signup_reload + 1}/{MAX_SIGNUP_RELOADS}",
                reason=exc,
            )
            random_sleep(1.5, 3.0)

    roblosecurity_cookie = driver.get_cookie(".ROBLOSECURITY")
    if not roblosecurity_cookie or not roblosecurity_cookie.get("value"):
        raise RuntimeError(
            ".ROBLOSECURITY cookie was not found after account creation"
        )
    log(
        "Account session created",
        cookie=secret_summary(roblosecurity_cookie["value"]),
    )
    return roblosecurity_cookie["value"]


def main():
    global hba_material
    driver = None
    hba_material = None

    try:
        set_step("validate-environment")
        validate_environment()
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
        create_account(driver)

        set_step("email-verification")
        verified = verify_email_address(driver)
        if verified:
            print("Email verified.", flush=True)
        else:
            print("Email verification failed.", flush=True)

        if age_verification_enabled:
            set_step("age-verification")
            age_verification_cookie = driver.get_cookie(".ROBLOSECURITY")
            if not age_verification_cookie or not age_verification_cookie.get("value"):
                raise RuntimeError(
                    ".ROBLOSECURITY cookie was not found before age verification"
                )
            verify_age(
                driver,
                age_verification_cookie["value"],
                config=AgeVerificationConfig.from_environment(),
                logger=log,
            )

        set_step("verify-hba")
        seeded_hba_material = hba_material
        current_hba_material, hba_observations = inspect_hba_keypair(
            driver,
            seeded_hba_material,
        )
        observed_public_keys = [
            observation.get("client_public_key")
            for observation in hba_observations
            if isinstance(observation, dict) and observation.get("client_public_key")
        ]
        observed_public_key = observed_public_keys[-1] if observed_public_keys else None
        if observed_public_key == seeded_hba_material.public_key_spki:
            hba_material = seeded_hba_material
        elif observed_public_key == current_hba_material.public_key_spki or observed_public_key is None:
            hba_material = current_hba_material
        else:
            raise RuntimeError(
                "Roblox signup used an HBA key that is no longer available in IndexedDB"
            )
        log(
            "Verified browser HBA key",
            key_changed=(
                current_hba_material.public_key_spki
                != seeded_hba_material.public_key_spki
            ),
            observed_intents=len(observed_public_keys),
            observed_key_matches_selected=(
                observed_public_key is None
                or observed_public_key == hba_material.public_key_spki
            ),
            selected_public_key=secret_summary(hba_material.public_key_spki),
        )

        set_step("session-capture")
        roblosecurity_cookie = driver.get_cookie('.ROBLOSECURITY')
        if not roblosecurity_cookie or not roblosecurity_cookie.get("value"):
            raise RuntimeError(".ROBLOSECURITY cookie was not found in the browser session")

        set_step("session-upload")
        log(
            "Uploading Roblox session",
            upload_url=upload_url,
            ingest_division=upload_division,
            ingest_pool=upload_pool,
            cookie=secret_summary(roblosecurity_cookie["value"]),
            hba_material=bool(hba_material),
        )

        try:
            payload = upload_session_cookie(roblosecurity_cookie["value"])
        except Exception as exc:
            raise SessionImportFailed(str(exc)) from exc
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
        return True
    except CaptchaDetected:
        log("Captcha detected", step=CURRENT_STEP)
        save_browser_artifacts(driver, f"captcha-{CURRENT_STEP}")
        raise
    except Exception as exc:
        report_exception("generator", exc, driver)
        raise
    finally:
        try:
            if driver is not None:
                driver.quit()
        except Exception:
            print("program closed, but webdriver already shutdown", flush=True)

def run_loop(generate=None, max_successes=None):
    generate = generate or main
    max_successes = generator_max_successes if max_successes is None else max_successes
    successes = 0
    failures = 0
    while True:
        try:
            if generate():
                successes += 1
                failures = 0
                if max_successes and successes >= max_successes:
                    log("Stopping generator after success limit", successes=successes)
                    return successes
        except KeyboardInterrupt:
            log("Stopping generator after interrupt", successes=successes)
            return successes
        except CaptchaDetected as exc:
            log("Stopping generator after captcha", successes=successes, error=exc)
            return successes
        except SessionImportFailed as exc:
            log(
                "Stopping generator after session import failure",
                successes=successes,
                error=exc,
            )
            raise
        except Exception as exc:
            failures += 1
            if failures > generator_retry_attempts:
                log(
                    "Stopping generator after retry limit",
                    successes=successes,
                    failures=failures,
                    retries=generator_retry_attempts,
                    error=exc,
                )
                raise RuntimeError(f"Exceeded {generator_retry_attempts} generator retries") from exc
            log(
                "Retrying generator after failure",
                successes=successes,
                retry=f"{failures}/{generator_retry_attempts}",
                error=exc,
            )

if __name__ == "__main__":
    run_loop()
