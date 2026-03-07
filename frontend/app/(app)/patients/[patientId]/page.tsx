export default function PatientDetailPage({
  params,
}: {
  params: Promise<{ patientId: string }>;
}) {
  return (
    <div>
      <h1 className="text-2xl font-semibold">Patient Details</h1>
      <p className="text-muted-foreground">Patient profile, preferences, and call history.</p>
    </div>
  );
}
