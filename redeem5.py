import requests
import time
import threading

BOT_TOKEN = "8199228375:AAEXNLp2xE6i3z6w5gUM2Tv2bP2vVK3qb4I"
CHAT_ID = 6442344136  # admin/chat id for testing (optional)
GITHUB_LIST_URL = "https://raw.githubusercontent.com/ddxclipsxdx/gigDEV/refs/heads/main/gigID.json"
REWARD_ID_PRIMARY = 41
REWARD_ID_FALLBACK = 38
TWOCAPTCHA_API_KEY = "ced6b10518f6c32ac48fe88eeeb3f2eb"

API_LOGIN_URL = "https://api.gigrewards.ph/api/trpc/v2/auth.login"
API_REDEEM_URL = "https://api.gigrewards.ph/api/trpc/v2/reward.redeem"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
REFERER = "https://app.gigrewards.ph/"

user_sessions = {}
authorized_users = set()

def fetch_authorized_users():
    global authorized_users
    try:
        r = requests.get(GITHUB_LIST_URL)
        data = r.json()
        if isinstance(data, dict) and "authorized_users" in data:
            authorized_users = set(int(u) for u in data["authorized_users"])
        elif isinstance(data, dict) and "deviceIds" in data:
            authorized_users = set(int(u) for u in data["deviceIds"])
        elif isinstance(data, list):
            authorized_users = set(int(u) for u in data)
        else:
            authorized_users = set()
        print(f"Authorized users loaded: {authorized_users}")
    except Exception as e:
        print(f"Failed to fetch authorized users: {e}")
        authorized_users = set()

def is_user_authorized(user_id):
    return user_id in authorized_users

def send_telegram(text, chat_id):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Failed to send message: {e}")

def login(raw_number, password):
    if raw_number.startswith("09") and len(raw_number) == 11:
        username = "+63" + raw_number[1:]
    else:
        username = raw_number

    headers = {
        "Content-Type": "application/json",
        "Referer": REFERER,
        "User-Agent": USER_AGENT,
    }
    payload = {
        "json": {
            "number": username,
            "password": password
        }
    }
    r = requests.post(API_LOGIN_URL, json=payload, headers=headers)
    data = r.json()
    if r.status_code == 200 and "result" in data:
        login_data = data["result"]["data"]["json"]
        if login_data.get("code") == 200 and "session" in login_data:
            return {
                "token": login_data["session"],
                "tenantId": login_data.get("tenantId", ""),
                "relatedCode": login_data.get("relatedCode", "")
            }
        else:
            raise Exception(f"Login failed: {login_data.get('message', 'Unknown error')}")
    else:
        raise Exception(f"Login request failed: {data}")

def solve_captcha(site_key, page_url):
    captcha_req = requests.post("http://2captcha.com/in.php", data={
        "key": TWOCAPTCHA_API_KEY,
        "method": "userrecaptcha",
        "googlekey": site_key,
        "pageurl": page_url,
        "json": 1
    }).json()

    if captcha_req.get("status") != 1:
        print("Failed to send captcha:", captcha_req)
        return None

    captcha_id = captcha_req.get("request")
    print(f"Captcha sent. ID: {captcha_id}")

    for i in range(30):
        res = requests.get("http://2captcha.com/res.php", params={
            "key": TWOCAPTCHA_API_KEY,
            "action": "get",
            "id": captcha_id,
            "json": 1
        }).json()

        if res.get("status") == 1:
            print("Captcha solved!")
            return res.get("request")
        elif res.get("request") == "CAPCHA_NOT_READY":
            print(f"Waiting for captcha solution... ({i + 1}/30)")
            time.sleep(2)
            continue
        else:
            print("Captcha solving failed:", res)
            return None

    print("Captcha solve timed out")
    return None

def redeem(token, captcha_token, reward_id):
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
        "Referer": REFERER,
        "User-Agent": USER_AGENT,
    }
    payload = {
        "json": {
            "rewardId": reward_id,
            "token": captcha_token
        }
    }
    r = requests.post(API_REDEEM_URL, json=payload, headers=headers)
    data = r.json()
    if r.status_code == 200:
        if "error" in data:
            return data["error"]["json"]["message"]
        return None
    else:
        return f"Redeem request failed: {data}"

def claim_loop(chat_id, username, password):
    max_claims = 15
    claim_count = 0

    while True:
        try:
            login_data = login(username, password)
            token = login_data["token"]
            send_telegram(f"✅ Logged in successfully. Starting claim process...", chat_id)

            while claim_count < max_claims:
                captcha_token = solve_captcha("6LcMQ_EqAAAAAG6VZr9tkvjkNJxr_OW7twr2OWY2", "https://app.gigrewards.ph")
                if not captcha_token:
                    send_telegram("❌ Captcha solving failed. Retrying...", chat_id)
                    # Retry captcha up to 3 times
                    retry_captcha = 0
                    while retry_captcha < 3 and not captcha_token:
                        captcha_token = solve_captcha("6LcMQ_EqAAAAAG6VZr9tkvjkNJxr_OW7twr2OWY2", "https://app.gigrewards.ph")
                        retry_captcha += 1
                        time.sleep(3)
                    if not captcha_token:
                        send_telegram("❌ Captcha failed after 3 retries. Stopping claim process.", chat_id)
                        break

                error = redeem(token, captcha_token, REWARD_ID_PRIMARY)
                if error and "Insufficient funds" in error:
                    send_telegram("⚠️ Primary reward insufficient funds. Trying fallback reward...", chat_id)
                    error = redeem(token, captcha_token, REWARD_ID_FALLBACK)
                    if error and "Insufficient funds" in error:
                        send_telegram(f"❌ Both rewards insufficient funds. Stopped at {claim_count}/{max_claims}.", chat_id)
                        break

                if error:
                    send_telegram(f"❌ Error during claiming: {error}", chat_id)
                    break

                claim_count += 1
                send_telegram(f"🎉 Successfully claimed reward {claim_count}/{max_claims}", chat_id)
                time.sleep(3)

            send_telegram(f"🎊 Claim process complete. Restarting login flow...", chat_id)
            break

        except Exception as e:
            send_telegram(f"❌ Login or claiming failed: {str(e)}", chat_id)
            break

    # Reset session so user can input number again automatically
    if chat_id in user_sessions:
        user_sessions.pop(chat_id)
    user_sessions[chat_id] = {"step": "username"}
    send_telegram("🔄 Please enter your login number starting with 09 to start again:", chat_id)

def process_message(update):
    if "message" not in update:
        return

    message = update["message"]
    chat_id = message["chat"]["id"]
    user_text = message.get("text", "").strip()

    if not is_user_authorized(chat_id):
        send_telegram(f"⛔️ YOU ARE NOT AUTHORIZED!! PLEASE CONTACT THE OWNER TO BE AUTHORIZED TO USE THIS BOT!\n\nYour User ID: {chat_id}", chat_id)
        return

    if user_text.lower().startswith("/start"):
        user_sessions[chat_id] = {"step": "username"}
        send_telegram("Welcome! Please enter your login number starting with 09 (e.g., 09123456789):", chat_id)
        return

    if user_text.lower().startswith("/stop"):
        if chat_id in user_sessions:
            user_sessions.pop(chat_id)
        send_telegram("⏹️ Stopped your current session.", chat_id)
        return

    if chat_id not in user_sessions:
        send_telegram("Please send /start to begin.", chat_id)
        return

    session = user_sessions[chat_id]

    if session["step"] == "username":
        if user_text.startswith("09") and len(user_text) == 11:
            session["username"] = user_text
            session["step"] = "password"
            send_telegram("Please enter your password:", chat_id)
        else:
            send_telegram("❌ Invalid phone number format. Please enter a number starting with 09 and 11 digits long (e.g., 09123456789).", chat_id)
        return

    if session["step"] == "password":
        session["password"] = user_text
        send_telegram("🔐 Logging in and starting claim process...", chat_id)
        session["step"] = "claiming"

        # Start claim loop in a background thread
        claim_thread = threading.Thread(target=claim_loop, args=(chat_id, session["username"], session["password"]))
        claim_thread.daemon = True
        claim_thread.start()
        return

def main():
    fetch_authorized_users()
    offset = 0

    print("Bot started. Waiting for messages...")

    while True:
        try:
            updates = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={offset}&timeout=30").json()

            if updates["ok"]:
                for update in updates["result"]:
                    offset = update["update_id"] + 1
                    process_message(update)
        except Exception as e:
            print(f"Error fetching updates: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
