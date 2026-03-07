# This is twilio_service.py and this is used for interacting with the Twilio API to place and manage calls.

import os
from twilio.rest import Client

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# Initialize client here if environment variables are set
client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

def make_outbound_call(patient_id: str):
    if not client:
        print(f"Twilio client not initialized. Cannot make call to {patient_id}")
        return
    # Example logic to call patient
    # call = client.calls.create(
    #     to="+1234567890",
    #     from_=TWILIO_PHONE_NUMBER,
    #     url="http://your-ngrok-url/api/twilio/webhook"
    # )
    print(f"Call initiated for patient {patient_id}")
