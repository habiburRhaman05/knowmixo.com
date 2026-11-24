/**
 * Shared loading fallback for every screen under the authenticated shell.
 * Keeps the sidebar visible (it's in the group layout) and shows a subtle
 * shimmer where content will appear.
 */
export default function AppLoading() {
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-6 h-10 w-48 skeleton" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-32 skeleton" />
        ))}
      </div>
      <div className="mt-8 h-72 skeleton" />
    </div>
  );
}
