#!/usr/bin/env python3
"""Delete duplicate Zotero items via Debug Bridge WebSocket."""
import json, websocket, time, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
WS_URL = "ws://127.0.0.1:23119/"

def load_dup_keys():
    audit_path = os.path.join(HERE, "zotero_dedup_audit.json")
    with open(audit_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    keys = []
    for d in data["details"]:
        keys.extend(d["deleted_keys"])
    return keys

def ws_eval(ws, code):
    ws.send(json.dumps({"action": "code", "code": code}))
    result = ws.recv()
    return json.loads(result)

def main():
    keys = load_dup_keys()
    print(f"Duplicate keys to trash: {len(keys)}")

    print("Connecting to Zotero Debug Bridge...")
    try:
        ws = websocket.create_connection(WS_URL, timeout=10)
    except Exception as e:
        print(f"WebSocket connection failed: {e}")
        print("Debug Bridge may not be enabled.")
        print("Enable it: Zotero > Edit > Preferences > Advanced > Editor >")
        print("  extensions.zotero.debug.bridge = true")
        return False

    # Test connection
    r = ws_eval(ws, "Zotero.version")
    print(f"Zotero version: {r}")

    # Trash items in batches of 50
    batch_size = 50
    total_ok = 0
    for i in range(0, len(keys), batch_size):
        batch = keys[i:i+batch_size]
        num = i // batch_size + 1
        total_batches = (len(keys) + batch_size - 1) // batch_size
        keys_js = json.dumps(batch)
        code = (
            "(async () => {"
            f"  const keys = {keys_js};"
            "  let trashed = Zotero.Items.getAsync(keys).then(items => {"
            "    let ids = items.map(it => it.id);"
            "    return Zotero.Items.trash(ids);"
            "  });"
            "  return await trashed;"
            "})()"
        )
        try:
            r = ws_eval(ws, code)
            total_ok += len(batch)
            print(f"  Batch {num}/{total_batches}: trashed {len(batch)} items")
        except Exception as e:
            print(f"  Batch {num}/{total_batches} FAILED: {e}")
        time.sleep(0.5)

    ws.close()
    print(f"\nDone: {total_ok} items trashed")
    return True

if __name__ == "__main__":
    main()
