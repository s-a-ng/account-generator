import json
from dataclasses import dataclass
from datetime import datetime, timezone


HBA_SEED_SCRIPT = r"""
const done = arguments[arguments.length - 1];

function base64FromArrayBuffer(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode.apply(null, bytes.subarray(offset, offset + 0x8000));
  }
  return btoa(binary);
}

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
  const publicKeySpki = await crypto.subtle.exportKey("spki", keyPair.publicKey);
  const privateKeyJwk = await crypto.subtle.exportKey("jwk", keyPair.privateKey);
  const publicKeyJwk = await crypto.subtle.exportKey("jwk", keyPair.publicKey);

  const db = await openDatabase(dbName, dbVersion, objectStoreName);
  try {
    await putKeyPair(db, objectStoreName, keyName, keyPair);
  } finally {
    db.close();
  }

  done({
    ok: true,
    public_key_spki: base64FromArrayBuffer(publicKeySpki),
    private_key_jwk: privateKeyJwk,
    public_key_jwk: publicKeyJwk,
    db_name: dbName,
    object_store_name: objectStoreName,
    key_name: keyName,
    db_version: dbVersion,
    meta_present: Boolean(meta),
  });
})().catch((error) => {
  done({
    ok: false,
    error: String(error && error.message ? error.message : error),
    stack: error && error.stack ? String(error.stack) : "",
  });
});
"""

HBA_REQUEST_OBSERVER_SCRIPT = r"""
(() => {
  const storageKey = "roblox_hba_intent_observations";

  function findIntent(value, depth = 0) {
    if (!value || typeof value !== "object" || depth > 4) return null;
    const direct = value.secureAuthenticationIntent || value.SecureAuthenticationIntent;
    if (direct && typeof direct.clientPublicKey === "string") return direct;
    for (const child of Object.values(value)) {
      const found = findIntent(child, depth + 1);
      if (found) return found;
    }
    return null;
  }

  function record(url, body) {
    try {
      const parsed = typeof body === "string" ? JSON.parse(body) : body;
      const intent = findIntent(parsed);
      if (!intent) return;
      const target = new URL(String(url || ""), window.location.href);
      const existing = JSON.parse(sessionStorage.getItem(storageKey) || "[]");
      existing.push({
        endpoint: `${target.origin}${target.pathname}`,
        client_public_key: intent.clientPublicKey,
        timestamp_type: typeof intent.clientEpochTimestamp,
        signature_length: String(intent.saiSignature || "").length,
      });
      sessionStorage.setItem(storageKey, JSON.stringify(existing.slice(-20)));
    } catch (_) {}
  }

  if (window.__robloxHbaObserverInstalled) return;
  window.__robloxHbaObserverInstalled = true;

  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url, ...args) {
    this.__robloxHbaObservedUrl = url;
    return originalOpen.call(this, method, url, ...args);
  };
  XMLHttpRequest.prototype.send = function(body) {
    record(this.__robloxHbaObservedUrl, body);
    return originalSend.call(this, body);
  };

  const originalFetch = window.fetch;
  if (typeof originalFetch === "function") {
    window.fetch = function(input, init = {}) {
      record(typeof input === "string" ? input : input && input.url, init.body);
      return originalFetch.call(this, input, init);
    };
  }
})();
"""

HBA_INSPECTION_SCRIPT = r"""
const [dbName, objectStoreName, keyName, dbVersion] = arguments;
const done = arguments[arguments.length - 1];

function base64FromArrayBuffer(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode.apply(null, bytes.subarray(offset, offset + 0x8000));
  }
  return btoa(binary);
}

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
  if (!keyPair || !keyPair.privateKey || !keyPair.publicKey) {
    throw new Error("Stored HBA key pair is missing");
  }
  const publicKeySpki = await crypto.subtle.exportKey("spki", keyPair.publicKey);
  const privateKeyJwk = await crypto.subtle.exportKey("jwk", keyPair.privateKey);
  const publicKeyJwk = await crypto.subtle.exportKey("jwk", keyPair.publicKey);
  let observations = [];
  try {
    observations = JSON.parse(sessionStorage.getItem("roblox_hba_intent_observations") || "[]");
  } catch (_) {}
  done({
    ok: true,
    public_key_spki: base64FromArrayBuffer(publicKeySpki),
    private_key_jwk: privateKeyJwk,
    public_key_jwk: publicKeyJwk,
    observations,
  });
})().catch((error) => done({
  ok: false,
  error: String(error && error.message ? error.message : error),
}));
"""

BROWSER_REAUTH_SCRIPT = r"""
const [expectedPublicKey] = arguments;
const done = arguments[arguments.length - 1];
const reauthUrl = "https://auth.roblox.com/v1/logoutfromallsessionsandreauthenticate";
const authenticatedUrl = "https://users.roblox.com/v1/users/authenticated";

(async () => {
  const cryptoUtil = window.CoreRobloxUtilities && window.CoreRobloxUtilities.cryptoUtil;
  const httpService = window.CoreUtilities && window.CoreUtilities.httpService;
  if (!cryptoUtil || typeof cryptoUtil.generateSecureAuthIntentV2 !== "function") {
    throw new Error("Roblox V2 secure-auth intent generator is unavailable");
  }
  if (!httpService || typeof httpService.post !== "function") {
    throw new Error("Roblox HTTP service is unavailable");
  }

  const intent = await cryptoUtil.generateSecureAuthIntentV2();
  if (!intent) throw new Error("Roblox secure-auth intent generator returned no intent");

  let reauthStatus = null;
  let responseCode = null;
  let responseMessage = null;
  try {
    const response = await httpService.post(
      { url: reauthUrl, withCredentials: true, timeout: 10000 },
      { secureAuthenticationIntent: intent },
    );
    reauthStatus = response && (response.status ?? response.statusCode ?? 200);
  } catch (error) {
    const response = error && error.response;
    const responseBody = (response && response.data) || (error && error.data) || null;
    reauthStatus = (response && response.status) || (error && (error.status || error.statusCode)) || null;
    responseCode = responseBody && (responseBody.code ?? responseBody.errorCode ?? null);
    responseMessage = responseBody && String(responseBody.message || responseBody.error || "").slice(0, 160);
  }

  const authenticatedResponse = await fetch(authenticatedUrl, {
    method: "GET",
    credentials: "include",
  });
  done({
    ok: reauthStatus >= 200 && reauthStatus < 300 && authenticatedResponse.ok,
    implementation: "roblox_core_utilities_v2",
    reauth_status: reauthStatus,
    authenticated_after_status: authenticatedResponse.status,
    response_code: responseCode,
    response_message: responseMessage,
    intent_public_key_matches_seed: intent.clientPublicKey === expectedPublicKey,
    intent_timestamp_type: typeof intent.clientEpochTimestamp,
    intent_signature_length: String(intent.saiSignature || "").length,
  });
})().catch((error) => done({
  ok: false,
  error: String(error && error.message ? error.message : error),
}));
"""


@dataclass
class HbaMaterial:
    public_key_spki: str
    private_key_jwk: dict
    public_key_jwk: dict
    db_name: str
    object_store_name: str
    key_name: str
    db_version: int
    created_at: str

    def upload_payload(self):
        return {
            "hba_private_key_jwk": json.dumps(self.private_key_jwk, separators=(",", ":")),
        }


def seed_hba_keypair(driver):
    result = driver.execute_async_script(HBA_SEED_SCRIPT)
    if not isinstance(result, dict) or not result.get("ok"):
        error = result.get("error") if isinstance(result, dict) else result
        raise RuntimeError(f"Failed to seed HBA keypair: {error}")

    return HbaMaterial(
        public_key_spki=result["public_key_spki"],
        private_key_jwk=result["private_key_jwk"],
        public_key_jwk=result["public_key_jwk"],
        db_name=result["db_name"],
        object_store_name=result["object_store_name"],
        key_name=result["key_name"],
        db_version=int(result["db_version"]),
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def install_hba_request_observer(driver):
    driver.execute_script(HBA_REQUEST_OBSERVER_SCRIPT)


def inspect_hba_keypair(driver, seeded_material):
    result = driver.execute_async_script(
        HBA_INSPECTION_SCRIPT,
        seeded_material.db_name,
        seeded_material.object_store_name,
        seeded_material.key_name,
        seeded_material.db_version,
    )
    if not isinstance(result, dict) or not result.get("ok"):
        error = result.get("error") if isinstance(result, dict) else result
        raise RuntimeError(f"Failed to inspect browser HBA keypair: {error}")

    current = HbaMaterial(
        public_key_spki=result["public_key_spki"],
        private_key_jwk=result["private_key_jwk"],
        public_key_jwk=result["public_key_jwk"],
        db_name=seeded_material.db_name,
        object_store_name=seeded_material.object_store_name,
        key_name=seeded_material.key_name,
        db_version=seeded_material.db_version,
        created_at=seeded_material.created_at,
    )
    observations = result.get("observations") or []
    return current, observations


def browser_reauthenticate(driver, material):
    result = driver.execute_async_script(
        BROWSER_REAUTH_SCRIPT,
        material.public_key_spki,
    )
    if not isinstance(result, dict):
        raise RuntimeError(f"Browser reauthentication returned invalid data: {result}")
    return result
