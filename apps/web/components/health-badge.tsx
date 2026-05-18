import { getApiHealth } from "@/lib/api";

export async function HealthBadge() {
  const health = await getApiHealth();

  if (!health.ok) {
    return (
      <span
        className="inline-flex items-center gap-2 rounded-full border border-red-500/40 bg-red-500/10 px-3 py-1 text-xs text-red-200"
        title={health.error}
      >
        <span className="size-2 rounded-full bg-red-400" />
        API offline
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-200">
      <span className="size-2 rounded-full bg-emerald-400" />
      API {health.data.service} v{health.data.version}
    </span>
  );
}
