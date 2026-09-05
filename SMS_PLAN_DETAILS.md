# MPLAE PRO - SMS Marketing & Billing System Guide

This document provides a detailed breakdown of the SMS pricing plans, how the credits work, and instructions for activating the live SMS feature in your MPLAE PRO software.

---

## 1. SMS Pricing Plans (via Fast2SMS)

Fast2SMS works on a **Wallet System**. You add money to your wallet, and a fixed amount is deducted for every message you send.

| Recharge Amount | Cost Per SMS | Total SMS (Approx) | Validity | Best For |
| :--- | :--- | :--- | :--- | :--- |
| **₹100** | **25 Paise** | **400 SMS** | **Unlimited** | Testing & Small Shops |
| **₹4,000** | **21 Paise** | **19,047 SMS** | **6 Months** | Growing Businesses |
| **₹14,000** | **17 Paise** | **82,352 SMS** | **12 Months** | Large Scale Marketing |

---

## 2. Understanding "Total SMS" and "Validity"

### What does "Total SMS" mean?
It is the total number of times you can hit the "Send" button. 
- If you recharge for **₹100**, you get **400 attempts**.
- Every time you send a bill or a broadcast, 1 attempt is deducted from your balance.

### What does "Unlimited Validity" mean? (For the ₹100 Plan)
- Your messages **never expire**.
- If you buy 400 SMS today and only use 10 this month, the remaining 390 SMS will still be there next year. 
- You only pay again when your balance reaches zero.

---

## 3. The 160-Character Rule
Standard SMS is calculated based on characters:
*   **1 SMS Credit** = Up to 160 characters (letters, numbers, spaces).
*   **2 SMS Credits** = 161 to 306 characters.
*   **Recommendation:** Keep your "Broadcast" messages short and sweet to save money!

---

## 4. How to Activate Live SMS

I have already written the code. You just need to follow these **two steps** to start sending real messages to phones:

### Step A: Install the "Requests" Library
Open your terminal/command prompt and run:
```powershell
pip install requests
```

### Step B: Add your API Key
1. Sign up/Login at [Fast2SMS.com](https://www.fast2sms.com).
2. Copy your **Authorization Key** from the dashboard.
3. Open `app.py` in your code editor.
4. Find line **1470** (inside the `send_fast2sms` function).
5. Replace the placeholder with your real key:
   ```python
   # Change this:
   API_KEY = "YOUR_API_KEY_HERE"
   # To this:
   API_KEY = "pXyZ... (your actual key)"
   ```

---

## 5. How to use the Broadcast Feature
1. Go to **Sales Menu** -> **Customer Data**.
2. Click the **BROADCAST OFFER** button.
3. Type your message. 
    - *Tip: Use `{name}` in your message (e.g., "Hi {name}...") and the system will automatically put the customer's real name in each text!*
4. Click **SEND TO ALL**. The system will handle the rest in the background.

---

*Generated for MPLAE PRO v3.0*
