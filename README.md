# DiaFLowAssist
DiaFLowAssist

## Emergency workflow

When **Acute complaint / symptoms** is checked, selecting any listed emergency
symptom or entering CBG below 70 or above 300 mg/dL, SBP below 90 mmHg, or RR
above 20/min raises an emergency alert and disables ordinary queue assignment.
For acute complaints, eGFR and the time since the last kidney check are required.
The doctor popup appears only after a patient name and numeric CBG, SBP, and RR
values, eGFR, and the last kidney check have been selected. It displays the
reported symptoms and vitals.
**Accept** adds the patient to the Emergency priority queue; **Bypass the queue**
adds the patient to the routine queue. Both choices close the popup, reset the
intake form, and refresh the queue. Emergency queue rows have **Delete** and
**Shifted to ward** icon actions. Deletion removes the appointment from the CSV;
shifting to the ward removes it from the active queues but retains it in
`data/appointment.csv` with its ward status. When a consultation ends, the
patient record and consultation timestamps are moved from
`data/appointment.csv` to `data/patient.csv`. When an acute patient is accepted
or bypassed into a queue, their entered CBG, SBP, RR, symptoms, and emergency
flags are saved to `data/vital.csv`. These are workflow flags based on entered
data, not a diagnosis.
