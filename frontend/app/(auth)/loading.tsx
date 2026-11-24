/** Auth pages share a subdued centered skeleton while the chunk loads. */
export default function AuthLoading() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-md space-y-4">
        <div className="h-8 w-40 skeleton" />
        <div className="h-4 w-60 skeleton" />
        <div className="h-10 w-full skeleton" />
        <div className="h-10 w-full skeleton" />
        <div className="h-10 w-full skeleton rounded-lg" />
      </div>
    </div>
  );
}
