export default function TriggerLogsPage({
  params,
}: {
  params: Promise<{ triggerId: string }>;
}) {
  return (
    <div>
      <h1 className="text-2xl font-semibold">Trigger Logs</h1>
      <p className="text-muted-foreground">Activity log for this trigger.</p>
    </div>
  );
}
