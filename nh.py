from __future__ import annotations
import asyncio
import base64
import json
import os
import sys
import time
from io import StringIO
from enum import Enum, auto
from datetime import datetime, timedelta
from typing import (
    AsyncIterator,
    Dict,
    List,
    NamedTuple,
    Optional,
    Tuple,
    TypedDict,
    Union,
)
from dataclasses import dataclass
from pathlib import Path
import httpx
from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).parent
DATA_FILE = ROOT / 'data.json'

INCOME_URL = "https://kageherostudio.com/event/?event=daily"
XSS_LOGIN = "https://kageherostudio.com/payment/server_.php?fbid={}&selserver=1"
LOGIN_URL = "https://kageherostudio.com/event/index_.php?act=login"
DATE = datetime.utcnow() + timedelta(hours=7)
PERIOD = DATE.month
PERIOD_D = DATE.replace(month=DATE.month % 12 + 1, day=1) - timedelta(days=1)
TIMEOUT = httpx.Timeout(60 * 5)

def b64_encode(text: str) -> str:
    return base64.b64encode(text.encode('utf-8')).decode('utf-8')

def b64_decode(encoded_text: str) -> str:
    return base64.b64decode(encoded_text.encode('utf-8')).decode('utf-8')

def is_base64(s: str) -> bool:
    try:
        decoded = base64.b64decode(s, validate=True)
        decoded.decode('utf-8')
        return True
    except Exception:
        return False

class ClaimStatus(Enum):
    SUCCESS = auto()
    FAILED = auto()
    CLAIMED = auto()

MSGSMAP = {
    ClaimStatus.SUCCESS: "Succes ✅",
    ClaimStatus.FAILED: "Unclaimed ❌",
    ClaimStatus.CLAIMED: "Claimed ✔️",
}

class UserData(TypedDict):
    email: str
    password: str
    server: int

class UserStatus(NamedTuple):
    email: str
    statuses: List[ClaimData]
    last_claim: int
    
    @property
    def print_mail(self):
        if "@" not in self.email:
            return self.email
        email, mail = self.email.split("@", 1)
        head, tail = (email[:2], email[2:])
        return head + "*" * len(tail) + mail

    def print_status(self):
        info = StringIO()
        info.writelines(
            (
                f"Income report for: {self.print_mail}\n",
                f"{DATE.date()}\n",
                f"Last Claim: {self.last_claim if self.last_claim > 0 else 'No last claim!'}\n",
            )
        )
        for data in self.statuses:
            info.write(f"\n{data}")
        return info.getvalue()

class ClaimCheck(Enum):
    CLAIMED = "grayscale"
    UNCLAIMED = "dailyClaim"
    CURRENT = "reward-star"
    
    def __str__(self) -> str:
        return self.value

@dataclass
class ClaimData:
    status: ClaimStatus
    day: int
    item: int
    name: str
    period: int
    
    def __str__(self) -> str:
        return f"Item: {self.item}/Day {self.day} ({self.name}): {MSGSMAP.get(self.status, 'Unclaimed!')}"

class NhIncome:
    def __init__(self, email: str, server: int, passwd: Optional[str] = None) -> None:
        self.email = email
        self.passwd = passwd
        self.server = server
        self.baselogin = LOGIN_URL if passwd else XSS_LOGIN.format(email)
        self.cookies: Optional[httpx.Cookies] = None
        self.claim_data: List[ClaimData] = []
        self.claim_success = False
        
    async def reserve_cookie(self, client: httpx.AsyncClient):
        await client.get(INCOME_URL)
        if self.passwd:
            await client.post(
                self.baselogin,
                data={"txtuserid": self.email, "txtpassword": self.passwd},
                timeout=5000,
            )
        else:
            await client.get(self.baselogin)
        self.cookies = client.cookies
        return await client.get(INCOME_URL)
        
    def post_claim(self, client: httpx.AsyncClient, item_id: int, period: int):
        return client.post(
            "https://kageherostudio.com/event/index_.php?act=daily",
            data={
                "itemId": item_id,
                "periodId": period,
                "selserver": self.server,
            },
        )
        
    async def fast_claim(self):
        async with httpx.AsyncClient() as client:
            resp = await self.reserve_cookie(client)
            soup = BeautifulSoup(resp.text, "html.parser")
            if not soup.find("p", "userid"):
                print(f"\r[!] Failed to login for {self.email:<20}", end="")
                return False
            today_reward = soup.select_one(f".{ClaimCheck.CURRENT}")
            if today_reward:
                item_id = today_reward.get("data-id", 0)
                period_id = today_reward.get("data-period", 0)
                result = await self.post_claim(client, item_id, period_id)
                resdata = result.json()
                if resdata.get("message") == "success":
                    self.claim_success = True
                else:
                    print(f"\r[-] Server rejected claim for {self.email:<20}", end="")
            claimed = [
                ClaimData(
                    status=ClaimStatus.CLAIMED,
                    day=-1,
                    item=claim.get("data-id", 0),
                    name=claim.get("data-name", "Undefined!"),
                    period=claim.get("data-period", 0),
                )
                for claim in soup.select(f"div.{ClaimCheck.CLAIMED}")
            ]
            self.claim_data = sorted(claimed, key=lambda k: k.item)
            return True
            
    async def skip_income(self, amount: int):
        async with httpx.AsyncClient() as client:
            resp = await self.reserve_cookie(client)
            soup = BeautifulSoup(resp.text, "html.parser")
            if not soup.find("p", "userid"):
                return {"status": "error", "message": "Failed to login"}
            
            today_reward = soup.select_one(f".{ClaimCheck.CURRENT}")
            if not today_reward:
                return {"status": "error", "message": "No unclaimed reward found (Already claimed today?)"}
            
            reward_id = today_reward.get("data-id")
            reward_period = today_reward.get("data-period")
            success_count = 0
            fail_count = 0
            
            # FIXED FOR PYTHON < 3.11
            tasks = [self.post_claim(client, reward_id, reward_period) for _ in range(amount)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for res in results:
                if isinstance(res, Exception):
                    fail_count += 1
                else:
                    try:
                        if res.json().get("message") == "success":
                            success_count += 1
                        else:
                            fail_count += 1
                    except Exception:
                        fail_count += 1
            
            return {
                "status": "success",
                "message": f"Skip finished! Success: {success_count}, Failed/Rejected: {fail_count}"
            }

async def loading_animation(stop_event: asyncio.Event, total: int):
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    idx = 0
    while not stop_event.is_set():
        frame = frames[idx % len(frames)]
        print(f"\r {frame} Processing {total} accounts, please wait...", end="", flush=True)
        idx += 1
        await asyncio.sleep(0.1)
    print("\r" + " " * 60 + "\r", end="")

def clear_screen():
    try:
        os.system('clear')
    except Exception:
        print("\n" * 50)

def load_data():
    if not DATA_FILE.exists():
        with open(DATA_FILE, 'w') as f:
            json.dump([], f)
        return []
    with open(DATA_FILE, 'r', encoding='utf-8') as file:
        data = json.load(file)
    fixed_data = []
    needs_save = False
    for acc in data:
        if "username" in acc and "email" not in acc:
            acc["email"] = acc.pop("username")
            needs_save = True
        if not is_base64(acc.get("password", "")):
            acc["password"] = b64_encode(acc["password"])
            needs_save = True
        if not isinstance(acc.get("server"), int):
            try:
                acc["server"] = int(acc.get("server", 1))
                needs_save = True
            except ValueError:
                acc["server"] = 1
        fixed_data.append(acc)
    if needs_save:
        print("[*] Securing database (Base64 Encrypting passwords)...")
        save_data(fixed_data)
        time.sleep(1)
    return fixed_data

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as file:
        json.dump(data, file, indent=4)

def add_account():
    clear_screen()
    print("=== Add Multiple Accounts ===")
    print("NOTE: Leave 'Email/Username' blank and press ENTER to finish.\n")
    data = load_data()
    added_count = 0
    while True:
        email = input(f"[{added_count + 1}] Email/Username : ").strip()
        if not email:
            break
        password = input(f"    Password : ").strip()
        if not password:
            print("    [-] Password cannot be empty! Skipping this account.")
            time.sleep(1)
            continue
        try:
            server = int(input(f"    Server ID : ").strip())
        except ValueError:
            print("    [-] Server must be a number! Skipping this account.")
            time.sleep(1)
            continue
        data.append({
            "email": email,
            "password": b64_encode(password),
            "server": server
        })
        added_count += 1
        print("    [+] Encrypted & Added successfully!\n")
    if added_count > 0:
        save_data(data)
        print(f"[*] Saved {added_count} new accounts securely.")
    else:
        print("[-] No accounts were added.")
    time.sleep(2)

def delete_account():
    clear_screen()
    data = load_data()
    if not data:
        print("[-] No accounts found in database!")
        time.sleep(2)
        return
    print("================== DELETE ACCOUNT ==================")
    for i, acc in enumerate(data, 1):
        email = acc["email"]
        if "@" in email:
            name, domain = email.split("@", 1)
            display_name = name[:2] + "*" * (len(name) - 2) + "@" + domain
        else:
            display_name = email
        print(f" [{i}] {display_name} (Server: {acc.get('server', '?')})")
    print("====================================================")
    try:
        choice = input("\nEnter the number of the account to delete (0 to cancel): ").strip()
        if choice == '0':
            print("[*] Deletion cancelled.")
            time.sleep(1)
            return
        idx = int(choice) - 1
        if 0 <= idx < len(data):
            target_email = data[idx]["email"]
            confirm = input(f"Are you sure you want to delete '{target_email}'? (y/n): ").strip().lower()
            if confirm == 'y':
                data.pop(idx)
                save_data(data)
                print(f"[+] Successfully deleted: {target_email}")
            else:
                print("[*] Deletion cancelled.")
        else:
            print("[-] Invalid number selected.")
    except ValueError:
        print("[-] Please enter a valid number.")
    time.sleep(2)

async def skip_days_menu():
    clear_screen()
    data = load_data()
    if not data:
        print("[-] No accounts found in database!")
        time.sleep(2)
        return
    print("================== SKIP CLAIM DAYS ==================")
    for i, acc in enumerate(data, 1):
        email = acc["email"]
        if "@" in email:
            name, domain = email.split("@", 1)
            display_name = name[:2] + "*" * (len(name) - 2) + "@" + domain
        else:
            display_name = email
        print(f" [{i}] {display_name} (Server: {acc.get('server', '?')})")
    print("====================================================")
    try:
        choice = input("\nSelect account number (0 to cancel): ").strip()
        if choice == '0':
            return
        idx = int(choice) - 1
        if not (0 <= idx < len(data)):
            print("[-] Invalid number selected.")
            time.sleep(2)
            return
        amount = input("How many days to skip? (e.g., 5): ").strip()
        skip_amount = int(amount)
        if skip_amount <= 0:
            print("[-] Amount must be greater than 0.")
            time.sleep(2)
            return
        acc = data[idx]
        real_password = b64_decode(acc["password"])
        daily = NhIncome(acc["email"], acc["server"], real_password)
        print(f"\n[*] Skipping {skip_amount} days for {acc['email']}...")
        result = await daily.skip_income(skip_amount)
        print(f"\n[+] {result['message']}")
    except ValueError:
        print("[-] Please enter valid numbers.")
    except Exception as e:
        print(f"[-] An error occurred: {e}")
    input("\nPress Enter to return to menu...")

def view_statistics():
    clear_screen()
    data = load_data()
    if not data:
        print("[-] No accounts found in database!")
        time.sleep(2)
        return
    print("================== ACCOUNT STATISTICS ==================")
    print(f" Period: {DATE.strftime('%B %Y')} (Total Days: {PERIOD_D.day})")
    print(" Security: Base64 Encrypted 🔒")
    print("=" * 55)
    max_len = max(len(acc["email"]) for acc in data)
    for i, acc in enumerate(data, 1):
        email = acc["email"]
        if "@" in email:
            name, domain = email.split("@", 1)
            display_name = name[:2] + "*" * (len(name) - 2) + "@" + domain
        else:
            display_name = email
        server = acc.get("server", "?")
        status = "Secured 🔒" if is_base64(acc.get("password", "")) else "Unsafe ❌"
        print(f" {i}. {display_name.ljust(max_len + 2)} | Server: {str(server).ljust(3)} | {status}")
    print("=" * 55)
    print(f" Total Accounts: {len(data)}")
    input("\nPress Enter to return to menu...")

async def run_claim_process(data):
    claim_datas: dict[str, NhIncome] = {}
    stop_animation = asyncio.Event()
    anim_task = asyncio.create_task(loading_animation(stop_animation, len(data)))
    try:
        # FIXED FOR PYTHON < 3.11
        tasks = []
        for userdata in data:
            real_password = b64_decode(userdata["password"])       
            daily = NhIncome(userdata["email"], userdata["server"], real_password)
            tasks.append(daily.fast_claim())
            claim_datas.update({userdata["email"]: daily})
            
        await asyncio.gather(*tasks)
    finally:
        stop_animation.set()
        await anim_task
    return claim_datas

def print_results(claim_datas, data):
    print("[✓] Claiming process finished!\n")
    print("="*40)
    for userdata in data:
        done = claim_datas[userdata["email"]]
        if not done.claim_data:
            print(f"NO DATA FOUND FOR: {userdata['email']}")
            continue
        success = list(d for d in done.claim_data if d.status in [ClaimStatus.CLAIMED, ClaimStatus.SUCCESS])
        status = UserStatus(userdata["email"], done.claim_data, max(d.day for d in success) if success else -1)
        print(status.print_status())
        print("-" * 40)

async def start_claim():
    clear_screen()
    data = load_data()
    if not data:
        print("[-] No accounts found!")
        time.sleep(2)
        return
    claim_datas = await run_claim_process(data)
    print_results(claim_datas, data)
    input("\nPress Enter to return to menu...")

async def auto_claim_loop():
    clear_screen()
    data = load_data()
    if not data:
        print("[-] No accounts found! Add accounts first.")
        time.sleep(2)
        return
    print("[!] AUTO-CLAIM MODE ACTIVATED")
    print("[!] Press Ctrl+C to stop and return to the menu.\n")
    while True:
        claim_datas = await run_claim_process(data)
        print_results(claim_datas, data)
        now = datetime.utcnow() + timedelta(hours=7)
        next_run = now + timedelta(hours=24)
        print("\n" + "="*40)
        print(f"[🔄] Next claim scheduled at: {next_run.strftime('%H:%M:%S')}")
        print("="*40 + "\n")
        try:
            for _ in range(86400):
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            print("\n[!] Auto-claim stopped by user.")
            break

def main_menu():
    data = load_data()
    while True:
        clear_screen()
        print("=================================")
        print(bytes.fromhex('4e494e4a41204845524f455320544f4f4c5320425920544f5241205441524f202020').decode())
        print("=================================")
        print(f" Total Accounts: {len(data)}")
        print("=================================")
        print(" [1] Start Claiming (Manual)")
        print(" [2] Add Multiple Accounts")
        print(" [3] Account Statistics")
        print(" [4] Start Auto Claim (24H)")
        print(" [5] Delete Account")
        print(" [6] Skip Claim Days")
        print(" [0] Exit")
        print("=================================")
        choice = input(" Select Option: ").strip()
        
        if choice == '1':
            try:
                asyncio.run(start_claim())
            except Exception as e:
                print(f"\n[-] An error occurred: {e}")
                input("Press Enter to continue...")
            data = load_data()
        elif choice == '2':
            add_account()
            data = load_data()
        elif choice == '3':
            view_statistics()
        elif choice == '4':
            try:
                asyncio.run(auto_claim_loop())
            except KeyboardInterrupt:
                pass
            data = load_data()
        elif choice == '5':
            delete_account()
            data = load_data()
        elif choice == '6':
            try:
                asyncio.run(skip_days_menu())
            except Exception as e:
                print(f"\n[-] An error occurred: {e}")
                input("Press Enter to continue...")
        elif choice == '0':
            clear_screen()
            print("Exiting...")
            sys.exit(0)
        else:
            print("[-] Invalid choice.")
            time.sleep(1)

if __name__ == '__main__':
    main_menu()