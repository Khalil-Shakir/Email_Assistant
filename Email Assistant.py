import imaplib
import time
import email
from email.mime.text import MIMEText 
from email.utils import parseaddr
from google import genai
import csv
import os
import requests
import smtplib

client = genai.Client(api_key = "AIzaSyBH8mkRiWC-gB8EoXZkDPtFtojhN5o47Xk")

# Fetch settings dynamically from cloud environment variables
IMAP_SERVER = os.environ.get("IMAP_SERVER", "imap.gmail.com")
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
EMAIL_ACCOUNT = os.environ.get("EMAIL_ACCOUNT")
APP_PASSWORD = os.environ.get("APP_PASSWORD")
ACCOUNT_NAME = os.environ.get("ACCOUNT_NAME", "Support Team")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
WEB_HOOK_URL = os.environ.get("WEB_HOOK_URL")

client = genai.Client(api_key=GEMINI_API_KEY)


def decode_part(part):
    raw_data = part.get_payload(decode = True)
    if not raw_data: return "no data"
    raw_charset = part.get_content_charset() or 'utf-8'
    try:
       return raw_data.decode(raw_charset, errors="replace")
    except Exception:
       return raw_data.decode('utf-8', errors="replace")


def fetch_and_process(imap_ssl, mail_id):
    resp_code, mail_data = imap_ssl.fetch(str(mail_id), '(RFC822)')
    if resp_code is not "OK" or not mail_data[0]: print(resp_code)

    message = email.message_from_bytes(mail_data[0][1])

    print("From:     :{}".format(message.get("FROM")))
    print("To        :{}".format(message.get("TO")))
    print("Date      :{}".format(message.get("DATE")))
    print("Subject   :{}".format(message.get("SUBJECT")))

    body_text = ""
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                body_text = decode_part(part)
                break
    else:
        body_text = decode_part(part)
    print("Body Preview:")
    print("-"*40)
    print(body_text)
    print("-"*40)
    print("Professional Reply: \n")
    reply = generate_response(body_text, message)
    print(reply)
    print("-"*40)
    export_csv(message, reply, body_text)
    _, sender_address = parseaddr(message.get("From"))
    if sender_address:
        send_reply(sender_address, message.get("Subject"), reply, original_msg_id=message.get("Message-ID"))
    print("Successfully exported")
    print("Waiting for new mails...")

def send_reply(to_email: str, subject: str, reply_body: str, original_msg_id = None):
    try:
        reply_sub = (subject if subject.lower().startswith("re:") else f"Re: {subject}")

        message = MIMEText(reply_body, "plain", "utf-8")
        message["From"] = EMAIL_ACCOUNT
        message["To"] = to_email
        message["Subject"] = reply_sub

        if original_msg_id:
            message["In_Reply_To"] = original_msg_id
            message["Reference"] = original_msg_id

        server = smtplib.SMTP(SMTP_SERVER)
        server.ehlo()  # Identify ourselves to the server
        server.starttls()  # Upgrade connection to secure TLS
        server.ehlo()
        server.login(EMAIL_ACCOUNT, APP_PASSWORD)
        server.sendmail(EMAIL_ACCOUNT, to_email, message.as_string())
        server.quit()

        print(f"Reply sent to {to_email} successfully!")
        return True
    
    except Exception as e:
        print(f"Failed to send reply: {e}")
        return False

def generate_response(mail: str, message):
    sender = message.get("FROM")
    name, address = parseaddr(sender)
    prompt = f"""
    You are writing a direct, human email reply as {ACCOUNT_NAME}. 
    
    Sender Name: {name}
    Subject: {message.get("Subject")}
    Email Body:
    {mail}

    Task:
    - Write a warm, concise, and professional reply directly answering the sender's email.
    - Write in a natural, conversational tone as if a real person typed it quickly and thoughtfully.
    - Sign off naturally as "{ACCOUNT_NAME}".

    CRITICAL RULES (Human Masking):
    1. NEVER mention that you are an AI, an assistant, an automated script, or a language model.
    2. DO NOT use generic AI intro/outro boilerplate like "Thank you for reaching out to us", "I am happy to assist you", or "If you have any further questions, feel free to ask".
    3. DO NOT use placeholder brackets like [Your Name] or [Company Name].
    4. Keep it grounded, direct, and completely indistinguishable from a human response.
    """
    try:
        interaction = client.interactions.create(
            model = "gemini-3-flash-preview",
            input = prompt
        )
        return interaction.output_text
    except Exception as e:
        print("Failed to generate a response.")
        return "Thank you for your email. We have received your message and will get back to you shortly."


def export_csv(message, reply, mail_text, filename: str = "Email Record.csv"):
    sender = message.get("From")
    name, address = parseaddr(sender)

    file_path = os.path.dirname("C:\\Users\\Khalil Shakir\\Documents")
    file_exists = os.path.exists("C:\\Users\\Khalil Shakir\\Documents\\Email Record.csv")    

    payload = {
        "Name": name,
        "Email Address": address,
        "Date":message.get("Date"),
        "Subject":message.get("Subject"),
        "Mail": mail_text,
        "Reply": reply
    }
    requests.post(WEB_HOOK_URL, json=payload)
    try:
        with open("C:\\Users\\Khalil Shakir\\Documents\\Email Record.csv", "a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            if not file_exists:
                writer.writerow([
                    "Name", "Email Address", "Date", "Subject", "Mail", "Reply"
                ])
            writer.writerow([
                name, address, message.get("Date"), message.get("Subject"), mail_text, reply
            ])
    except PermissionError as e:
        print("Unable to write. File is already in use by some other program!")

def start_assistant():
    while True:
        imap_ssl = None
        try:
            print("Logging into IMAP SERVER...")
            imap_ssl =  imaplib.IMAP4_SSL(host = IMAP_SERVER)
            imap_ssl.login(EMAIL_ACCOUNT, APP_PASSWORD)
            imap_ssl.select(mailbox=FOLDER)
            print("Loggin was successful!")

            resp_code, prev_mails = imap_ssl.search(None, "All")
            total_ids = [int(i) for i in prev_mails[0].decode().split()] if prev_mails[0] else []
            last_processed_id = max(total_ids) if total_ids else 0
            print(f"Benchmark initialized. Email assistant will read mails aftermail id:{last_processed_id}!")

            print("Waiting for new mails...")
            while True:
                try:
                    imap_ssl.select(mailbox=FOLDER)
                    resp_code, unseen_mails = imap_ssl.search(None, "UNSEEN")
                    unseen_ids = [int(i) for i in unseen_mails[0].decode().split()] if unseen_mails[0] else []
                    new_ids = [message_id for message_id in unseen_ids if message_id >last_processed_id]

                    # print("New mail recieved...") if len(new_ids) >= 1 else ""
                    for message_id in new_ids:
                        fetch_and_process(imap_ssl, message_id)
                        last_processed_id = message_id
                    time.sleep(CHECK_INTERVAL)
                except (imaplib.IMAP4.error) as net_err:
                    print(f"Network/IMAP connection lost during poling: {net_err}")
        except KeyboardInterrupt:
            print("\n You stopped the assistant!")
            if imap_ssl:
                try: imap_ssl.logout()
                except Exception: pass
            break
        except Exception as e:
            print(f"\n Error Occured: {e}")
            print("Reconnecting in 15 seconds...")
            time.sleep(15)
            start_assistant()
        finally:
            try:
                imap_ssl.logout()
            except:
                pass

if __name__ == "__main__":
    start_assistant()