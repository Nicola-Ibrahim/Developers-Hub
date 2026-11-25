"use client";
import { FormEvent, useEffect, useState } from "react";
import { api, apiGeneration, isApiGenerationCurrent, isStaleRequest } from "@/lib/api/client";

type Profile = { userId: string; userName: string; displayName: string | null };
type SecurityEvent = { id: string; action: string; outcome: string; createdAt: string };
type Token = { id: string; name: string; projectId: string | null; scopes: string[]; expiresAt: string; revokedAt: string | null };
type CreatedToken = Token & { secret: string };
const TOKEN_SCOPES = ["catalog:read", "resources:read", "resources:write", "connections:read"] as const;

export default function AccountCards({ userId, userName }: { userId: string; userName: string }) {
    const [profile, setProfile] = useState<Profile>({ userId, userName, displayName: "" });
    const [history, setHistory] = useState<SecurityEvent[]>([]);
    const [tokens, setTokens] = useState<Token[]>([]);
    const [displayName, setDisplayName] = useState("");
    const [tokenName, setTokenName] = useState("");
    const [scopes, setScopes] = useState<string[]>(["catalog:read", "resources:read"]);
    const [hours, setHours] = useState("24");
    const [secret, setSecret] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [notice, setNotice] = useState("");

    useEffect(() => {
        const generation = apiGeneration();
        let active = true;
        const load = async () => {
            try {
                const [p, h, t] = await Promise.all([
                    api<Profile>("me/profile"), api<SecurityEvent[]>("me/security-history"), api<Token[]>("me/tokens"),
                ]);
                if (!active || !isApiGenerationCurrent(generation)) return;
                setProfile(p); setDisplayName(p.displayName ?? ""); setHistory(h); setTokens(t);
            } catch (cause) {
                if (active && !isStaleRequest(cause) && isApiGenerationCurrent(generation)) setError(messageOf(cause, "Could not load account details"));
            }
        };
        void load();
        return () => { active = false; };
    }, []);

    async function saveProfile(event: FormEvent) {
        event.preventDefault(); const generation = apiGeneration(); setBusy(true); setError(""); setNotice("");
        try {
            const updated = await api<Profile>("me/profile", { method: "PATCH", body: JSON.stringify({ displayName: displayName.trim() || null }) });
            if (!isApiGenerationCurrent(generation)) return;
            setProfile(updated); setDisplayName(updated.displayName ?? ""); setNotice("Profile updated.");
        } catch (cause) { if (!isStaleRequest(cause) && isApiGenerationCurrent(generation)) setError(messageOf(cause, "Could not update profile")); }
        finally { if (isApiGenerationCurrent(generation)) setBusy(false); }
    }
    async function createToken(event: FormEvent) {
        event.preventDefault(); const generation = apiGeneration(); setBusy(true); setError(""); setNotice(""); setSecret("");
        try {
            const { secret: createdSecret, ...created } = await api<CreatedToken>("me/tokens", { method: "POST", body: JSON.stringify({ name: tokenName.trim(), scopes, hours: Number(hours) }) });
            if (!isApiGenerationCurrent(generation)) return;
            setTokens(current => [created, ...current.filter(token => token.id !== created.id)]); setSecret(createdSecret); setNotice("Token created. Copy its secret now; it will not be shown again."); setTokenName("");
        } catch (cause) { if (!isStaleRequest(cause) && isApiGenerationCurrent(generation)) setError(messageOf(cause, "Could not create token")); }
        finally { if (isApiGenerationCurrent(generation)) setBusy(false); }
    }
    async function rotateToken(token: Token) {
        const generation = apiGeneration(); setBusy(true); setError(""); setNotice(""); setSecret("");
        try {
            const { secret: rotatedSecret, ...rotated } = await api<CreatedToken>(`me/tokens/${encodeURIComponent(token.id)}/rotate`, { method: "POST", body: "{}" });
            if (!isApiGenerationCurrent(generation)) return;
            setTokens(current => [rotated, ...current.filter(item => item.id !== token.id && item.id !== rotated.id)]);
            setSecret(rotatedSecret); setNotice("Token rotated. Copy its new secret now.");
        } catch (cause) { if (!isStaleRequest(cause) && isApiGenerationCurrent(generation)) setError(messageOf(cause, "Could not rotate token")); }
        finally { if (isApiGenerationCurrent(generation)) setBusy(false); }
    }
    async function revokeToken(token: Token) {
        const generation = apiGeneration(); setBusy(true); setError(""); setNotice(""); setSecret("");
        try {
            await api(`me/tokens/${encodeURIComponent(token.id)}`, { method: "DELETE" });
            if (!isApiGenerationCurrent(generation)) return;
            setTokens(current => current.filter(item => item.id !== token.id)); setNotice("Token revoked.");
        } catch (cause) { if (!isStaleRequest(cause) && isApiGenerationCurrent(generation)) setError(messageOf(cause, "Could not revoke token")); }
        finally { if (isApiGenerationCurrent(generation)) setBusy(false); }
    }

    return <div className="account-cards">
      {(error || notice) && <p className={`identity-message ${error ? "identity-error" : "identity-success"}`} role={error ? "alert" : "status"}>{error || notice}</p>}
      <section className="panel account-card"><div className="panel-heading"><div><div className="eyebrow">YOUR ACCOUNT</div><h2>Profile</h2></div></div>
        <form className="account-profile-form" onSubmit={saveProfile}><label>User name<input value={profile.userName || userName} readOnly/></label><label>Display name<input value={displayName} maxLength={100} onChange={event => setDisplayName(event.target.value)} autoComplete="name"/></label><button className="primary-button" disabled={busy}>Save profile</button></form>
      </section>
      <section className="panel account-card"><div className="panel-heading"><div><div className="eyebrow">ACCOUNT & ACCESS</div><h2>Security history</h2></div></div>
        {!history.length ? <p className="identity-muted">No security events were returned.</p> : <div className="identity-session-list">{history.map(item => <article className="identity-session" key={item.id}><div><strong>{item.action.replaceAll("_", " ")}</strong><span>{item.outcome}</span></div><time dateTime={item.createdAt}>{formatDate(item.createdAt)}</time></article>)}</div>}
      </section>
      <section className="panel account-card account-token-card"><div className="panel-heading"><div><div className="eyebrow">PERSONAL ACCESS</div><h2>Personal tokens</h2><p>Create short lived credentials for personal automation.</p></div></div>
        <form className="account-token-form" onSubmit={createToken}><label>Name<input value={tokenName} onChange={event => setTokenName(event.target.value)} required maxLength={100}/></label><fieldset className="account-scope-options"><legend>Allowed scopes</legend>{TOKEN_SCOPES.map(scope => <label key={scope}><input type="checkbox" checked={scopes.includes(scope)} onChange={event => setScopes(current => event.target.checked ? [...current, scope] : current.filter(item => item !== scope))}/>{scope}</label>)}</fieldset><label>Lifetime (hours)<input type="number" value={hours} min="1" max="720" onChange={event => setHours(event.target.value)} required/></label><button className="primary-button" disabled={busy || !tokenName.trim() || !scopes.length || !Number.isInteger(Number(hours)) || Number(hours) < 1 || Number(hours) > 720}>Create token</button></form>
        {secret && <div className="account-token-secret"><strong>Token secret</strong><code>{secret}</code><button className="secondary-button" type="button" onClick={() => setSecret("")}>Clear secret</button></div>}
        {!tokens.length ? <p className="identity-muted">No personal tokens.</p> : <div className="identity-session-list">{tokens.map(token => <article className="identity-session" key={token.id}><div><strong>{token.name}</strong><span>Scopes: {token.scopes.join(", ") || "none"}</span><small>{token.projectId ? `Project ${token.projectId} · ` : "Personal · "}Expires {formatDate(token.expiresAt)}{token.revokedAt ? ` · Revoked ${formatDate(token.revokedAt)}` : ""}</small></div>{!token.revokedAt && <><button className="secondary-button" type="button" onClick={() => void rotateToken(token)} disabled={busy}>Rotate</button><button className="identity-danger-button" type="button" onClick={() => void revokeToken(token)} disabled={busy}>Revoke</button></>}</article>)}</div>}
      </section>
    </div>;
}
function messageOf(cause: unknown, fallback: string) { return cause instanceof Error && cause.message ? cause.message : fallback; }
function formatDate(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? "unknown" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date); }
