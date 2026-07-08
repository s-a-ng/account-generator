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
            "hba_public_key": self.public_key_spki,
            "hba_private_key_jwk": json.dumps(self.private_key_jwk, separators=(",", ":")),
            "hba_public_key_jwk": json.dumps(self.public_key_jwk, separators=(",", ":")),
            "hba_indexed_db_name": self.db_name,
            "hba_indexed_db_object_store_name": self.object_store_name,
            "hba_indexed_db_key_name": self.key_name,
            "hba_indexed_db_version": self.db_version,
            "hba_key_created_at": self.created_at,
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
