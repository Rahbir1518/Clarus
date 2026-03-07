export default function TriggerDetailPage({
  params,
}: {
  params: Promise<{ triggerId: string }>;
}) {
  return (
    <div>
      <h1 className="text-2xl font-semibold">Trigger Details</h1>
      <p className="text-muted-foreground">View and edit trigger configuration.</p>
    </div>
  );
}
