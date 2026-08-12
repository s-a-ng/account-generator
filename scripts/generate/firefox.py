import getpass
import hashlib
import os
import random
import re
import string
import time
import traceback
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import requests
from ageverify import AgeVerificationConfig, verify_age
from browser_proxy import BrowserProxyBridge, configure_firefox_proxy
from pymailtm import Account
from pymailtm.pymailtm import CouldNotGetMessagesException
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from session_context import (
    browser_refresh_session,
    inspect_hba_keypair,
    seed_hba_keypair,
)
from username_generator import generate_username

ARTIFACT_DIR = Path(os.getenv("GENERATOR_ARTIFACT_DIR", "artifacts/generator"))
CURRENT_STEP = "startup"
CREATE_ACCOUNT_URL = "https://www.roblox.com/CreateAccount"
LOGIN_URL = "https://www.roblox.com/login"
ACCOUNT_SETTINGS_URL = "https://www.roblox.com/my/account#!/info"
USERNAME_VALIDATION_URL = "https://auth.roblox.com/v1/usernames/validate"
MAX_SIGNUP_RELOADS = 5
MAX_USERNAME_ATTEMPTS = 25
USERNAME_VALIDATION_TIMEOUT_MS = 3000
ROBLOX_WEB_USER_AGENT = "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:153.0) Gecko/20100101 Firefox/153.0"
USERNAME_VALIDATION_SCRIPT = """
const [url, payload, timeoutMs, done] = arguments;
const controller = new AbortController();
const timeout = setTimeout(() => controller.abort(), timeoutMs);

async function post(token) {
    const headers = {"Content-Type": "application/json"};
    if (token) {
        headers["X-CSRF-TOKEN"] = token;
    }
    return fetch(url, {
        method: "POST",
        credentials: "include",
        headers,
        body: JSON.stringify(payload),
        signal: controller.signal,
    });
}

(async () => {
    let token = window.accountGeneratorXsrfToken;
    let response = await post(token);
    if (response.status === 403) {
        token = response.headers.get("X-CSRF-TOKEN");
        if (!token) {
            throw new Error("Roblox did not return an X-CSRF token");
        }
        window.accountGeneratorXsrfToken = token;
        response = await post(token);
    }
    const body = await response.json();
    done({status: response.status, body, error: null});
})().catch(error => {
    done({status: 0, body: null, error: error.message || String(error)});
}).finally(() => clearTimeout(timeout));
"""
ADD_EMAIL_BUTTON_XPATH = (
    "//div[contains(@class, 'settings-text-field-container')]"
    "[.//span[text()='Email']]//button[contains(@class, 'foundation-web-button') "
    "and .//span[normalize-space()='Add']]"
)
SUBMIT_EMAIL_BUTTON_XPATH = (
    "//button[@class='modal-full-width-button btn-primary-md btn-min-width' and text()='Add Email']"
)


class SignupRetry(RuntimeError):
    pass


class CaptchaDetected(RuntimeError):
    pass


class SessionImportFailed(RuntimeError):
    pass


class BrowserSessionRefreshDiagnosticFailed(RuntimeError):
    pass


def utc_timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_field(value):
    return str(value).replace("\n", "\\n").replace("\r", "\\r")


def log(message, **fields):
    suffix = " ".join(f"{key}={safe_field(value)}" for key, value in fields.items())
    suffix = f" {suffix}" if suffix else ""
    print(f"[{utc_timestamp()}] {message}{suffix}", flush=True)


def set_step(name):
    global CURRENT_STEP
    CURRENT_STEP = name
    log("STEP", name=name)


def github_escape(value):
    return str(value).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def github_error(message):
    if os.getenv("GITHUB_ACTIONS"):
        print(f"::error::{github_escape(message)}", flush=True)


def secret_summary(value):
    if not value:
        return "<missing>"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    return f"<set len={len(value)} sha256={digest}>"


def proxy_summary(value):
    text = str(value or "")
    if not text:
        return {"present": False}
    parsed = urlparse(text)
    host = parsed.hostname or ""
    return {
        "present": True,
        "scheme": parsed.scheme or None,
        "host_sha256": (hashlib.sha256(host.encode("utf-8")).hexdigest()[:10] if host else None),
        "port": parsed.port,
        "has_auth": bool(parsed.username or parsed.password),
    }


def redacted_url(url):
    if not url:
        return "<unknown>"
    try:
        parsed = urlparse(url)
        query = "<redacted>" if parsed.query else ""
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, ""))
    except ValueError:
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


def env_int(name, default, minimum=1):
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}")
    return value


def env_bool(name, default):
    raw = os.getenv(name, str(default)).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be one of: 1, 0, true, false, yes, no, on, off")


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
        log(
            "Browser state",
            url=redacted_url(driver.current_url),
            title=driver.title,
        )
    except WebDriverException as exc:
        log("Could not read browser state", error=exc)
    try:
        screenshot = artifact_path(label, "png")
        driver.save_screenshot(str(screenshot))
        log("Saved browser screenshot", path=screenshot)
    except (OSError, WebDriverException) as exc:
        log("Could not save browser screenshot", error=exc)
    try:
        write_artifact(f"{label}-page", "html", driver.page_source or "")
    except (OSError, WebDriverException) as exc:
        log("Could not save page source", error=exc)


def report_exception(context, exc, driver=None):
    log(
        "Attempt failed",
        context=context,
        step=CURRENT_STEP,
        error=f"{type(exc).__name__}: {exc}",
    )
    trace = traceback.format_exc()
    print(trace, flush=True)
    with suppress(OSError):
        write_artifact(f"{context}-traceback", "txt", trace)
    save_browser_artifacts(driver, f"{context}-{CURRENT_STEP}")


def mail_username():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=10))


def generate_email(password):
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            log("Fetching mail.tm domains", attempt=f"{attempt}/{max_attempts}")
            domain_response = requests.get("https://api.mail.tm/domains", timeout=10)
            domain_response.raise_for_status()
            domains = domain_response.json()["hydra:member"]
            if not domains:
                raise RuntimeError("mail.tm returned no domains")

            address = f"{mail_username()}@{random.choice(domains)['domain']}"

            account_response = requests.post(
                "https://api.mail.tm/accounts",
                json={"address": address, "password": password},
                timeout=10,
            )
            account_response.raise_for_status()
            account = account_response.json()
            log("Created mail.tm account", address=address, account_id=account["id"])
            return address, password, account["id"]
        except requests.RequestException as error:
            log(
                "mail.tm request failed",
                error=error,
                attempt=f"{attempt}/{max_attempts}",
            )
            if attempt < max_attempts:
                time.sleep(2)

    raise RuntimeError(f"Failed to create email after {max_attempts} attempts")


try:
    os.getlogin()
except OSError:
    os.getlogin = getpass.getuser


def generate_random_birthdate():
    month = random.choice(
        [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
    )
    day = random.randint(1, 26)
    year = str(random.randint(1995, 2002))
    return month, day, year


PASSWORD = os.getenv("PASSWORD")
upload_key = os.getenv("UPLOAD_KEY")
upload_url = os.getenv("UPLOAD_URL", "https://command.botted.org/api/internal/roblox-sessions/import")
upload_division = os.getenv("ROBLOX_SESSION_INGEST_DIVISION", "default").strip() or "default"
upload_pool = os.getenv("ROBLOX_SESSION_INGEST_POOL", "global").strip().lower() or "global"
POOL_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
BROWSER_ENGINES = {"undetected_geckodriver", "seleniumbase_uc"}
upload_enqueue_timeout_seconds = env_float("UPLOAD_ENQUEUE_TIMEOUT_SECONDS", 15)
upload_import_timeout_seconds = env_float("UPLOAD_IMPORT_TIMEOUT_SECONDS", 90)
upload_import_poll_seconds = env_float("UPLOAD_IMPORT_POLL_SECONDS", 2)
roblox_page_retry_attempts = env_int("ROBLOX_PAGE_RETRY_ATTEMPTS", 5)
generator_retry_attempts = env_int("GENERATOR_RETRY_ATTEMPTS", 5)
generator_max_successes = env_int("GENERATOR_MAX_SUCCESSES", 0, minimum=0)
age_verification_enabled = env_bool("AGE_VERIFICATION_ENABLED", True)
browser_session_refresh_diagnostic = env_bool("BROWSER_SESSION_REFRESH_DIAGNOSTIC", False)
session_refresh_diagnostic_username = os.getenv("SESSION_REFRESH_DIAGNOSTIC_USERNAME", "").strip()
selenium_proxy_enabled = env_bool("SELENIUM_PROXY_ENABLED", False)
browser_engine = os.getenv("BROWSER_ENGINE", "undetected_geckodriver").strip().lower()


def validate_environment():
    if not PASSWORD:
        raise RuntimeError("PASSWORD is required")
    if not upload_key:
        raise RuntimeError("UPLOAD_KEY is required")
    if browser_engine not in BROWSER_ENGINES:
        raise RuntimeError(f"BROWSER_ENGINE must be one of: {', '.join(sorted(BROWSER_ENGINES))}")
    if len(upload_division) > 64:
        raise RuntimeError("ROBLOX_SESSION_INGEST_DIVISION must be 64 characters or fewer")
    if upload_pool == "project" or not POOL_NAME_PATTERN.match(upload_pool):
        raise RuntimeError("ROBLOX_SESSION_INGEST_POOL must use lowercase letters, numbers, underscores, or hyphens")
    if session_refresh_diagnostic_username and not browser_session_refresh_diagnostic:
        raise RuntimeError("SESSION_REFRESH_DIAGNOSTIC_USERNAME requires BROWSER_SESSION_REFRESH_DIAGNOSTIC")
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
        browser_session_refresh_diagnostic=browser_session_refresh_diagnostic,
        session_refresh_diagnostic_username=session_refresh_diagnostic_username or "<disabled>",
        selenium_proxy_enabled=selenium_proxy_enabled,
        browser_engine=browser_engine,
        fake_cam_video=(age_verification_config.video_path if age_verification_config is not None else "<disabled>"),
        fake_cam_device=(
            age_verification_config.loopback_device if age_verification_config is not None else "<disabled>"
        ),
        upload_key=secret_summary(upload_key),
        password=secret_summary(PASSWORD),
        artifacts=ARTIFACT_DIR,
    )


def random_sleep(lower=0.3, upper=0.8):
    time.sleep(random.uniform(lower, upper))


def is_roblox_request_error_page(driver):
    current_url = driver.current_url or ""
    page_source = (driver.page_source or "").lower()
    return "request-error" in current_url or (
        "something went wrong" in page_source and "unexpected error occurred" in page_source
    )


def validate_username(driver, username, month, day, year):
    birthday = f"{year}-{time.strptime(month, '%b').tm_mon:02d}-{day:02d}"
    result = driver.execute_async_script(
        USERNAME_VALIDATION_SCRIPT,
        USERNAME_VALIDATION_URL,
        {"username": username, "birthday": birthday, "context": "Signup"},
        USERNAME_VALIDATION_TIMEOUT_MS,
    )
    if result["error"] is not None:
        raise RuntimeError(f"Username validation request failed: {result['error']}")
    if result["status"] != 200:
        raise RuntimeError(f"Username validation returned HTTP {result['status']}")
    code = result["body"]["code"]
    message = result["body"]["message"]
    if not isinstance(code, int) or not isinstance(message, str):
        raise RuntimeError("Username validation returned an invalid response")
    return code == 0, message


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

    password_input = driver.find_element(By.ID, "signup-password")
    password_input.send_keys(PASSWORD)
    print("Password entered.")
    random_sleep()

    username_input = driver.find_element(By.ID, "signup-username")
    signup_button = driver.find_element(By.ID, "signup-button")

    for attempt in range(1, MAX_USERNAME_ATTEMPTS + 1):
        username = generate_username()
        print(f"Attempting username: {username} ({attempt}/{MAX_USERNAME_ATTEMPTS})")
        accepted, message = validate_username(driver, username, month, day, year)
        if accepted:
            username_input.send_keys(username)
            print(f"Username {username} accepted.")
            break
        print(f"Username {username} rejected: {message}")
    else:
        raise SignupRetry(f"Could not find an available username after {MAX_USERNAME_ATTEMPTS} attempts")

    checkboxes = driver.find_elements(By.ID, "signup-checkbox")
    if checkboxes:
        checkboxes[0].click()
        random_sleep()

    signup_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "signup-button")))
    signup_button.click()
    random_sleep()

    print("Signup button clicked.")


def poll_email(email, password, account_id):
    print(f"Polling email for {email}...")
    max_attempts = 300
    account = Account(account_id, email, password)

    for attempt in range(1, max_attempts + 1):
        print(f"Email poll attempt {attempt}/{max_attempts}")
        try:
            messages = account.get_messages()
            if messages:
                print(f"Found {len(messages)} messages.")
                return messages
        except (CouldNotGetMessagesException, requests.RequestException) as error:
            print(f"Error checking email: {error}")
        time.sleep(5)

    print("Email polling timed out.")
    return []


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
            log(
                "Roblox account settings returned request error; reloading",
                attempt=attempt,
            )
            random_sleep(1.5, 3.0)
            continue

        try:
            btn = wait.until(EC.element_to_be_clickable((By.XPATH, ADD_EMAIL_BUTTON_XPATH)))
            btn.click()
            print("Clicked Add button.")
            email_input = wait.until(EC.presence_of_element_located((By.ID, "emailAddress")))
            email_input.send_keys(email)
            print(f"Entered email into modal: {email}")
            random_sleep()

            add_email_btn = wait.until(EC.element_to_be_clickable((By.XPATH, SUBMIT_EMAIL_BUTTON_XPATH)))
            add_email_btn.click()
            print("Clicked Add Email button")
            random_sleep()
            return
        except TimeoutException as exc:
            last_error = exc
            if is_roblox_request_error_page(driver):
                log(
                    "Roblox account settings became request error; reloading",
                    attempt=attempt,
                )
                random_sleep(1.5, 3.0)
                continue
            raise

    raise RuntimeError(
        f"Failed to load Roblox account settings after {roblox_page_retry_attempts} attempts"
    ) from last_error


def verify_email_address(driver):
    email, password, account_id = generate_email(PASSWORD)
    print(f"Generated email: {email}")

    link_email(driver, email)

    messages = poll_email(email, password, account_id)
    if not messages:
        return False

    message = messages[0]
    body = message.text or (message.html[0] if message.html else "")
    if not body:
        print("No email body found.")
        return False

    match = re.search(
        r'https://www\.roblox\.com/account/settings/verify-email\?ticket=[^\s)"]+',
        body,
    )
    if not match:
        print("No verification link found in email body.")
        return False

    link = match.group(0)
    log("Verification link found", url=redacted_url(link))
    driver.get(link)
    return True


def poll_for_captcha(driver, timeout_seconds=120):
    started = time.time()
    while "https://www.roblox.com/home" not in driver.current_url:
        if time.time() - started > timeout_seconds:
            raise SignupRetry(f"Timed out waiting for signup completion after {timeout_seconds}s")

        if driver.find_elements(
            By.CSS_SELECTOR,
            'iframe[title="Verification challenge"], iframe[src*="arkoselabs"]',
        ):
            raise CaptchaDetected("Detected Roblox captcha during signup")

        if driver.find_elements(
            By.CSS_SELECTOR,
            'div#GeneralErrorText[role="button"][aria-label="dismiss general error"]',
        ):
            raise SignupRetry("Detected Roblox general signup error")

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


def control_endpoint(path):
    parsed = urlparse(upload_url)
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def acquire_import_proxy():
    response = requests.post(
        control_endpoint("/api/internal/roblox-sessions/import-proxy"),
        json={"division": upload_division},
        headers={"x-session-ingest-key": upload_key},
        timeout=upload_enqueue_timeout_seconds,
    )
    payload = parse_upload_payload(response)
    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to acquire Selenium proxy: status={response.status_code} body={response_body_preview(response)}"
        )
    proxy = payload["proxy"]
    log("Acquired Selenium proxy", proxy=proxy_summary(proxy))
    return proxy


def preflight_import_proxy(proxy):
    response = requests.get(
        CREATE_ACCOUNT_URL,
        headers={"user-agent": ROBLOX_WEB_USER_AGENT},
        proxies={"http": proxy, "https": proxy},
        timeout=upload_enqueue_timeout_seconds,
    )
    log(
        "Selenium proxy preflight",
        proxy=proxy_summary(proxy),
        status=response.status_code,
        url=redacted_url(response.url),
    )
    if response.status_code >= 500:
        raise RuntimeError(f"Selenium proxy preflight failed with status {response.status_code}")


def poll_upload_import(job):
    job_id = job["id"]
    status_url = job["status_url"]
    headers = {"x-session-ingest-key": upload_key}
    deadline = time.monotonic() + upload_import_timeout_seconds
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
                f"Import status request failed: status={response.status_code} body={response_body_preview(response)}"
            )

        current_job = payload["job"]
        status = current_job["status"]
        if status != last_status:
            error = payload["error"] or current_job["error"]
            session = payload["session"] or current_job["session"]
            log(
                "Roblox session import status",
                job_id=job_id,
                status=status,
                error_code=error["code"] if error else None,
                error_message=error["message"] if error else None,
                session_id=session["session_id"] if session else None,
                username=session["username"] if session else None,
            )
            last_status = status

        if status == "succeeded":
            return payload

        if status == "failed":
            error = payload["error"] or current_job["error"]
            raise RuntimeError(f"Roblox session import failed: code={error['code']} message={error['message']}")

        if time.monotonic() >= deadline:
            raise RuntimeError(f"Timed out waiting for Roblox session import job {job_id}; last_status={status}")

        time.sleep(upload_import_poll_seconds)


def upload_session_cookie(cookie, hba_material, proxy=None):
    if not hba_material:
        raise RuntimeError("HBA material is required before uploading Roblox sessions")

    headers = {"x-session-ingest-key": upload_key}
    payload = {
        "cookie": cookie,
        "division": upload_division,
        "pool": upload_pool,
    }
    if proxy:
        payload["proxy"] = proxy
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
    if response.status_code != 202:
        raise RuntimeError(
            f"Failed to queue session import: status={response.status_code} body={response_body_preview(response)}"
        )

    job = payload["job"]
    log(
        "Roblox session import queued",
        job_id=job["id"],
        status=job["status"],
        status_url=job["status_url"],
    )
    return poll_upload_import(job)


def roblosecurity_cookie(driver, context):
    cookie = driver.get_cookie(".ROBLOSECURITY")
    if cookie is None or not cookie["value"]:
        raise RuntimeError(f".ROBLOSECURITY cookie was not found {context}")
    return cookie["value"]


def create_account(driver):
    if not PASSWORD:
        raise RuntimeError("PASSWORD is required to create an account")

    hba_material = None
    for signup_reload in range(MAX_SIGNUP_RELOADS + 1):
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
            log("Seeded browser HBA key")

        set_step("fill-signup")
        fill_out_page(driver)

        set_step("wait-signup-result")
        try:
            poll_for_captcha(driver)
            break
        except SignupRetry as exc:
            if signup_reload >= MAX_SIGNUP_RELOADS:
                raise RuntimeError(f"Exceeded {MAX_SIGNUP_RELOADS} signup page reloads") from exc
            log(
                "Reloading signup page after retryable signup failure",
                reload=f"{signup_reload + 1}/{MAX_SIGNUP_RELOADS}",
                reason=exc,
            )
            random_sleep(1.5, 3.0)

    cookie = roblosecurity_cookie(driver, "after account creation")
    log("Account session created", cookie=secret_summary(cookie))
    return hba_material


def login_diagnostic_account(driver, username):
    set_step("open-login")
    driver.get(LOGIN_URL)
    log("Opened Roblox login page", url=redacted_url(driver.current_url))

    set_step("seed-hba")
    hba_material = seed_hba_keypair(driver)
    log("Seeded browser HBA key for diagnostic login")

    set_step("login-existing-account")
    wait = WebDriverWait(driver, 20)
    username_input = wait.until(EC.presence_of_element_located((By.ID, "login-username")))
    password_input = wait.until(EC.presence_of_element_located((By.ID, "login-password")))
    username_input.send_keys(username)
    password_input.send_keys(PASSWORD)
    wait.until(EC.element_to_be_clickable((By.ID, "login-button"))).click()

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        cookie = driver.get_cookie(".ROBLOSECURITY")
        if cookie is not None and cookie["value"]:
            log("Diagnostic account login succeeded", username=username)
            return hba_material
        if driver.find_elements(
            By.CSS_SELECTOR,
            'iframe[title="Verification challenge"], iframe[src*="arkoselabs"]',
        ):
            raise CaptchaDetected("Detected Roblox captcha during diagnostic login")
        time.sleep(0.5)

    raise RuntimeError("Timed out waiting for diagnostic account login")


def start_proxy():
    if not selenium_proxy_enabled:
        return None, None

    set_step("acquire-selenium-proxy")
    proxy = acquire_import_proxy()
    preflight_import_proxy(proxy)
    bridge = BrowserProxyBridge(proxy, upload_enqueue_timeout_seconds)
    log("Started local Selenium proxy bridge")
    return proxy, bridge


def start_browser(proxy_bridge):
    set_step("browser-start")
    if browser_engine == "seleniumbase_uc":
        from seleniumbase import Driver

        options = {
            "uc": True,
            "headed": True,
            "window_size": "1920,1080",
        }
        if age_verification_enabled:
            options["chromium_arg"] = "auto-accept-camera-and-microphone-capture"
        if proxy_bridge is not None:
            options["proxy"] = proxy_bridge.url
        driver = Driver(**options)
        log("Browser initialized", engine=browser_engine)
        return driver

    from selenium.webdriver.firefox.options import Options as FxOptions
    from undetected_geckodriver import Firefox

    options = FxOptions()
    options.set_preference("general.useragent.override", ROBLOX_WEB_USER_AGENT)
    options.set_preference("permissions.default.camera", 1)
    options.set_preference("permissions.default.microphone", 1)
    options.set_preference("media.navigator.permission.disabled", True)
    options.set_preference("media.getusermedia.insecure.enabled", True)
    if proxy_bridge is not None:
        configure_firefox_proxy(options, proxy_bridge.url)
    driver = Firefox(options=options)
    log("Browser initialized", engine=browser_engine)
    return driver


def prepare_account(driver):
    if session_refresh_diagnostic_username:
        return login_diagnostic_account(driver, session_refresh_diagnostic_username)

    hba_material = create_account(driver)
    set_step("email-verification")
    print(
        "Email verified." if verify_email_address(driver) else "Email verification failed.",
        flush=True,
    )

    if age_verification_enabled:
        set_step("age-verification")
        verify_age(
            driver,
            roblosecurity_cookie(driver, "before age verification"),
            config=AgeVerificationConfig.from_environment(),
            logger=log,
        )
    return hba_material


def capture_hba_material(driver, seeded):
    set_step("verify-hba")
    current = inspect_hba_keypair(driver, seeded)
    log(
        "Captured browser HBA key",
        key_changed=current.private_key_jwk != seeded.private_key_jwk,
    )
    return current


def run_session_refresh_diagnostic(driver):
    if not browser_session_refresh_diagnostic:
        return

    set_step("browser-session-refresh-diagnostic")
    try:
        result = browser_refresh_session(driver)
    except Exception as error:
        raise BrowserSessionRefreshDiagnosticFailed(
            f"Browser session refresh diagnostic did not complete: {error}"
        ) from error
    log("Browser session refresh diagnostic", **result)
    if not result["ok"]:
        raise BrowserSessionRefreshDiagnosticFailed(f"Browser session refresh diagnostic was rejected: {result}")


def upload_browser_session(driver, proxy, hba_material):
    set_step("session-capture")
    cookie = roblosecurity_cookie(driver, "in the browser session")

    set_step("session-upload")
    log(
        "Uploading Roblox session",
        upload_url=upload_url,
        ingest_division=upload_division,
        ingest_pool=upload_pool,
        cookie=secret_summary(cookie),
        hba_material=bool(hba_material),
        selenium_proxy=proxy_summary(proxy),
    )

    try:
        payload = upload_session_cookie(cookie, hba_material, proxy)
    except Exception as error:
        raise SessionImportFailed(f"Roblox session import failed: {error}") from error

    session = payload["session"]
    print(
        "Cookie uploaded successfully.",
        f"session_id={session['session_id']}",
        f"username={session['username']}",
        f"status={session['status']}",
        flush=True,
    )


def main():
    driver = None
    proxy = None
    proxy_bridge = None

    try:
        set_step("validate-environment")
        validate_environment()
        proxy, proxy_bridge = start_proxy()
        driver = start_browser(proxy_bridge)
        hba_material = prepare_account(driver)
        hba_material = capture_hba_material(driver, hba_material)
        run_session_refresh_diagnostic(driver)
        upload_browser_session(driver, proxy, hba_material)
        return True
    except CaptchaDetected:
        log("Captcha detected", step=CURRENT_STEP)
        save_browser_artifacts(driver, f"captcha-{CURRENT_STEP}")
        raise
    except Exception as exc:
        report_exception("generator", exc, driver)
        raise
    finally:
        if driver is not None:
            with suppress(Exception):
                driver.quit()
        if proxy_bridge is not None:
            with suppress(Exception):
                proxy_bridge.close()


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
        except (SessionImportFailed, BrowserSessionRefreshDiagnosticFailed) as exc:
            log(
                "Stopping generator after fatal failure",
                successes=successes,
                error=exc,
            )
            github_error(str(exc))
            raise
        except Exception as exc:
            if session_refresh_diagnostic_username:
                log(
                    "Stopping diagnostic after first failure",
                    successes=successes,
                    error=exc,
                )
                github_error(f"Generator diagnostic failed: {exc}")
                raise
            failures += 1
            if failures > generator_retry_attempts:
                log(
                    "Stopping generator after retry limit",
                    successes=successes,
                    failures=failures,
                    retries=generator_retry_attempts,
                    error=exc,
                )
                github_error(f"Generator exceeded {generator_retry_attempts} retries: {exc}")
                raise RuntimeError(f"Exceeded {generator_retry_attempts} generator retries") from exc
            log(
                "Retrying generator after failure",
                successes=successes,
                retry=f"{failures}/{generator_retry_attempts}",
                error=exc,
            )


if __name__ == "__main__":
    run_loop()
