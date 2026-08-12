import json
from dataclasses import dataclass

HBA_SEED_SCRIPT = r"""
const done = arguments[arguments.length - 1];

function openDatabase(dbName, version, objectStoreName) {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(dbName, version);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(objectStoreName)) {
        db.createObjectStore(objectStoreName);
      }
    };
    request.onerror = () => reject(request.error || new Error("IndexedDB open failed"));
    request.onsuccess = () => resolve(request.result);
  });
}

function putKeyPair(db, objectStoreName, keyName, keyPair) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(objectStoreName, "readwrite");
    tx.objectStore(objectStoreName).put(keyPair, keyName);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error || new Error("IndexedDB put failed"));
    tx.onabort = () => reject(tx.error || new Error("IndexedDB put aborted"));
  });
}

(async () => {
  const meta = document.querySelector('meta[name="hardware-backed-authentication-data"]');
  const dataset = meta ? meta.dataset : {};
  const dbName = dataset.hbaIndexedDbName || "hbaDB";
  const objectStoreName = dataset.hbaIndexedDbObjStoreName || "hbaObjectStore";
  const keyName = dataset.hbaIndexedDbKeyName || "hba_keys";
  const dbVersion = Number(dataset.hbaIndexedDbVersion || 1);

  const keyPair = await crypto.subtle.generateKey(
    { name: "ECDSA", namedCurve: "P-256" },
    true,
    ["sign", "verify"],
  );
  const privateKeyJwk = await crypto.subtle.exportKey("jwk", keyPair.privateKey);

  const db = await openDatabase(dbName, dbVersion, objectStoreName);
  try {
    await putKeyPair(db, objectStoreName, keyName, keyPair);
  } finally {
    db.close();
  }

  done({
    ok: true,
    private_key_jwk: privateKeyJwk,
    db_name: dbName,
    object_store_name: objectStoreName,
    key_name: keyName,
    db_version: dbVersion,
  });
})().catch((error) => {
  done({
    ok: false,
    error: String(error && error.message ? error.message : error),
    stack: error && error.stack ? String(error.stack) : "",
  });
});
"""

HBA_INSPECTION_SCRIPT = r"""
const [dbName, objectStoreName, keyName, dbVersion] = arguments;
const done = arguments[arguments.length - 1];

function getKeyPair() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(dbName, dbVersion);
    request.onerror = () => reject(request.error || new Error("IndexedDB open failed"));
    request.onsuccess = () => {
      const db = request.result;
      try {
        const tx = db.transaction(objectStoreName, "readonly");
        const get = tx.objectStore(objectStoreName).get(keyName);
        get.onsuccess = () => resolve(get.result);
        get.onerror = () => reject(get.error || new Error("IndexedDB get failed"));
        tx.oncomplete = () => db.close();
      } catch (error) {
        db.close();
        reject(error);
      }
    };
  });
}

(async () => {
  const keyPair = await getKeyPair();
  if (!keyPair || !keyPair.privateKey) {
    throw new Error("Stored HBA key pair is missing");
  }
  const privateKeyJwk = await crypto.subtle.exportKey("jwk", keyPair.privateKey);
  done({
    ok: true,
    private_key_jwk: privateKeyJwk,
  });
})().catch((error) => done({
  ok: false,
  error: String(error && error.message ? error.message : error),
}));
"""

BROWSER_SESSION_REFRESH_SCRIPT = r"""
const done = arguments[arguments.length - 1];
const refreshUrl = "https://auth.roblox.com/v2/session/refresh";
const authenticatedUrl = "https://users.roblox.com/v1/users/authenticated";

function timeoutResult(milliseconds) {
  return new Promise((resolve) => setTimeout(
    () => resolve({ settled: false, timeout_ms: milliseconds }),
    milliseconds,
  ));
}

(async () => {
  const httpService = window.CoreUtilities && window.CoreUtilities.httpService;
  if (!httpService || typeof httpService.post !== "function") {
    throw new Error("Roblox HTTP service is unavailable");
  }

  const xsrfPresentBefore = Boolean(localStorage.getItem("x-csrf-token"));

  const refreshOperation = (async () => {
    try {
      const response = await httpService.post(
        { url: refreshUrl, withCredentials: true, timeout: 10000 },
        {},
      );
      return {
        settled: true,
        status: response && (response.status ?? response.statusCode ?? 200),
        response_code: null,
        response_message: null,
      };
    } catch (error) {
      const response = error && error.response;
      const responseBody = (response && response.data) || (error && error.data) || null;
      return {
        settled: true,
        status: (response && response.status) || (error && (error.status || error.statusCode)) || null,
        response_code: responseBody && (responseBody.code ?? responseBody.errorCode ?? null),
        response_message: responseBody && String(responseBody.message || responseBody.error || "").slice(0, 160),
      };
    }
  })();
  const refreshOutcome = await Promise.race([refreshOperation, timeoutResult(15000)]);

  const authenticatedOutcome = await Promise.race([
    fetch(authenticatedUrl, { method: "GET", credentials: "include" })
      .then((response) => ({ status: response.status }))
      .catch((error) => ({ status: null, error: String(error && error.message ? error.message : error) })),
    timeoutResult(5000),
  ]);
  const refreshStatus = refreshOutcome.status ?? null;
  const authenticatedStatus = authenticatedOutcome.status ?? null;
  done({
    ok: refreshStatus >= 200 && refreshStatus < 300 && authenticatedStatus === 200,
    implementation: "roblox_v2_session_refresh",
    refresh_settled: refreshOutcome.settled,
    refresh_status: refreshStatus,
    refresh_timeout_ms: refreshOutcome.timeout_ms || null,
    authenticated_after_status: authenticatedStatus,
    response_code: refreshOutcome.response_code ?? null,
    response_message: refreshOutcome.response_message ?? null,
    xsrf_present_before: xsrfPresentBefore,
  });
})().catch((error) => done({
  ok: false,
  error: String(error && error.message ? error.message : error),
}));
"""


@dataclass(frozen=True)
class HbaMaterial:
    private_key_jwk: dict
    db_name: str
    object_store_name: str
    key_name: str
    db_version: int

    def upload_payload(self):
        return {
            "hba_private_key_jwk": json.dumps(self.private_key_jwk, separators=(",", ":")),
        }


def seed_hba_keypair(driver):
    result = driver.execute_async_script(HBA_SEED_SCRIPT)
    if not result["ok"]:
        raise RuntimeError(f"Failed to seed HBA keypair: {result['error']}")

    return HbaMaterial(
        private_key_jwk=result["private_key_jwk"],
        db_name=result["db_name"],
        object_store_name=result["object_store_name"],
        key_name=result["key_name"],
        db_version=int(result["db_version"]),
    )


def inspect_hba_keypair(driver, seeded_material):
    result = driver.execute_async_script(
        HBA_INSPECTION_SCRIPT,
        seeded_material.db_name,
        seeded_material.object_store_name,
        seeded_material.key_name,
        seeded_material.db_version,
    )
    if not result["ok"]:
        raise RuntimeError(f"Failed to inspect browser HBA keypair: {result['error']}")

    return HbaMaterial(
        private_key_jwk=result["private_key_jwk"],
        db_name=seeded_material.db_name,
        object_store_name=seeded_material.object_store_name,
        key_name=seeded_material.key_name,
        db_version=seeded_material.db_version,
    )


def browser_refresh_session(driver):
    return driver.execute_async_script(BROWSER_SESSION_REFRESH_SCRIPT)
