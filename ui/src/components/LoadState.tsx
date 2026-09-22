export default function LoadState({ loading, error, retry }: {
  loading: boolean; error: string | null; retry: () => void;
}) {
  if (error) return <div className="empty-state inline-error" role="alert"><p>{error}</p><button onClick={retry}>Try again</button></div>;
  if (loading) return <div className="empty-state" role="status"><span className="connecting-ring" aria-hidden="true" /> Loading…</div>;
  return null;
}
