# This is supabase_service.py and this is used for interacting with the Supabase database (e.g., retrieving triggers, updating call logs).

import os
from supabase import create_client, Client

url: str = os.getenv("SUPABASE_URL", "")
key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# Initialize client here if environment variables are set
supabase: Client | None = None
if url and key:
    supabase = create_client(url, key)

def get_patient(patient_id: str):
    if supabase:
        response = supabase.table('patients').select('*').eq('id', patient_id).execute()
        return response.data
    return None
