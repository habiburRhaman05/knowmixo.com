"use client";
import * as React from "react";
import { Lightbulb, ThumbsDown, CheckCircle2, X, Send, Loader2, MessageSquareQuote } from "lucide-react";

import { TopBar } from "@/components/layout/topbar";
import { PageShell } from "@/components/layout/page-shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { apiFetch } from "@/lib/api-client";
import { describeError } from "@/lib/errors";
import { useToast } from "@/components/ui/toast";
import { fromNow } from "@/lib/utils";

type Gap = {
  id: string;
  sample_question: string;
  occurrence_count: number;
  first_seen_at: string;
  last_seen_at: string;
  status: string;
};

type BadAnswer = {
  message_id: string;
  conversation_id: string;
  content: string;
  created_at: string;
  reasons: string[];
  status: string;
};

const REASON_LABEL: Record<string, string> = {
  thumbs_down: "Thumbs down",
  hallucination: "Unsupported claim",
  escalated: "Escalated",
};

export default function QualityPage() {
  return (
    <>
      <TopBar title="Quality" description="Knowledge gaps and answers that need a second look." />
      <main>
        <PageShell>
          <Tabs defaultValue="gaps">
            <TabsList>
              <TabsTrigger value="gaps">Gaps</TabsTrigger>
              <TabsTrigger value="bad-answers">Bad answers</TabsTrigger>
            </TabsList>
            <TabsContent value="gaps">
              <GapsPanel />
            </TabsContent>
            <TabsContent value="bad-answers">
              <BadAnswersPanel />
            </TabsContent>
          </Tabs>
        </PageShell>
      </main>
    </>
  );
}

function GapsPanel() {
  const { toast } = useToast();
  const [gaps, setGaps] = React.useState<Gap[] | null>(null);
  const [error, setError] = React.useState<unknown>(null);
  const [answering, setAnswering] = React.useState<string | null>(null);
  const [answer, setAnswer] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  const load = React.useCallback(async () => {
    try {
      setGaps(await apiFetch<Gap[]>("/api/bff/quality/gaps?status=open"));
    } catch (e) {
      setError(e);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  async function submitAnswer(id: string) {
    if (!answer.trim()) return;
    setBusy(true);
    try {
      await apiFetch(`/api/bff/quality/gaps/${id}/resolve`, { method: "POST", json: { answer: answer.trim() } });
      toast({ tone: "success", title: "Added to your knowledge base" });
      setAnswering(null);
      setAnswer("");
      await load();
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    } finally {
      setBusy(false);
    }
  }

  async function ignore(id: string) {
    try {
      await apiFetch(`/api/bff/quality/gaps/${id}/ignore`, { method: "POST" });
      await load();
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    }
  }

  if (error) {
    const info = describeError(error);
    return (
      <Alert tone="danger" title={info.title} className="mt-4">
        {info.message}
      </Alert>
    );
  }

  return (
    <div className="mt-4 space-y-3">
      {gaps === null ? (
        <>
          <div className="h-24 skeleton" />
          <div className="h-24 skeleton" />
        </>
      ) : gaps.length === 0 ? (
        <EmptyState
          icon={Lightbulb}
          title="No gaps right now"
          description="Questions your assistant couldn't answer will show up here, clustered together."
        />
      ) : (
        gaps.map((gap) => (
          <Card key={gap.id}>
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium">{gap.sample_question}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Asked {gap.occurrence_count} time{gap.occurrence_count === 1 ? "" : "s"} · last seen{" "}
                    {fromNow(gap.last_seen_at)}
                  </p>
                </div>
                <Badge tone="warning">{gap.occurrence_count}×</Badge>
              </div>
              {answering === gap.id ? (
                <div className="mt-3 space-y-2">
                  <Textarea
                    value={answer}
                    onChange={(e) => setAnswer(e.target.value)}
                    placeholder="Write the answer to add to your knowledge base…"
                    rows={3}
                  />
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => void submitAnswer(gap.id)} loading={busy} disabled={!answer.trim()}>
                      <Send className="h-3.5 w-3.5" /> Save answer
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setAnswering(null)}>
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="mt-3 flex gap-2">
                  <Button size="sm" onClick={() => setAnswering(gap.id)}>
                    Write the answer
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => void ignore(gap.id)}>
                    <X className="h-3.5 w-3.5" /> Ignore
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        ))
      )}
    </div>
  );
}

function BadAnswersPanel() {
  const { toast } = useToast();
  const [items, setItems] = React.useState<BadAnswer[] | null>(null);
  const [error, setError] = React.useState<unknown>(null);
  const [correcting, setCorrecting] = React.useState<string | null>(null);
  const [correction, setCorrection] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  const load = React.useCallback(async () => {
    try {
      setItems(await apiFetch<BadAnswer[]>("/api/bff/quality/bad-answers"));
    } catch (e) {
      setError(e);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  async function submitCorrection(messageId: string) {
    if (!correction.trim()) return;
    setBusy(true);
    try {
      await apiFetch(`/api/bff/quality/bad-answers/${messageId}/correct`, {
        method: "POST",
        json: { correction_text: correction.trim() },
      });
      toast({ tone: "success", title: "Correction saved", description: "This becomes new knowledge for your assistant." });
      setCorrecting(null);
      setCorrection("");
      await load();
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    } finally {
      setBusy(false);
    }
  }

  async function dismiss(messageId: string) {
    try {
      await apiFetch(`/api/bff/quality/bad-answers/${messageId}/dismiss`, { method: "POST" });
      await load();
    } catch (e) {
      const info = describeError(e);
      toast({ tone: "danger", title: info.title, description: info.message });
    }
  }

  if (error) {
    const info = describeError(error);
    return (
      <Alert tone="danger" title={info.title} className="mt-4">
        {info.message}
      </Alert>
    );
  }

  return (
    <div className="mt-4 space-y-3">
      {items === null ? (
        <>
          <div className="h-24 skeleton" />
          <div className="h-24 skeleton" />
        </>
      ) : items.length === 0 ? (
        <EmptyState
          icon={ThumbsDown}
          title="No flagged answers"
          description="Answers with a thumbs-down, an unsupported claim, or an escalation show up here."
        />
      ) : (
        items.map((item) => (
          <Card key={item.message_id}>
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm text-muted-foreground">{fromNow(item.created_at)}</p>
                  <p className="mt-1 whitespace-pre-wrap">{item.content}</p>
                </div>
                <div className="flex gap-1">
                  {item.reasons.map((r) => (
                    <Badge key={r} tone="danger">
                      {REASON_LABEL[r] ?? r}
                    </Badge>
                  ))}
                </div>
              </div>
              {correcting === item.message_id ? (
                <div className="mt-3 space-y-2">
                  <Textarea
                    value={correction}
                    onChange={(e) => setCorrection(e.target.value)}
                    placeholder="Write the correct answer…"
                    rows={3}
                  />
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => void submitCorrection(item.message_id)} loading={busy} disabled={!correction.trim()}>
                      <MessageSquareQuote className="h-3.5 w-3.5" /> Save correction
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setCorrecting(null)}>
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="mt-3 flex gap-2">
                  <Button size="sm" onClick={() => setCorrecting(item.message_id)}>
                    Correct this answer
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => void dismiss(item.message_id)}>
                    <CheckCircle2 className="h-3.5 w-3.5" /> Looks fine
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        ))
      )}
    </div>
  );
}
