import { WidgetFrame } from "./frame";

type Props = { params: Promise<{ publicId: string }> };

export default async function WidgetPage({ params }: Props) {
  const { publicId } = await params;
  return <WidgetFrame publicId={publicId} />;
}
