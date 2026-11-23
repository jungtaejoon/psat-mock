/**
 * 수험생 이야기(댓글·감정 반응) — Supabase(alltests 프로젝트).
 * supabase-js 는 이 기능을 처음 쓸 때만 불러온다(첫 화면·시험 화면 번들에 넣지 않음).
 *
 * 대상(target): 시험 전체 "x:<examId>", 문항 "q:<paperId>:<no>"
 * 반응은 로그인 없이 기기 id(브라우저에 저장한 무작위 uuid)로, 댓글은 구글·카카오 로그인 후.
 */
import type { SupabaseClient, User } from "@supabase/supabase-js";

// 공개용(publishable) 키: 브라우저에 그대로 노출되는 값이라 비밀이 아니다. 권한은 DB 의 RLS 로 막는다
const URL = "https://hzyvylezebigwugffxii.supabase.co";
const KEY = "sb_publishable_QNI_tSA_PlIuAwc0ZvTrjA_WYwvylFi";
const RETURN_KEY = "alltests.talk.return";
// Supabase 대시보드에서 켠 로그인 방법만 버튼으로 보인다 (비어 있으면 댓글 쓰기는 "준비 중")
export const PROVIDERS: { id: "kakao" | "google"; label: string }[] = [];

export const MOODS = [
  { k: "hard", e: "😵", label: "어려워요" },
  { k: "confusing", e: "🤔", label: "헷갈려요" },
  { k: "easy", e: "😌", label: "쉬웠어요" },
  { k: "good", e: "👍", label: "좋은 문제" },
  { k: "wrong_answer", e: "🚨", label: "정답 이상해요" },
] as const;
export type Mood = (typeof MOODS)[number]["k"];

export interface Comment {
  id: string;
  author_id: string;
  author_name: string;
  body: string;
  mood: Mood | null;
  created_at: string;
}
export interface ReactionCount {
  kind: Mood;
  n: number;
  mine: boolean;
}

let clientP: Promise<SupabaseClient> | null = null;
export function client(): Promise<SupabaseClient> {
  clientP ??= import("@supabase/supabase-js").then(({ createClient }) =>
    createClient(URL, KEY, {
      auth: { flowType: "pkce", persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    }),
  );
  return clientP;
}

export function deviceId(): string {
  try {
    let id = localStorage.getItem("alltests.device");
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem("alltests.device", id);
    }
    return id;
  } catch {
    return (window as unknown as { __dev?: string }).__dev ??= crypto.randomUUID();
  }
}

export async function getReactions(target: string): Promise<ReactionCount[]> {
  const sb = await client();
  const { data, error } = await sb.rpc("get_reactions", { p_targets: [target], p_device: deviceId() });
  if (error) throw error;
  return (data as { kind: Mood; n: number; mine: boolean }[]).map((r) => ({ kind: r.kind, n: Number(r.n), mine: !!r.mine }));
}

export async function toggleReaction(target: string, kind: Mood): Promise<boolean> {
  const sb = await client();
  const { data, error } = await sb.rpc("toggle_reaction", { p_target: target, p_kind: kind, p_device: deviceId() });
  if (error) throw error;
  return !!data;
}

export async function listComments(target: string, limit = 30): Promise<Comment[]> {
  const sb = await client();
  const { data, error } = await sb
    .from("comments")
    .select("id,author_id,author_name,body,mood,created_at")
    .eq("target", target)
    .order("created_at", { ascending: false })
    .limit(limit);
  if (error) throw error;
  return data as Comment[];
}

export async function addComment(target: string, body: string, mood: Mood | null): Promise<Comment> {
  const sb = await client();
  const { data, error } = await sb
    .from("comments")
    .insert({ target, body, mood })
    .select("id,author_id,author_name,body,mood,created_at")
    .single();
  if (error) throw error;
  return data as Comment;
}

export async function deleteComment(id: string): Promise<void> {
  const sb = await client();
  const { error } = await sb.from("comments").delete().eq("id", id);
  if (error) throw error;
}

export async function reportComment(id: string): Promise<void> {
  const sb = await client();
  const { error } = await sb.rpc("report_comment", { p_id: id, p_device: deviceId() });
  if (error) throw error;
}

export async function currentUser(): Promise<User | null> {
  const sb = await client();
  const { data } = await sb.auth.getSession();
  return data.session?.user ?? null;
}

export async function onAuth(cb: (u: User | null) => void): Promise<() => void> {
  const sb = await client();
  const { data } = sb.auth.onAuthStateChange((_e, s) => cb(s?.user ?? null));
  return () => data.subscription.unsubscribe();
}

/** 구글·카카오 로그인. 돌아올 화면(해시 경로)을 기억해 두고 사이트 첫 주소로 돌아온다 */
export async function signIn(provider: "google" | "kakao"): Promise<void> {
  const sb = await client();
  try {
    sessionStorage.setItem(RETURN_KEY, location.hash || "#/");
  } catch {
    /* 저장이 막혀도 로그인은 진행 */
  }
  const { error } = await sb.auth.signInWithOAuth({
    provider,
    options: { redirectTo: `${location.origin}/` },
  });
  if (error) throw error;
}

export async function signOut(): Promise<void> {
  const sb = await client();
  await sb.auth.signOut();
}

/** 로그인에서 돌아왔을 때(?code=…) 세션을 만들고 원래 화면으로 */
export async function finishLoginIfNeeded(): Promise<void> {
  const q = new URLSearchParams(location.search);
  if (!q.has("code") && !q.has("error")) return;
  const sb = await client();
  await sb.auth.getSession(); // detectSessionInUrl 이 code 를 세션으로 바꾼다
  let back = "#/";
  try {
    back = sessionStorage.getItem(RETURN_KEY) || "#/";
    sessionStorage.removeItem(RETURN_KEY);
  } catch {
    /* 기본값 */
  }
  history.replaceState(null, "", `${location.pathname}${back}`);
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}

export function friendlyError(e: unknown): string {
  const m = (e as { message?: string })?.message || String(e);
  if (/잠시 후/.test(m)) return m;
  if (/provider is not enabled|Unsupported provider/i.test(m)) return "이 로그인 방법은 아직 준비 중이에요.";
  if (/JWT|not allowed|row-level security/i.test(m)) return "로그인이 필요해요.";
  return "잠시 문제가 생겼어요. 다시 시도해 주세요.";
}
