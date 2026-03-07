// This is api.ts and this is used for handling requests to the FastAPI backend.

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function simulateLabEvent(patientId: string, reportType: string) {
    const response = await fetch(`${API_URL}/api/lab-event`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ patient_id: patientId, report_type: reportType }),
    });
    return response.json();
}
