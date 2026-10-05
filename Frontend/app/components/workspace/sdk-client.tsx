"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Circle, LoaderCircle, ShieldCheck } from "lucide-react";
import { useConnectedWallet } from "@solana/kit-plugin-wallet/react";
import { useAppClient } from "../../lib/client-provider";
import { apiClient } from "../../lib/api-client";

type FlowState =
  | "disconnected"
  | "wallet"
  | "preparing"
  | "existing"
  | "scoring"
  | "issuing"
  | "verifying"
  | "success"
  | "error";

type AttestationResult = {
  score: {
    trustScore: number;
    riskLevel: string;
  };
  attestation: {
    verified: boolean;
    alreadyExisted: boolean;
    trustScore: number;
    riskLevel: string;
  };
};

const progressSteps: { state: FlowState; label: string }[] = [
  { state: "preparing", label: "Preparing" },
  { state: "scoring", label: "Calculating trust score" },
  { state: "issuing", label: "Creating your attestation" },
  { state: "verifying", label: "Confirming your credential" },
];
const existingSteps: { state: FlowState; label: string }[] = [
  { state: "preparing", label: "Preparing" },
  { state: "existing", label: "Checking your existing credential" },
  { state: "verifying", label: "Confirming your credential" },
];

function friendlyError(code: string) {
  switch (code) {
    case "scoring":
      return "We couldn't calculate your trust score right now. Please try again shortly.";
    case "verification":
      return "We couldn't verify your attestation on-chain. Please try again.";
    case "wallet_disconnected":
      return "Your wallet was disconnected. Please reconnect and try again.";
    case "attestation":
      return "We couldn't create your attestation right now. Please try again shortly.";
    default:
      return "We couldn't reach CredLayer right now. Please try again shortly.";
  }
}

export function TrustScoreLiveDemo() {
  const client = useAppClient();
  const connectedWallet = useConnectedWallet(client);
  const walletAddress = connectedWallet?.account.address
    ? String(connectedWallet.account.address)
    : null;
  const [flowState, setFlowState] = useState<FlowState>(
    walletAddress ? "wallet" : "disconnected",
  );
  const [result, setResult] = useState<AttestationResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [progressMessage, setProgressMessage] = useState<string | null>(null);
  const requestController = useRef<AbortController | null>(null);
  const previousWalletAddress = useRef(walletAddress);

  useEffect(() => {
    const walletChanged = previousWalletAddress.current !== walletAddress;
    const hadInFlightRequest = requestController.current !== null;
    previousWalletAddress.current = walletAddress;
    if (walletChanged && requestController.current) {
      requestController.current.abort();
      requestController.current = null;
    }

    if (!walletAddress && walletChanged && hadInFlightRequest) {
      setResult(null);
      setErrorMessage(friendlyError("wallet_disconnected"));
      setFlowState("error");
      return;
    }
    setResult(null);
    setErrorMessage(null);
    setProgressMessage(null);
    setFlowState(walletAddress ? "wallet" : "disconnected");
  }, [walletAddress]);

  const runAttestation = async () => {
    if (!walletAddress || requestController.current) return;

    const controller = new AbortController();
    requestController.current = controller;
    setErrorMessage(null);
    setProgressMessage(null);
    setResult(null);
    setFlowState("preparing");

    try {
      const url = apiClient.getUri({
        url: `/scores/${encodeURIComponent(walletAddress)}/attestation`,
      });
      const response = await fetch(url, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        signal: controller.signal,
      });

      const payload = (await response.json().catch(() => ({}))) as {
        success?: boolean;
        txHash?: string;
        alreadyExists?: boolean;
        score?: {
          trustScore?: number;
          riskLevel?: string;
          trust_score?: number;
          risk_level?: string;
        };
        detail?: string;
        error?: string;
        message?: string;
      };

      if (!response.ok || payload.success !== true) {
        const detail = payload.detail || payload.error || payload.message || "attestation";
        throw new Error(typeof detail === "string" ? detail : "attestation");
      }

      const trustScore = Number(
        payload.score?.trustScore ?? payload.score?.trust_score ?? 0,
      );
      const riskLevel = String(
        payload.score?.riskLevel ?? payload.score?.risk_level ?? "unknown",
      ).toUpperCase();

      if (!Number.isFinite(trustScore) || !riskLevel) {
        throw new Error("verification");
      }

      const finalResult: AttestationResult = {
        score: {
          trustScore,
          riskLevel,
        },
        attestation: {
          verified: true,
          alreadyExisted: Boolean(payload.alreadyExists ?? false),
          trustScore,
          riskLevel,
        },
      };

      setResult(finalResult);
      setFlowState("success");
    } catch (error) {
      if (controller.signal.aborted) return;
      console.error("Attestation flow failed", error);

      // Prefer showing backend detail when running in development, otherwise keep the friendly message
      const rawDetail = error instanceof Error ? error.message : String(error);
      const showableDetail =
        process.env.NODE_ENV === "development" && rawDetail ? rawDetail : null;

      setErrorMessage(showableDetail ?? friendlyError("attestation"));
      setFlowState("error");
    } finally {
      if (requestController.current === controller) {
        requestController.current = null;
      }
    }
  };

  const isProcessing = [
    "preparing",
    "existing",
    "scoring",
    "issuing",
    "verifying",
  ].includes(flowState);
  const currentSteps = flowState === "existing" ? existingSteps : progressSteps;

  return (
    <section aria-labelledby="reputation-flow-title" className="py-2">
      <div className="mx-auto max-w-3xl">
        <div className="border-b border-border pb-7">
          <div className="flex items-center gap-3 text-primary">
            <ShieldCheck className="size-5" aria-hidden="true" />
            <span className="text-xs font-semibold uppercase tracking-[0.14em]">
              CredLayer Reputation
            </span>
          </div>
          <h2
            id="reputation-flow-title"
            className="mt-5 max-w-2xl text-3xl font-semibold leading-tight text-foreground sm:text-4xl"
          >
            Verify your on-chain reputation
          </h2>
          <p className="mt-3 max-w-xl text-sm leading-6 text-muted-foreground">
            Connect your Solana wallet to calculate your trust score and create
            a verifiable credential.
          </p>
        </div>

        <div className="flex flex-col gap-5 border-b border-border py-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              {walletAddress ? "Wallet connected" : "Wallet"}
            </p>
            <p className="mt-2 font-mono text-sm text-foreground">
              {walletAddress
                ? `${walletAddress.slice(0, 4)}...${walletAddress.slice(-4)}`
                : "Not connected"}
            </p>
          </div>
        </div>

        {walletAddress && flowState !== "success" && (
          <div className="py-6">
            <button
              type="button"
              onClick={runAttestation}
              disabled={isProcessing}
              className="inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-md bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground transition hover:bg-primary\/90"
            >
              {isProcessing && (
                <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
              )}
              {isProcessing
                ? "Working on your verification..."
                : "Get Trust Score & Attestation"}
            </button>
          </div>
        )}

        {isProcessing && (
          <ol
            aria-label="Verification progress"
            aria-live="polite"
            className="space-y-4 border-b border-border py-5"
          >
            {currentSteps.map((step) => {
              const currentIndex = currentSteps.findIndex(
                (item) => item.state === flowState,
              );
              const stepIndex = currentSteps.findIndex(
                (item) => item.state === step.state,
              );
              const complete = stepIndex < currentIndex;
              const current = step.state === flowState;
              return (
                <li key={step.state} className="flex items-center gap-3 text-sm">
                  {complete ? (
                    <Check className="size-4 text-primary" aria-hidden="true" />
                  ) : current ? (
                    <LoaderCircle
                      className="size-4 animate-spin text-primary"
                      aria-hidden="true"
                    />
                  ) : (
                    <Circle
                      className="size-4 text-muted-foreground\/50"
                      aria-hidden="true"
                    />
                  )}
                  <span
                    className={
                      current || complete
                        ? "text-foreground"
                        : "text-muted-foreground"
                    }
                  >
                    {step.label}
                  </span>
                </li>
              );
            })}
          </ol>
        )}

        {isProcessing && progressMessage && (
          <p aria-live="polite" className="py-3 text-sm text-muted-foreground">
            {progressMessage}
          </p>
        )}

        {errorMessage && (
          <div
            role="alert"
            className="border-b border-border py-5 text-sm text-destructive"
          >
            {errorMessage}
          </div>
        )}

        {flowState === "success" && result && (
          <div aria-live="polite" className="py-7">
            <div className="flex flex-col gap-6 border-b border-border pb-7 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Trust score
                </p>
                <p className="mt-2 text-5xl font-semibold tabular-nums text-foreground">
                  {result.attestation.trustScore}
                  <span className="ml-2 text-base font-medium text-muted-foreground">
                    / 1000
                  </span>
                </p>
              </div>
              <div className="sm:text-right">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Risk level
                </p>
                <p className="mt-2 text-lg font-medium capitalize text-foreground">
                  {result.attestation.riskLevel.toLowerCase()} risk
                </p>
              </div>
            </div>
            <p className="flex items-center gap-2 pt-5 text-sm font-medium text-primary">
              <Check className="size-4" aria-hidden="true" />
              Attestation verified on-chain
              {result.attestation.alreadyExisted && (
                <span className="font-normal text-muted-foreground">
                  · Existing credential confirmed
                </span>
              )}
            </p>
            <button
              type="button"
              onClick={runAttestation}
              disabled={isProcessing}
              className="mt-6 min-h-10 rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground transition hover:bg-accent disabled:opacity-60"
            >
              Refresh
            </button>
          </div>
        )}

        {!walletAddress && (
          <p className="py-5 text-sm text-muted-foreground">
            Connect a wallet to get started.
          </p>
        )}
      </div>
    </section>
  );
}
