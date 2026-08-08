"""Roblox age-verification support for the Firefox account generator."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import requests
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

START_VERIFICATION_URL = (
    "https://apis.roblox.com/age-verification-service/v1/"
    "persona-id-verification/start-verification"
)
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:153.0) "
    "Gecko/20100101 Firefox/153.0"
)

SUCCESS_STATUSES = {"approved", "completed"}
FAILURE_STATUSES = {"declined", "expired", "failed"}
INQUIRY_STATUS_SCRIPT = r"""
const done = arguments[0];
const inquiryId = new URL(window.location.href).searchParams.get("inquiry-id");
if (!inquiryId) {
  done({status: null, httpStatus: null, error: "missing inquiry-id"});
} else {
  const endpoint = `/api/internal/verify/v1/inquiries/${
    encodeURIComponent(inquiryId)
  }`;
  fetch(endpoint, {credentials: "include"})
    .then(async (response) => {
      const payload = await response.json();
      done({
        status: payload?.data?.attributes?.status || null,
        httpStatus: response.status,
        error: null,
      });
    })
    .catch((error) => done({
      status: null,
      httpStatus: null,
      error: `${error.name}: ${error.message}`,
    }));
}
"""

LogFunction = Callable[..., None]


class AgeVerificationError(RuntimeError):
    """Raised when the age-verification workflow cannot be completed."""


@dataclass(frozen=True)
class AgeVerificationConfig:
    video_path: Path
    loopback_device: Path
    completion_timeout_seconds: float = 600
    request_timeout_seconds: float = 20
    webcam_startup_seconds: float = 1

    def validate_runtime(self) -> str:
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path is None:
            raise AgeVerificationError("ffmpeg was not found on PATH")
        if not self.video_path.is_file():
            raise AgeVerificationError(
                f"Fake-camera video does not exist: {self.video_path}"
            )
        if not self.loopback_device.exists():
            raise AgeVerificationError(
                f"Loopback camera does not exist: {self.loopback_device}; "
                "load v4l2loopback or set FAKE_CAM_DEVICE"
            )
        return ffmpeg_path

    @classmethod
    def from_environment(cls) -> "AgeVerificationConfig":
        return cls(
            video_path=Path(os.getenv("FAKE_CAM_VIDEO", "TEST.mov")).expanduser(),
            loopback_device=Path(
                os.getenv("FAKE_CAM_DEVICE", "/dev/video1")
            ).expanduser(),
            completion_timeout_seconds=_positive_float(
                "AGE_VERIFICATION_TIMEOUT_SECONDS", 600
            ),
            request_timeout_seconds=_positive_float(
                "AGE_VERIFICATION_REQUEST_TIMEOUT_SECONDS", 20
            ),
            webcam_startup_seconds=_positive_float(
                "FAKE_CAM_STARTUP_SECONDS", 1
            ),
        )


def _positive_float(name: str, default: float) -> float:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise AgeVerificationError(f"{name} must be a number") from exc
    if value <= 0:
        raise AgeVerificationError(f"{name} must be greater than zero")
    return value


def _log(logger: LogFunction | None, message: str, **fields: object) -> None:
    if logger is not None:
        logger(message, **fields)
        return

    suffix = " ".join(f"{key}={value}" for key, value in fields.items())
    print(f"{message}{' ' + suffix if suffix else ''}", flush=True)


class FakeWebcam:
    """Streams a video into a v4l2 loopback device for one verification run."""

    def __init__(
        self,
        config: AgeVerificationConfig,
        logger: LogFunction | None = None,
    ) -> None:
        self.config = config
        self.logger = logger
        self.process: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        if self.process is not None and self.process.poll() is None:
            return

        ffmpeg_path = self.config.validate_runtime()

        command = [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-re",
            "-stream_loop",
            "-1",
            "-i",
            str(self.config.video_path),
            "-vf",
            "scale=1280:720,noise=alls=5:allf=t+u,format=yuyv422",
            "-r",
            "30",
            "-c:v",
            "rawvideo",
            "-pix_fmt",
            "yuyv422",
            "-f",
            "v4l2",
            str(self.config.loopback_device),
        ]
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            time.sleep(self.config.webcam_startup_seconds)
            return_code = self.process.poll()
            if return_code is not None:
                raise AgeVerificationError(
                    "ffmpeg exited during fake-camera startup "
                    f"with status {return_code}"
                )
        except BaseException:
            self.stop()
            raise

        _log(
            self.logger,
            "Fake camera started",
            video=self.config.video_path,
            device=self.config.loopback_device,
        )

    def stop(self) -> None:
        process = self.process
        self.process = None
        if process is None or process.poll() is not None:
            return

        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        _log(self.logger, "Fake camera stopped")

    def __enter__(self) -> "FakeWebcam":
        self.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.stop()


def _cookie_header(cookie: str) -> str:
    cookie = cookie.strip()
    if not cookie:
        raise AgeVerificationError(".ROBLOSECURITY cookie is empty")
    if "\r" in cookie or "\n" in cookie:
        raise AgeVerificationError(".ROBLOSECURITY cookie contains invalid characters")
    if cookie.startswith(".ROBLOSECURITY="):
        return cookie
    return f".ROBLOSECURITY={cookie}"


def request_verification_link(
    cookie: str,
    *,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout_seconds: float = 20,
) -> str:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": user_agent,
            "Cookie": _cookie_header(cookie),
        }
    )
    payload = {
        "generateLink": True,
        "ageEstimation": True,
        "parentVerification": False,
    }

    response = None
    try:
        response = session.post(
            START_VERIFICATION_URL,
            json=payload,
            timeout=timeout_seconds,
        )
        csrf_token = response.headers.get("x-csrf-token")
        if response.status_code == 403 and csrf_token:
            session.headers["x-csrf-token"] = csrf_token
            response = session.post(
                START_VERIFICATION_URL,
                json=payload,
                timeout=timeout_seconds,
            )
        response.raise_for_status()
    except requests.RequestException as exc:
        status = response.status_code if response is not None else "<no response>"
        body = response.text if response is not None else ""
        body = (body or "").replace("\r", "\\r").replace("\n", "\\n")
        raise AgeVerificationError(
            "Could not start age verification: "
            f"status={status} body={body[:500]}"
        ) from exc

    try:
        response_payload = response.json()
    except ValueError as exc:
        body = (response.text or "").replace("\r", "\\r").replace("\n", "\\n")
        raise AgeVerificationError(
            "Age-verification service returned invalid JSON: "
            f"body={body[:500]}"
        ) from exc

    if not isinstance(response_payload, dict):
        raise AgeVerificationError(
            "Age-verification service returned an unexpected JSON payload"
        )

    verification_link = response_payload.get("verificationLink")
    parsed_link = urlparse(verification_link or "")
    if parsed_link.scheme != "https" or not parsed_link.netloc:
        raise AgeVerificationError(
            "Age-verification response did not contain a valid verificationLink"
        )
    return verification_link


def _click_continue(driver: object) -> None:
    continue_button = WebDriverWait(driver, 30).until(
        EC.element_to_be_clickable(
            (
                By.ID,
                "button_submit",
            )
        )
    )
    continue_button.click()


def _click_camera(driver: object) -> None:
    camera_button = WebDriverWait(driver, 30).until(
        EC.element_to_be_clickable(
            (
                By.ID,
                "selfie-prompt__button--camera",
            )
        )
    )
    camera_button.click()


def read_inquiry_status(driver: object) -> dict[str, object]:
    result = driver.execute_async_script(INQUIRY_STATUS_SCRIPT)
    if not isinstance(result, dict):
        return {
            "status": None,
            "httpStatus": None,
            "error": "unexpected inquiry-status response",
        }
    return result


def _verification_complete(driver: object, verification_host: str) -> bool:
    current_host = urlparse(driver.current_url or "").netloc.lower()
    if current_host != verification_host and (
        current_host == "roblox.com" or current_host.endswith(".roblox.com")
    ):
        return True

    inquiry = read_inquiry_status(driver)
    status = inquiry.get("status")
    if status in SUCCESS_STATUSES:
        return True
    if status in FAILURE_STATUSES:
        raise AgeVerificationError(
            f"Persona inquiry reached terminal status: {status}"
        )

    page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
    if "couldn't access camera" in page_text:
        raise AgeVerificationError(
            "Persona could not access the configured camera"
        )
    return False


def verify_age(
    driver: object,
    cookie: str,
    *,
    config: AgeVerificationConfig | None = None,
    logger: LogFunction | None = None,
) -> bool:
    """Run Persona age estimation using the authenticated Roblox session."""

    config = config or AgeVerificationConfig.from_environment()
    user_agent = (
        driver.execute_script("return navigator.userAgent") or DEFAULT_USER_AGENT
    )

    _log(logger, "Starting age verification")
    verification_link = request_verification_link(
        cookie,
        user_agent=user_agent,
        timeout_seconds=config.request_timeout_seconds,
    )
    _log(
        logger,
        "Age-verification session created",
        host=urlparse(verification_link).netloc,
    )
    verification_host = urlparse(verification_link).netloc.lower()

    with FakeWebcam(config, logger):
        driver.get(verification_link)
        _click_continue(driver)
        _click_camera(driver)
        _log(logger, "Waiting for age-verification completion")
        try:
            WebDriverWait(driver, config.completion_timeout_seconds).until(
                lambda current_driver: _verification_complete(
                    current_driver,
                    verification_host,
                )
            )
        except TimeoutException as exc:
            raise AgeVerificationError(
                "Age verification did not reach a terminal screen within "
                f"{config.completion_timeout_seconds:g} seconds"
            ) from exc

    _log(logger, "Age verification completed")
    return True
