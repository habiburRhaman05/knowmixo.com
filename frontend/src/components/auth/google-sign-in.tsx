"use client";
import * as React from "react";
import Script from "next/script";
import { GoogleButton } from "@/components/ui/google-button";
import { publicEnv } from "@/lib/env";
import { apiFetch } from "@/lib/api-client";
import { describeError } from "@/lib/errors";
import { useToast } from "@/components/ui/toast";

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (opts: {
            client_id: string;
            callback: (resp: { credential: string }) => void;
            auto_select?: boolean;
            use_fedcm_for_prompt?: boolean;
            ux_mode?: "popup" | "redirect";
          }) => void;
          prompt: () => void;
          cancel: () => void;
        };
      };
    };
  }
}

/**
 * Google sign-in / link button. The browser receives an id_token from
 * Google Identity Services and posts it to the BFF, which forwards it to
 * the backend. The backend verifies audience/issuer/expiry independently --
 * we never trust the browser's parse.
 *
 * - `mode="signin"` posts to /api/bff/auth/google and redirects on success.
 * - `mode="link"` posts to /api/bff/me/oauth/google/link (attaches to the
 *   signed-in account; requires a recent password re-auth).
 */
export function GoogleSignIn({
  mode = "signin",
  nextPath = "/overview",
  label,
}: {
  mode?: "signin" | "link";
  nextPath?: string;
  label?: string;
}) {
  const [loading, setLoading] = React.useState(false);
  const [ready, setReady] = React.useState(false);
  const { toast } = useToast();
  const scriptLoaded = React.useRef(false);

  const clientId = publicEnv.googleClientId;

  const handleCredential = React.useCallback(
    async (credential: string) => {
      setLoading(true);
      try {
        const path = mode === "link" ? "/api/bff/me/oauth/google/link" : "/api/bff/auth/google";
        await apiFetch(path, { method: "POST", json: { id_token: credential } });
        if (mode === "signin") {
          window.location.assign(nextPath);
        } else {
          toast({ tone: "success", title: "Google account linked" });
          setLoading(false);
        }
      } catch (error) {
        const info = describeError(error);
        toast({ tone: "danger", title: info.title, description: info.message });
        setLoading(false);
      }
    },
    [mode, nextPath, toast]
  );

  const initialize = React.useCallback(() => {
    if (!clientId || !window.google) return;
    window.google.accounts.id.initialize({
      client_id: clientId,
      callback: (resp) => handleCredential(resp.credential),
      use_fedcm_for_prompt: true,
    });
    setReady(true);
  }, [clientId, handleCredential]);

  React.useEffect(() => {
    if (scriptLoaded.current && window.google) initialize();
  }, [initialize]);

  const onClick = () => {
    if (!clientId) {
      toast({
        tone: "warning",
        title: "Google sign-in isn't configured",
        description: "Ask an administrator to set NEXT_PUBLIC_GOOGLE_CLIENT_ID.",
      });
      return;
    }
    if (!window.google || !ready) {
      toast({ tone: "info", title: "Loading Google sign-in…" });
      return;
    }
    window.google.accounts.id.prompt();
  };

  return (
    <>
      <Script
        src="https://accounts.google.com/gsi/client"
        strategy="afterInteractive"
        onLoad={() => {
          scriptLoaded.current = true;
          initialize();
        }}
      />
      <GoogleButton loading={loading} onClick={onClick}>
        {label ?? (mode === "link" ? "Link a Google account" : "Continue with Google")}
      </GoogleButton>
    </>
  );
}
