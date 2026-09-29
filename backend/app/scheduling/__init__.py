"""When the practice can see a patient.

Pure calculation over three inputs: the practice's opening hours, the length of
an appointment, and the appointments already booked. No database and no
network, so every rule here is testable without either — the callers in
app/api/routes and app/engine do the reading and hand the rows in.
"""
