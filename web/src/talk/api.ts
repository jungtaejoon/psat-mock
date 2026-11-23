/**
 * 수험생 이야기(댓글·감정 반응) — Supabase(alltests 프로젝트).
 * supabase-js 는 이 기능을 처음 쓸 때만 불러온다(첫 화면·시험 화면 번들에 넣지 않음).
 *
 * 대상(target): 시험 전체 "x:<examId>", 문항 "q:<paperId>:<no>"
 * 로그인 없이: 반응·댓글 모두 기기 id(브라우저에 저장한 무작위 uuid)와 닉네임으로. 본인 글 삭제도 기기 id 로.
 */
import type { SupabaseClient } from "@supabase/supabase-js";

// 공개용(publishable) 키: 브라우저에 그대로 노출되는 값이라 비밀이 아니다. 권한은 DB 의 RLS 로 막는다
const URL = "https://hzyvylezebigwugffxii.supabase.co";
const KEY = "sb_publishable_QNI_tSA_PlIuAwc0ZvTrjA_WYwvylFi";
const NAME_KEY = "alltests.talk.name";

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
  mine: boolean;
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
      auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
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
  const { data, error } = await sb.rpc("list_comments", { p_target: target, p_device: deviceId(), p_limit: limit });
  if (error) throw error;
  return data as Comment[];
}

export async function addComment(target: string, body: string, mood: Mood | null, name: string): Promise<Comment> {
  const sb = await client();
  const { data, error } = await sb.rpc("add_comment", {
    p_target: target,
    p_body: body,
    p_mood: mood,
    p_name: name,
    p_device: deviceId(),
  });
  if (error) throw error;
  return (data as Comment[])[0];
}

export async function deleteComment(id: string): Promise<void> {
  const sb = await client();
  const { error } = await sb.rpc("delete_comment", { p_id: id, p_device: deviceId() });
  if (error) throw error;
}

export async function reportComment(id: string): Promise<void> {
  const sb = await client();
  const { error } = await sb.rpc("report_comment", { p_id: id, p_device: deviceId() });
  if (error) throw error;
}

/** 닉네임: 처음엔 "수험생 1234" 처럼 정해 두고, 바꾸면 기기에 저장 */
export function savedName(): string {
  try {
    let n = localStorage.getItem(NAME_KEY);
    if (!n) {
      n = `수험생 ${Math.floor(1000 + Math.random() * 9000)}`;
      localStorage.setItem(NAME_KEY, n);
    }
    return n;
  } catch {
    return "수험생";
  }
}
export function saveName(n: string): void {
  try {
    localStorage.setItem(NAME_KEY, n.slice(0, 20));
  } catch {
    /* 이 화면에서만 */
  }
}

export function friendlyError(e: unknown): string {
  const m = (e as { message?: string })?.message || String(e);
  if (/잠시 후/.test(m)) return m;
  if (/두 글자|링크는|같은 글/.test(m)) return m;
  return "잠시 문제가 생겼어요. 다시 시도해 주세요.";
}
